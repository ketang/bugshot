"""Vizdiff workflow: capture HEAD, classify against baseline, run bugshot, return drafts."""

from __future__ import annotations

import fcntl
import os
import shutil
import threading
from pathlib import Path
from typing import Callable

import baseline_manifest
import bugshot_workflow
import capture_runner
import gallery_server
import image_diff
import vizdiff_review_root
import vizline_workflow  # for VizlineError, _rev_parse, lock helpers


class VizdiffError(Exception):
    pass


def build_review_root(
    *,
    feature_worktree: Path,
    base_ref: str | None = None,
    base_dir: Path | None = None,
    head_only: bool = False,
) -> Path:
    """Preflight: lock head.lock, capture HEAD, classify, assemble review root.

    Releases the lock once the review root is on disk. Returns the review-root path.
    Raises VizdiffError on any failure.
    """
    feature_worktree = Path(feature_worktree).resolve()
    bugshot_dir = feature_worktree / ".bugshot"
    bugshot_dir.mkdir(exist_ok=True)
    vizline_workflow._ensure_gitignore(bugshot_dir)

    head_dir = bugshot_dir / "head"
    review_root = bugshot_dir / "review-root"

    capture_command = capture_runner.locate(feature_worktree, "capture-command")
    if capture_command is None:
        raise VizdiffError(
            "capture-command does not exist under "
            ".agent-plugins/bento/bugshot/viz/ in this worktree"
        )

    base_for_classification, base_ref_resolved, base_sha = _resolve_baseline_source(
        feature_worktree=feature_worktree,
        bugshot_dir=bugshot_dir,
        base_ref=base_ref,
        base_dir=base_dir,
        head_only=head_only,
    )
    head_sha = vizline_workflow._rev_parse(feature_worktree, "HEAD")

    lock_path = bugshot_dir / "head.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VizdiffError(
                "another vizdiff run holds the lock; wait for it to finish, then retry"
            )

        if head_dir.exists():
            shutil.rmtree(head_dir)
        head_dir.mkdir(parents=True)
        cap = capture_runner.run_capture(capture_command, head_dir, env={})
        if cap.returncode != 0:
            raise VizdiffError(
                f"capture-command failed (exit {cap.returncode}): {cap.stderr.strip()}"
            )

        if head_only:
            head_map = image_diff.discover(head_dir)
            pairs = [
                image_diff.Pair(rel_path=rel, classification="added",
                                base_sha=None, head_sha=sha)
                for rel, sha in sorted(head_map.items())
            ]
            base_for_assemble = head_dir  # unused: no base assets to copy
        else:
            assert base_for_classification is not None
            pairs, _warnings = image_diff.classify_pairs_with_warnings(
                base_for_classification, head_dir,
            )
            base_for_assemble = base_for_classification

        vizdiff_review_root.assemble(
            out_dir=review_root,
            base_dir=base_for_assemble,
            head_dir=head_dir,
            pairs=pairs,
            base_ref=base_ref_resolved or "head-only",
            base_sha=base_sha or "",
            head_sha=head_sha,
        )
        return review_root
    finally:
        os.close(fd)


def _resolve_baseline_source(
    *,
    feature_worktree: Path,
    bugshot_dir: Path,
    base_ref: str | None,
    base_dir: Path | None,
    head_only: bool,
) -> tuple[Path | None, str | None, str | None]:
    if head_only:
        return None, None, None
    if base_dir is not None:
        return Path(base_dir).resolve(), base_ref or "manual", "manual"

    baseline_dir = bugshot_dir / "baseline"
    manifest_path = baseline_dir / "manifest.json"
    if not manifest_path.is_file():
        raise VizdiffError(
            f"No baseline found at {baseline_dir}.\n"
            f"  Create one via:        bento:vizline --feature-worktree {feature_worktree}\n"
            f"  Or supply manually:    --base-dir <path-to-prebuilt-base-screenshots>\n"
            f"  Or skip diff entirely: --head-only"
        )
    manifest = baseline_manifest.read_manifest(manifest_path)
    resolved = base_ref or manifest.base_ref
    actual_sha = vizline_workflow._rev_parse(feature_worktree, resolved)
    if actual_sha != manifest.base_sha:
        raise VizdiffError(
            f"Stale baseline at {baseline_dir}: captured at {manifest.base_sha[:8]}, "
            f"base ref {resolved!r} now resolves to {actual_sha[:8]}.\n"
            f"  Refresh via:    bento:vizline --feature-worktree {feature_worktree} --refresh"
        )
    return baseline_dir / "images", resolved, actual_sha


def run_in_process(
    *,
    feature_worktree: Path,
    base_ref: str | None = None,
    base_dir: Path | None = None,
    head_only: bool = False,
    bind_address: str = "0.0.0.0",
    on_server_ready: Callable | None = None,
) -> list[dict]:
    """Build the review root, run the gallery, return enriched drafts.

    on_server_ready: optional callback invoked with the running GalleryServer
    so tests can submit comments + signal done programmatically.
    """
    review_root = build_review_root(
        feature_worktree=feature_worktree,
        base_ref=base_ref,
        base_dir=base_dir,
        head_only=head_only,
    )

    server = gallery_server.create_server(str(review_root), bind_address=bind_address)
    try:
        if on_server_ready is not None:
            thread = threading.Thread(target=on_server_ready, args=(server,))
            thread.start()
            thread.join(timeout=20)
        else:
            from bugshot_workflow import _wait_for_completion, ShellIO
            _wait_for_completion(server.db_path, ShellIO(json_output=True), 0.2)

        comments = bugshot_workflow._fetch_comments(server.db_path)
        from bugshot_workflow import _process_comments, ShellIO
        summary = _process_comments(
            comments,
            server.units,
            os.path.abspath(str(review_root)),
            ShellIO(json_output=True),
            json_output=True,
        )
        # Pair each draft with its source comment so we know the unit_id
        # even when bugshot collapsed it into the legacy single-asset shape.
        units_by_id = {u["id"]: u for u in server.units}
        comments_with_known_unit = [
            c for c in comments if c["unit_id"] in units_by_id
        ]
        return [
            _enrich_draft(draft, comment["unit_id"], server.units)
            for draft, comment in zip(summary.drafts, comments_with_known_unit)
        ]
    finally:
        server.shutdown()
        if os.path.exists(server.db_path):
            os.unlink(server.db_path)


def _enrich_draft(draft: dict, unit_id: str, units: list[dict]) -> dict:
    """Attach the unit's vizdiff metadata block and normalize to unit shape.

    Bugshot emits the legacy {image_name, image_path} draft shape for
    single-asset units. Vizdiff's added/removed classifications produce
    single-asset units, but downstream consumers expect a uniform unit
    shape across all four classifications. When a unit carries the
    bugshot.vizdiff/v1 schema, this function rewrites the draft into the
    unit shape (asset_names/asset_paths/...) and attaches the vizdiff block.
    """
    units_by_id = {u["id"]: u for u in units}
    unit = units_by_id.get(unit_id)
    if unit is None:
        return draft

    vizdiff_content = None
    for meta in unit["metadata"]:
        content = meta.get("content")
        if isinstance(content, dict) and content.get("schema") == vizdiff_review_root.VIZDIFF_SCHEMA:
            vizdiff_content = content
            break

    if vizdiff_content is None:
        return draft

    if "unit_id" not in draft:
        # Legacy single-asset shape — rebuild as a grouped-unit draft.
        image_path = draft.get("image_path", "")
        screenshot_dir = (
            os.path.dirname(os.path.dirname(image_path))
            if image_path
            else ""
        )
        unit_path = (
            os.path.join(screenshot_dir, unit["relative_dir"])
            if unit["relative_dir"]
            else screenshot_dir
        )
        asset_names = [a["name"] for a in unit["assets"]]
        asset_paths = [
            os.path.join(unit_path, a["name"]) if unit_path else a["name"]
            for a in unit["assets"]
        ]
        rebuilt = {
            "unit_id": unit["id"],
            "unit_label": unit["label"],
            "unit_path": unit_path,
            "asset_names": asset_names,
            "asset_paths": asset_paths,
            "metadata_names": [m["name"] for m in unit["metadata"]],
            "metadata_paths": [
                os.path.join(unit_path, m["name"]) if unit_path else m["name"]
                for m in unit["metadata"]
            ],
            "user_comment": draft.get("user_comment", ""),
        }
        ref_rel = unit.get("reference_asset_relative_path")
        if ref_rel:
            ref_name = os.path.basename(ref_rel)
            rebuilt["reference_asset_name"] = ref_name
            rebuilt["reference_asset_path"] = (
                os.path.join(unit_path, ref_name) if unit_path else ref_name
            )
        rebuilt["vizdiff"] = vizdiff_content
        return rebuilt

    draft["vizdiff"] = vizdiff_content
    return draft

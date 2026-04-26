"""Vizline: capture a baseline image set at a base ref into a feature worktree."""

from __future__ import annotations

import datetime
import fcntl
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import baseline_manifest
import capture_runner
import image_diff


GITIGNORE_BODY = "*\n"


class VizlineError(Exception):
    pass


@dataclass
class VizlineResult:
    skipped: bool
    skip_reason: str | None
    image_count: int
    base_sha: str
    baseline_dir: Path


def run(
    feature_worktree: Path,
    base_ref: str | None = None,
    ephemeral_root_override: Path | None = None,
    task_title: str | None = None,
    task_description: str | None = None,
    task_id: str | None = None,
    force: bool = False,
    refresh: bool = False,
) -> VizlineResult:
    feature_worktree = Path(feature_worktree).resolve()
    _require_git_worktree(feature_worktree)

    resolved_base_ref = base_ref or _default_base_ref(feature_worktree)
    base_sha = _rev_parse(feature_worktree, resolved_base_ref)
    head_sha = _rev_parse(feature_worktree, "HEAD")
    branch = _current_branch(feature_worktree)

    bugshot_dir = feature_worktree / ".bugshot"
    bugshot_dir.mkdir(exist_ok=True)
    _ensure_gitignore(bugshot_dir)

    baseline_dir = bugshot_dir / "baseline"
    if baseline_dir.exists() and not refresh:
        raise VizlineError(
            f"baseline already exists at {baseline_dir}; pass --refresh to overwrite"
        )

    lock_path = bugshot_dir / "baseline.lock"
    fd = _acquire_lock(lock_path, "vizline")
    try:
        env = _baseline_env(
            feature_worktree=feature_worktree,
            branch=branch,
            base_ref=resolved_base_ref,
            base_sha=base_sha,
            head_sha=head_sha,
            task_title=task_title,
            task_description=task_description,
            task_id=task_id,
        )

        if not force:
            should_baseline = capture_runner.locate(feature_worktree, "should-baseline")
            if should_baseline is not None:
                gate = capture_runner.run_should_baseline(should_baseline, feature_worktree, env=env)
                if gate.returncode == 1:
                    return VizlineResult(
                        skipped=True,
                        skip_reason=gate.stdout.strip() or "should-baseline returned 1",
                        image_count=0,
                        base_sha=base_sha,
                        baseline_dir=baseline_dir,
                    )
                if gate.returncode != 0:
                    raise VizlineError(
                        f"should-baseline failed (exit {gate.returncode}): {gate.stderr.strip()}"
                    )

        ephemeral_parent = _resolve_ephemeral_root(feature_worktree, ephemeral_root_override)
        ephemeral = ephemeral_parent / f"bugshot-baseline-{base_sha[:8]}-{os.getpid()}"
        try:
            _git_worktree_add(feature_worktree, ephemeral, base_sha)

            capture_in_ephemeral = capture_runner.locate(ephemeral, "capture-command")
            if capture_in_ephemeral is None:
                raise VizlineError(
                    f"capture-command does not exist at base ref {resolved_base_ref!r}. "
                    f"Land it on the base branch first, or pass "
                    f"--base-ref <ref-with-capture-command>."
                )

            ephemeral_output = ephemeral / ".bugshot-output"
            ephemeral_output.mkdir()
            cap_result = capture_runner.run_capture(
                capture_in_ephemeral, ephemeral_output, env=env,
            )
            if cap_result.returncode != 0:
                raise VizlineError(
                    f"capture-command failed (exit {cap_result.returncode}): {cap_result.stderr.strip()}"
                )

            tmp_baseline = bugshot_dir / "baseline.tmp"
            if tmp_baseline.exists():
                shutil.rmtree(tmp_baseline)
            (tmp_baseline / "images").mkdir(parents=True)

            entries: list[baseline_manifest.ImageEntry] = []
            sha_map = image_diff.discover(ephemeral_output)
            for rel_path, sha in sha_map.items():
                src = ephemeral_output / rel_path
                dst = tmp_baseline / "images" / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                entries.append(baseline_manifest.ImageEntry(path=rel_path, sha256=sha))
            entries.sort(key=lambda e: e.path)

            manifest = baseline_manifest.Manifest(
                schema_version=baseline_manifest.SCHEMA_VERSION,
                base_ref=resolved_base_ref,
                base_sha=base_sha,
                created_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                capture_command_path=str(capture_in_ephemeral.relative_to(ephemeral)),
                capture_command_sha256=image_diff.sha256_file(capture_in_ephemeral),
                images=entries,
            )
            baseline_manifest.write_manifest(tmp_baseline / "manifest.json", manifest)
            baseline_manifest.atomic_promote(tmp_baseline, baseline_dir, refresh=refresh)
            return VizlineResult(
                skipped=False,
                skip_reason=None,
                image_count=len(entries),
                base_sha=base_sha,
                baseline_dir=baseline_dir,
            )
        finally:
            _git_worktree_remove(feature_worktree, ephemeral)
    finally:
        os.close(fd)


def _ensure_gitignore(bugshot_dir: Path) -> None:
    gi = bugshot_dir / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE_BODY)


def _require_git_worktree(path: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise VizlineError(f"not a git worktree: {path}")


def _default_base_ref(feature_worktree: Path) -> str:
    for ref in ("origin/HEAD", "main", "master"):
        proc = subprocess.run(
            ["git", "-C", str(feature_worktree), "rev-parse", "--verify", ref],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return "main" if ref == "origin/HEAD" else ref
    raise VizlineError("could not resolve default base ref")


def _rev_parse(worktree: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", ref],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise VizlineError(f"could not resolve ref {ref!r}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _current_branch(worktree: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "HEAD"


def _baseline_env(*, feature_worktree, branch, base_ref, base_sha, head_sha,
                  task_title, task_description, task_id) -> dict[str, str]:
    env = {
        "BUGSHOT_REPO_ROOT": str(feature_worktree),
        "BUGSHOT_BRANCH": branch,
        "BUGSHOT_BASE_REF": base_ref,
        "BUGSHOT_BASE_SHA": base_sha,
        "BUGSHOT_HEAD_SHA": head_sha,
    }
    if task_title:
        env["BUGSHOT_TASK_TITLE"] = task_title
    if task_description:
        env["BUGSHOT_TASK_DESCRIPTION"] = task_description
    if task_id:
        env["BUGSHOT_TASK_ID"] = task_id
    return env


def _resolve_ephemeral_root(feature_worktree: Path, override: Path | None) -> Path:
    if override:
        return Path(override)
    env_override = os.environ.get("BUGSHOT_EPHEMERAL_ROOT")
    if env_override:
        return Path(env_override)
    script = capture_runner.locate(feature_worktree, "ephemeral-root")
    if script is not None:
        result = capture_runner.run_ephemeral_root(script, feature_worktree)
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip().splitlines()[0])
    return Path(tempfile.mkdtemp(prefix="bugshot-baseline-"))


def _git_worktree_add(feature_worktree: Path, ephemeral: Path, base_sha: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(feature_worktree), "worktree", "add", "--detach",
         str(ephemeral), base_sha],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise VizlineError(f"git worktree add failed: {proc.stderr.strip()}")


def _git_worktree_remove(feature_worktree: Path, ephemeral: Path) -> None:
    if not ephemeral.exists():
        return
    subprocess.run(
        ["git", "-C", str(feature_worktree), "worktree", "remove", "--force", str(ephemeral)],
        capture_output=True, text=True,
    )
    if ephemeral.exists():
        shutil.rmtree(ephemeral, ignore_errors=True)


def _acquire_lock(lock_path: Path, holder_label: str) -> int:
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise VizlineError(
            f"another {holder_label} run holds the lock at {lock_path}; "
            f"wait for it to finish or kill the holder, then retry"
        )
    return fd

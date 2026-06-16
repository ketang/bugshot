"""Wire a project worktree for Bugshot vizline/vizdiff captures."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import baseline_manifest
import image_diff


VIZ_DIR_REL = Path(".agent-plugins/bento/bugshot/viz")
GITIGNORE_BODY = "*\n"


class WireBugshotError(Exception):
    pass


@dataclass(frozen=True)
class WireBugshotResult:
    capture_command: Path
    image_count: int
    baseline_dir: Path | None


def wire(
    *,
    worktree: Path,
    capture_command: str,
    base_ref: str | None = None,
    seed_baseline: bool = False,
    refresh_baseline: bool = False,
) -> WireBugshotResult:
    worktree = Path(worktree).resolve()
    _require_git_worktree(worktree)
    normalized_command = _normalize_capture_command(capture_command)

    image_count = _validate_deterministic_capture(worktree, normalized_command)
    target = worktree / VIZ_DIR_REL / "capture-command"
    _write_capture_command(target, normalized_command)

    baseline_dir = None
    if seed_baseline:
        baseline_dir = _seed_baseline(
            worktree=worktree,
            capture_command_path=target,
            capture_command=normalized_command,
            base_ref=base_ref,
            refresh=refresh_baseline,
        )

    return WireBugshotResult(
        capture_command=target,
        image_count=image_count,
        baseline_dir=baseline_dir,
    )


def _normalize_capture_command(command: str) -> str:
    command = command.strip()
    if not command:
        raise WireBugshotError("capture command is empty")
    if "{output_dir}" in command:
        return (
            command
            .replace("'{output_dir}'", "'$BUGSHOT_CAPTURE_OUTPUT_DIR'")
            .replace('"{output_dir}"', '"$BUGSHOT_CAPTURE_OUTPUT_DIR"')
            .replace("{output_dir}", '"$BUGSHOT_CAPTURE_OUTPUT_DIR"')
        )
    return f'{command} "$BUGSHOT_CAPTURE_OUTPUT_DIR"'


def _require_git_worktree(path: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise WireBugshotError(f"not a git worktree: {path}")
    root = Path(proc.stdout.strip()).resolve()
    if root != path:
        raise WireBugshotError(f"worktree must be the git root: {path}")


def _validate_deterministic_capture(worktree: Path, command: str) -> int:
    first = _run_capture_template(worktree, command)
    second = _run_capture_template(worktree, command)
    first_paths = sorted(first)
    second_paths = sorted(second)
    if not first_paths:
        raise WireBugshotError("capture command produced no recognized images or ANSI files")
    if first_paths != second_paths:
        raise WireBugshotError(
            "capture command output paths are nondeterministic; first run produced "
            f"{first_paths}, second run produced {second_paths}"
        )
    return len(first_paths)


def _run_capture_template(worktree: Path, command: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="bugshot-wire-capture-") as tmp:
        output_dir = Path(tmp) / "output"
        output_dir.mkdir()
        result = _run_shell_capture(worktree, command, output_dir)
        if result.returncode != 0:
            raise WireBugshotError(
                f"capture command failed during validation (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        return image_diff.discover(output_dir)


def _run_shell_capture(worktree: Path, command: str, output_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BUGSHOT_CAPTURE_OUTPUT_DIR"] = str(output_dir)
    return subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )


def _write_capture_command(path: Path, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "if [ \"$#\" -ne 1 ]; then\n"
        "  echo \"usage: capture-command <output-dir>\" >&2\n"
        "  exit 2\n"
        "fi\n"
        "BUGSHOT_CAPTURE_OUTPUT_DIR=$1\n"
        "mkdir -p \"$BUGSHOT_CAPTURE_OUTPUT_DIR\"\n"
        "export BUGSHOT_CAPTURE_OUTPUT_DIR\n"
        "repo=$(git rev-parse --show-toplevel 2>/dev/null || pwd)\n"
        "cd \"$repo\"\n"
        f"exec /bin/sh -c {_shell_single_quote(command)}\n"
    )
    path.chmod(0o755)


def _seed_baseline(
    *,
    worktree: Path,
    capture_command_path: Path,
    capture_command: str,
    base_ref: str | None,
    refresh: bool,
) -> Path:
    resolved_base_ref = base_ref or _default_base_ref(worktree)
    base_sha = _rev_parse(worktree, resolved_base_ref)
    bugshot_dir = worktree / ".bugshot"
    bugshot_dir.mkdir(exist_ok=True)
    _ensure_gitignore(bugshot_dir)
    baseline_dir = bugshot_dir / "baseline"
    if baseline_dir.exists() and not refresh:
        raise WireBugshotError(
            f"baseline already exists at {baseline_dir}; pass --refresh-baseline to overwrite"
        )

    tmp_baseline = bugshot_dir / "baseline.tmp"
    worktree_output = worktree / ".bugshot-output"
    if tmp_baseline.exists():
        shutil.rmtree(tmp_baseline)
    if worktree_output.exists():
        shutil.rmtree(worktree_output)
    try:
        worktree_output.mkdir()
        result = _run_shell_capture(worktree, capture_command, worktree_output)
        if result.returncode != 0:
            raise WireBugshotError(
                f"capture command failed while seeding baseline (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        images_dir = tmp_baseline / "images"
        images_dir.mkdir(parents=True)
        entries = _copy_discovered_entries(worktree_output, images_dir)
        if not entries:
            raise WireBugshotError("capture command produced no recognized baseline files")
        manifest = baseline_manifest.Manifest(
            schema_version=baseline_manifest.SCHEMA_VERSION,
            base_ref=resolved_base_ref,
            base_sha=base_sha,
            created_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            capture_command_path=str(capture_command_path.relative_to(worktree)),
            capture_command_sha256=image_diff.sha256_file(capture_command_path),
            images=entries,
        )
        baseline_manifest.write_manifest(tmp_baseline / "manifest.json", manifest)
        baseline_manifest.atomic_promote(tmp_baseline, baseline_dir, refresh=refresh)
        return baseline_dir
    except Exception:
        if tmp_baseline.exists():
            shutil.rmtree(tmp_baseline)
        raise
    finally:
        if worktree_output.exists():
            shutil.rmtree(worktree_output)


def _copy_discovered_entries(src_dir: Path, dst_dir: Path) -> list[baseline_manifest.ImageEntry]:
    entries: list[baseline_manifest.ImageEntry] = []
    for rel_path, sha in sorted(image_diff.discover(src_dir).items()):
        src = src_dir / rel_path
        dst = dst_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entries.append(baseline_manifest.ImageEntry(path=rel_path, sha256=sha))
    return entries


def _ensure_gitignore(bugshot_dir: Path) -> None:
    gitignore = bugshot_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_BODY)


def _default_base_ref(worktree: Path) -> str:
    for ref in ("origin/HEAD", "main", "master"):
        proc = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "--verify", ref],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return "main" if ref == "origin/HEAD" else ref
    raise WireBugshotError("could not resolve default base ref")


def _rev_parse(worktree: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", ref],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise WireBugshotError(f"could not resolve ref {ref!r}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

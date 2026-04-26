"""Locate and execute project-owned capture / should-baseline / ephemeral-root scripts."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIZ_DIR_REL = ".agent-plugins/bento/bugshot/viz"


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def locate(worktree_root: Path, name: str) -> Path | None:
    """Return the executable script path for `name`, or None if absent / not executable."""
    candidate = Path(worktree_root) / VIZ_DIR_REL / name
    if not candidate.is_file():
        return None
    if not os.access(candidate, os.X_OK):
        return None
    return candidate


def _run(argv: list[str], cwd: Path, env: dict[str, str] | None) -> RunResult:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
    )
    return RunResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def run_capture(script: Path, output_dir: Path, env: dict[str, str] | None = None) -> RunResult:
    """Run `<script> <output_dir>`. CWD is the parent of output_dir."""
    return _run([str(script), str(output_dir)], cwd=Path(output_dir).parent, env=env)


def run_should_baseline(script: Path, worktree_root: Path, env: dict[str, str] | None = None) -> RunResult:
    return _run([str(script)], cwd=worktree_root, env=env)


def run_ephemeral_root(script: Path, worktree_root: Path, env: dict[str, str] | None = None) -> RunResult:
    return _run([str(script)], cwd=worktree_root, env=env)

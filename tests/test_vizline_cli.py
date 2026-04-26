import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_vizline(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "vizline_cli.py"), *args],
        capture_output=True, text=True,
    )


def test_vizline_creates_baseline(fake_git_worktree, fake_capture_command):
    result = run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    assert result.returncode == 0, result.stderr
    baseline = fake_git_worktree / ".bugshot" / "baseline"
    assert (baseline / "manifest.json").is_file()
    assert (baseline / "images" / "pages" / "login" / "desktop.png").read_text() == "BASE-LOGIN"
    assert (baseline / "images" / "pages" / "welcome.png").read_text() == "BASE-WELCOME"

    manifest = json.loads((baseline / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["base_ref"] == "main"
    assert manifest["image_count"] == 2
    paths = sorted(img["path"] for img in manifest["images"])
    assert paths == ["pages/login/desktop.png", "pages/welcome.png"]


def test_vizline_writes_gitignore_inside_dot_bugshot(fake_git_worktree, fake_capture_command):
    run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    assert (fake_git_worktree / ".bugshot" / ".gitignore").read_text() == "*\n"


def test_vizline_refuses_to_overwrite_without_refresh(fake_git_worktree, fake_capture_command):
    run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    second = run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    assert second.returncode != 0
    assert "already exists" in second.stderr.lower() or "refresh" in second.stderr.lower()


def test_vizline_refresh_overwrites(fake_git_worktree, fake_capture_command):
    run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    second = run_vizline([
        "--feature-worktree", str(fake_git_worktree),
        "--base-ref", "main",
        "--refresh",
    ])
    assert second.returncode == 0, second.stderr


def test_vizline_should_baseline_skip_exits_cleanly(fake_git_worktree, fake_capture_command):
    sb = fake_git_worktree / ".agent-plugins/bento/bugshot/viz/should-baseline"
    sb.write_text("#!/bin/sh\necho 'no relevant changes'\nexit 1\n")
    sb.chmod(0o755)
    subprocess.run(["git", "-C", str(fake_git_worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(fake_git_worktree), "commit", "-q", "-m", "+sb"], check=True)
    result = run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    assert result.returncode == 0, result.stderr
    assert "no relevant changes" in result.stdout
    assert not (fake_git_worktree / ".bugshot" / "baseline").exists()


def test_vizline_force_ignores_should_baseline_skip(fake_git_worktree, fake_capture_command):
    sb = fake_git_worktree / ".agent-plugins/bento/bugshot/viz/should-baseline"
    sb.write_text("#!/bin/sh\nexit 1\n")
    sb.chmod(0o755)
    subprocess.run(["git", "-C", str(fake_git_worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(fake_git_worktree), "commit", "-q", "-m", "+sb"], check=True)
    result = run_vizline([
        "--feature-worktree", str(fake_git_worktree),
        "--base-ref", "main",
        "--force",
    ])
    assert result.returncode == 0, result.stderr
    assert (fake_git_worktree / ".bugshot" / "baseline" / "manifest.json").is_file()


def test_vizline_capture_command_missing_at_base_errors(fake_git_worktree):
    """No capture-command was ever committed → vizline must error with guidance."""
    result = run_vizline(["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"])
    assert result.returncode != 0
    assert "capture-command" in result.stderr.lower()

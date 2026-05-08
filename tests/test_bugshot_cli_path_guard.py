"""bugshot_cli refuses to launch on paths inside a .bugshot/ working area.

This catches the failure pattern where an agent runs `bugshot
.bugshot/baseline/images/` directly instead of `vizdiff <worktree>`, which
would otherwise show unpaired images in flat-mode and silently mask the
intended diff workflow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_bugshot_baseline_tree(root: Path) -> Path:
    images = root / ".bugshot" / "baseline" / "images"
    images.mkdir(parents=True)
    (images / "a.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return images


def _run_bugshot_cli(directory: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bugshot_cli.py"), str(directory), "--local-only"],
        capture_output=True, text=True, timeout=10,
    )


def test_refuses_baseline_images_directory(tmp_path):
    images = _make_bugshot_baseline_tree(tmp_path)
    result = _run_bugshot_cli(images)
    assert result.returncode != 0
    assert ".bugshot" in result.stderr
    assert "vizdiff" in result.stderr.lower()


def test_refuses_baseline_root_directory(tmp_path):
    _make_bugshot_baseline_tree(tmp_path)
    result = _run_bugshot_cli(tmp_path / ".bugshot" / "baseline")
    assert result.returncode != 0
    assert "vizdiff" in result.stderr.lower()


def test_refuses_head_directory(tmp_path):
    head = tmp_path / ".bugshot" / "head"
    head.mkdir(parents=True)
    (head / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    result = _run_bugshot_cli(head)
    assert result.returncode != 0
    assert "vizdiff" in result.stderr.lower()


def test_refuses_top_level_dot_bugshot(tmp_path):
    bugshot = tmp_path / ".bugshot"
    bugshot.mkdir()
    (bugshot / "stray.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    result = _run_bugshot_cli(bugshot)
    assert result.returncode != 0
    assert "vizdiff" in result.stderr.lower()


def test_allows_unrelated_directory(tmp_path):
    """Sanity check: a normal screenshot directory must still work."""
    (tmp_path / "a.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    process = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "bugshot_cli.py"), str(tmp_path),
         "--local-only", "--poll-interval", "0.05"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # We just want to confirm the path guard doesn't fire — the gallery
        # url should appear, then we tear down by closing stdin to signal done.
        import time, urllib.request, json
        deadline = time.time() + 5
        url = None
        while time.time() < deadline:
            line = process.stdout.readline()
            if line.startswith("Gallery is running at "):
                url = line.strip().split("Gallery is running at ", 1)[1]
                break
            if process.poll() is not None:
                break
        assert url is not None, "gallery did not start for a non-.bugshot directory"
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/done", data=b"", method="POST",
        )).read()
        process.communicate(timeout=10)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import gallery_server  # noqa: E402


@pytest.fixture
def fake_git_worktree(tmp_path: Path) -> Path:
    """Create a real git repo with one commit so vizline can resolve refs."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"], check=True)
    (tmp_path / ".gitkeep").write_text("")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "branch", "-M", "main"], check=True)
    return tmp_path


@pytest.fixture
def fake_capture_command(fake_git_worktree: Path) -> Path:
    """Install a deterministic capture-command and commit it on main."""
    viz = fake_git_worktree / ".agent-plugins/bento/bugshot/viz"
    viz.mkdir(parents=True)
    script = viz / "capture-command"
    script.write_text(
        "#!/bin/sh\n"
        "out=\"$1\"\n"
        "mkdir -p \"$out/pages/login\"\n"
        "printf 'BASE-LOGIN' > \"$out/pages/login/desktop.png\"\n"
        "printf 'BASE-WELCOME' > \"$out/pages/welcome.png\"\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    subprocess.run(["git", "-C", str(fake_git_worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(fake_git_worktree), "commit", "-q", "-m", "add capture"], check=True)
    return script


@pytest.fixture
def screenshot_dir():
    """Create a temp directory with test images and an ANSI file."""
    d = tempfile.mkdtemp(prefix="bugshot_test_")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    for name in ["alpha.png", "beta.png", "gamma.jpg"]:
        with open(os.path.join(d, name), "wb") as f:
            f.write(png_bytes)

    with open(os.path.join(d, "delta.ansi"), "w") as f:
        f.write("\x1b[31mRed text\x1b[0m\n")

    yield d
    shutil.rmtree(d)


@pytest.fixture
def workflow_screenshot_dir():
    """Create a temp directory with fake review screenshots."""
    d = tempfile.mkdtemp(prefix="bugshot_workflow_")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    for name in ["login-clipped-button.png", "settings-overlap.png"]:
        with open(os.path.join(d, name), "wb") as f:
            f.write(png_bytes)

    with open(os.path.join(d, "terminal-output.ansi"), "w", encoding="utf-8") as f:
        f.write("\x1b[31mFailure:\x1b[0m missing border\n")

    yield d
    shutil.rmtree(d)


@pytest.fixture
def review_units_dir():
    """Create a temp review root with grouped image units and metadata."""
    d = tempfile.mkdtemp(prefix="bugshot_units_")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    login_dir = os.path.join(d, "login-button")
    settings_dir = os.path.join(d, "settings-panel")
    os.makedirs(login_dir, exist_ok=True)
    os.makedirs(settings_dir, exist_ok=True)

    for unit_dir, names in [
        (login_dir, ["reference.png", "candidate.png"]),
        (settings_dir, ["reference.png", "candidate.png"]),
    ]:
        for name in names:
            with open(os.path.join(unit_dir, name), "wb") as f:
                f.write(png_bytes)

    svg_content = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<rect width="10" height="10" fill="#111"/>'
        '<circle cx="5" cy="5" r="3" fill="#fff"/>'
        "</svg>"
    )
    for unit_dir in [login_dir, settings_dir]:
        with open(os.path.join(unit_dir, "final.svg"), "w", encoding="utf-8") as f:
            f.write(svg_content)

    with open(os.path.join(login_dir, "report.json"), "w", encoding="utf-8") as f:
        f.write(
            '{"kind":"comparison","reference":"reference.png","derived":["candidate.png"]}'
        )
    with open(os.path.join(login_dir, "bugshot-unit.json"), "w", encoding="utf-8") as f:
        f.write(
            '{"label":"Login Button Review","assets":["candidate.png","final.svg","reference.png"],"reference_asset":"reference.png","metadata":["report.json"]}'
        )

    with open(os.path.join(settings_dir, "report.json"), "w", encoding="utf-8") as f:
        f.write(
            '{"kind":"comparison","reference":"reference.png","derived":["candidate.png"],"notes":["header overlap"]}'
        )
    with open(os.path.join(settings_dir, "bugshot-unit.json"), "w", encoding="utf-8") as f:
        f.write(
            '{"label":"Settings Panel Review","assets":["reference.png","final.svg","candidate.png"],"reference_asset":"reference.png","metadata":["report.json"]}'
        )

    yield d
    shutil.rmtree(d)


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def server(screenshot_dir):
    """Start an in-process gallery server and yield it."""
    running = gallery_server.create_server(screenshot_dir)
    try:
        yield running
    finally:
        running.shutdown()
        running.cleanup_temporary_files()


@pytest.fixture
def grouped_server(review_units_dir):
    """Start an in-process gallery server for grouped review units."""
    running = gallery_server.create_server(review_units_dir)
    try:
        yield running
    finally:
        running.shutdown()
        running.cleanup_temporary_files()


@pytest.fixture
def parroty_artifacts_dir():
    """Create a small parroty-style artifacts tree for conversion tests."""
    d = tempfile.mkdtemp(prefix="bugshot_parroty_")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    unit_dir = os.path.join(d, "logo-sample")
    os.makedirs(unit_dir, exist_ok=True)
    for name in [
        "source-crop.png",
        "input-minus-svg.png",
        "svg-minus-input.png",
        "difference-overlay.png",
    ]:
        with open(os.path.join(unit_dir, name), "wb") as f:
            f.write(png_bytes)

    with open(os.path.join(unit_dir, "final.svg"), "w", encoding="utf-8") as f:
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<rect width="10" height="10" fill="#222"/></svg>'
        )

    with open(os.path.join(unit_dir, "report.json"), "w", encoding="utf-8") as f:
        f.write(
            """
{
  "input": "/tmp/logo-sample.png",
  "output": "/tmp/logo-sample.svg",
  "mode": "balanced",
  "text_mode": "auto",
  "comparison_scale": 2,
  "mask_method": "border-kmeans3-label1",
  "original_size": [243, 234],
  "trimmed_size": [209, 213],
  "crop_box": [16, 9, 225, 222],
  "warnings": [],
  "detected_text_regions": [{"text": "COLLEGE", "confidence": 0.98}],
  "selected": {
    "name": "path-text-contour-boundary-smooth",
    "backend": "boundary-smoothed-bezier-contours",
    "visual_error": 0.048742581435797294,
    "rgb_error": 0.036178890615701675,
    "alpha_error": 0.03066275641322136,
    "mask_error": 0.04011388907608329,
    "edge_error": 0.10034687817471077,
    "sdf_error": 0.04586036503314972,
    "shape_error": 0.06217411282456069,
    "topology_error": 0.2,
    "bytes": 3886,
    "elements": 1,
    "path_commands": 124,
    "cubic_segments": 85,
    "line_segments": 39,
    "text_strategy": "path-text",
    "text_elements": 0,
    "text_regions": 0
  }
}
""".strip()
        )

    with open(os.path.join(unit_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("<html><body>preview</body></html>")

    with open(os.path.join(d, "batch-report.json"), "w", encoding="utf-8") as f:
        f.write(
            """
{
  "count": 1,
  "failed": 0,
  "input": "/tmp/samples",
  "items": [
    {
      "artifacts": "/tmp/logo-sample",
      "input": "/tmp/logo-sample.png",
      "output": "/tmp/logo-sample.svg",
      "report": "/tmp/logo-sample.report.json",
      "selected": {
        "backend": "boundary-smoothed-bezier-contours",
        "bytes": 3886,
        "visual_error": 0.048742581435797294
      }
    }
  ],
  "succeeded": 1
}
""".strip()
        )

    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write("<html><body>batch preview</body></html>")

    yield d
    shutil.rmtree(d)

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import gallery_server  # noqa: E402


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
        if os.path.exists(running.db_path):
            os.unlink(running.db_path)

import json
import os
import shutil
import subprocess
import tempfile

import pytest


@pytest.fixture
def screenshot_dir():
    """Create a temp directory with test images and an ANSI file."""
    d = tempfile.mkdtemp(prefix="bugshot_test_")

    # Create minimal valid PNG files (1x1 pixel)
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

    # Create an ANSI file
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
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def server(screenshot_dir):
    """Start the gallery server and yield (url, info, process)."""
    proc = subprocess.Popen(
        ["python3", "gallery_server.py", screenshot_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    # Read startup JSON from stdout
    line = proc.stdout.readline().decode().strip()
    info = json.loads(line)
    url = info["url"]

    yield url, info, proc

    proc.terminate()
    proc.wait(timeout=5)

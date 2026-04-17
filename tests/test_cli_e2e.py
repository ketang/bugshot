import json
import subprocess
import time
import urllib.request


CLI_START_TIMEOUT_SECONDS = 5
CLI_FINISH_TIMEOUT_SECONDS = 10


def _post_json(url, payload):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return response.status, response.read()


def _start_cli(repo_root, screenshot_dir):
    return subprocess.Popen(
        [
            "python3",
            "bugshot_cli.py",
            screenshot_dir,
            "--poll-interval",
            "0.05",
        ],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_gallery_url(process):
    deadline = time.time() + CLI_START_TIMEOUT_SECONDS
    output_lines = []

    while time.time() < deadline:
        line = process.stdout.readline()
        if line:
            output_lines.append(line)
            if line.startswith("Gallery is running at "):
                url = line.strip().split("Gallery is running at ", 1)[1]
                return url, "".join(output_lines)
        elif process.poll() is not None:
            break

    raise AssertionError("CLI did not report the gallery URL")


def test_cli_emits_issue_drafts(repo_root, workflow_screenshot_dir):
    process = _start_cli(repo_root, workflow_screenshot_dir)
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(
        f"{gallery_url}/api/comments",
        {
            "image": "login-clipped-button.png",
            "body": "Submit button is clipped on the right edge.",
        },
    )
    _post_json(
        f"{gallery_url}/api/comments",
        {
            "image": "settings-overlap.png",
            "body": "The panel header overlaps the first checkbox.",
        },
    )
    _post_json(f"{gallery_url}/api/done", {})

    stdout, stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert stderr == ""
    assert "\n------------------------------------------------------------\nImage name: login-clipped-button.png" in full_output
    assert (
        f"Image path: {workflow_screenshot_dir}/login-clipped-button.png" in full_output
    )
    assert "User comment: Submit button is clipped on the right edge." in full_output
    assert "Image name: settings-overlap.png" in full_output
    assert (
        f"Image path: {workflow_screenshot_dir}/settings-overlap.png" in full_output
    )
    assert "User comment: The panel header overlaps the first checkbox." in full_output
    assert "Bugshot session complete. Produced 2 issue drafts." in full_output


def test_cli_emits_ansi_draft(repo_root, workflow_screenshot_dir):
    process = _start_cli(repo_root, workflow_screenshot_dir)
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(
        f"{gallery_url}/api/comments",
        {
            "image": "terminal-output.ansi",
            "body": "Rendered output is missing the outer border.",
        },
    )
    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert "Image name: terminal-output.ansi" in full_output
    assert f"Image path: {workflow_screenshot_dir}/terminal-output.ansi" in full_output
    assert "User comment: Rendered output is missing the outer border." in full_output
    assert "Bugshot session complete. Produced 1 issue drafts." in full_output


def test_cli_handles_empty_review(repo_root, workflow_screenshot_dir):
    process = _start_cli(repo_root, workflow_screenshot_dir)
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert "No comments were submitted." in full_output
    assert "Bugshot session complete. Produced 0 issue drafts." in full_output

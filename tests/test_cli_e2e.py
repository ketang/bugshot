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
        return response.status, json.loads(response.read())


def _start_cli(repo_root, screenshot_dir, mock_tracker_state_file, user_input):
    return subprocess.Popen(
        [
            "python3",
            "bugshot_cli.py",
            screenshot_dir,
            "--tracker",
            "mock",
            "--mock-state",
            mock_tracker_state_file,
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


def _read_tracker_state(mock_tracker_state_file):
    with open(mock_tracker_state_file, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_cli_files_issues_into_mock_tracker(
    repo_root,
    workflow_screenshot_dir,
    mock_tracker_state_file,
):
    process = _start_cli(repo_root, workflow_screenshot_dir, mock_tracker_state_file, user_input="")
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
    assert "\n------------------------------------------------------------\nIssue for login-clipped-button.png:" in full_output
    assert "Filed: #1" in full_output
    assert "Filed: #2" in full_output
    assert "Bugshot session complete. Filed 2 issues, skipped 0." in full_output

    tracker_state = _read_tracker_state(mock_tracker_state_file)
    assert len(tracker_state["issues"]) == 2
    assert tracker_state["issues"][0]["attachments"] == ["login-clipped-button.png"]
    assert tracker_state["issues"][1]["attachments"] == ["settings-overlap.png"]


def test_cli_reports_duplicate_and_still_files_issue(
    repo_root,
    workflow_screenshot_dir,
    mock_tracker_state_file,
):
    with open(mock_tracker_state_file, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "supports_attachments": True,
                "issues": [
                    {
                        "id": 7,
                        "title": "Login Clipped Button: Submit button is clipped",
                        "body": "Existing issue for the login screen.",
                        "attachments": [],
                    }
                ],
            },
            handle,
        )

    process = _start_cli(repo_root, workflow_screenshot_dir, mock_tracker_state_file, user_input="")
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(
        f"{gallery_url}/api/comments",
        {
            "image": "login-clipped-button.png",
            "body": "Submit button is clipped on the right edge.",
        },
    )
    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert "Found potential duplicates for login-clipped-button.png:" in full_output
    assert "Filed: #8 - Login Clipped Button: Submit button is clipped on the right edge." in full_output
    assert "Bugshot session complete. Filed 1 issues, skipped 0." in full_output

    tracker_state = _read_tracker_state(mock_tracker_state_file)
    assert len(tracker_state["issues"]) == 2


def test_cli_reports_attachment_fallback(
    repo_root,
    workflow_screenshot_dir,
    mock_tracker_state_file,
):
    with open(mock_tracker_state_file, "w", encoding="utf-8") as handle:
        json.dump({"supports_attachments": False, "issues": []}, handle)

    process = _start_cli(repo_root, workflow_screenshot_dir, mock_tracker_state_file, user_input="")
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
    assert "Note: Could not attach screenshot to #1" in full_output
    assert "Bugshot session complete. Filed 1 issues, skipped 0." in full_output

    tracker_state = _read_tracker_state(mock_tracker_state_file)
    assert len(tracker_state["issues"]) == 1
    assert tracker_state["issues"][0]["attachments"] == []


def test_cli_handles_empty_review(
    repo_root,
    workflow_screenshot_dir,
    mock_tracker_state_file,
):
    process = _start_cli(
        repo_root,
        workflow_screenshot_dir,
        mock_tracker_state_file,
        user_input="",
    )
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert "No comments were submitted." in full_output
    assert "Bugshot session complete. Filed 0 issues, skipped 0." in full_output

    tracker_state = _read_tracker_state(mock_tracker_state_file)
    assert tracker_state["issues"] == []

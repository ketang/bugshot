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


def _start_cli(repo_root, screenshot_dir, extra_args=None):
    args = [
        "python3",
        "bugshot_cli.py",
        screenshot_dir,
        "--poll-interval",
        "0.05",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.Popen(
        args,
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_gallery_url(process, source="stdout"):
    deadline = time.time() + CLI_START_TIMEOUT_SECONDS
    output_lines = []
    stream = process.stdout if source == "stdout" else process.stderr

    while time.time() < deadline:
        line = stream.readline()
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
            "unit_id": "login-clipped-button.png",
            "body": "Submit button is clipped on the right edge.",
        },
    )
    _post_json(
        f"{gallery_url}/api/comments",
        {
            "unit_id": "settings-overlap.png",
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
            "unit_id": "terminal-output.ansi",
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


def test_cli_json_output(repo_root, workflow_screenshot_dir):
    process = _start_cli(repo_root, workflow_screenshot_dir, extra_args=["--json"])
    gallery_url, _initial_stderr = _read_gallery_url(process, source="stderr")

    _post_json(
        f"{gallery_url}/api/comments",
        {
            "unit_id": "login-clipped-button.png",
            "body": "Submit button is clipped on the right edge.",
        },
    )
    _post_json(
        f"{gallery_url}/api/comments",
        {
            "unit_id": "settings-overlap.png",
            "body": "The panel header overlaps the first checkbox.",
        },
    )
    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)

    assert process.returncode == 0
    payload = json.loads(stdout.strip())
    assert payload["draft_count"] == 2
    assert payload["drafts"] == [
        {
            "image_name": "login-clipped-button.png",
            "image_path": f"{workflow_screenshot_dir}/login-clipped-button.png",
            "user_comment": "Submit button is clipped on the right edge.",
        },
        {
            "image_name": "settings-overlap.png",
            "image_path": f"{workflow_screenshot_dir}/settings-overlap.png",
            "user_comment": "The panel header overlaps the first checkbox.",
        },
    ]


def test_cli_emits_grouped_unit_drafts(repo_root, review_units_dir):
    process = _start_cli(repo_root, review_units_dir, extra_args=["--json"])
    gallery_url, _initial_stderr = _read_gallery_url(process, source="stderr")

    _post_json(
        f"{gallery_url}/api/comments",
        {
            "unit_id": "login-button",
            "body": "The candidate image loses the right edge of the button.",
        },
    )
    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)

    assert process.returncode == 0
    payload = json.loads(stdout.strip())
    assert payload["draft_count"] == 1
    assert payload["drafts"] == [
        {
            "unit_id": "login-button",
            "unit_label": "Login Button Review",
            "unit_path": f"{review_units_dir}/login-button",
            "asset_names": ["candidate.png", "final.svg", "reference.png"],
            "asset_paths": [
                f"{review_units_dir}/login-button/candidate.png",
                f"{review_units_dir}/login-button/final.svg",
                f"{review_units_dir}/login-button/reference.png",
            ],
            "metadata_names": ["report.json"],
            "metadata_paths": [f"{review_units_dir}/login-button/report.json"],
            "reference_asset_name": "reference.png",
            "reference_asset_path": f"{review_units_dir}/login-button/reference.png",
            "user_comment": "The candidate image loses the right edge of the button.",
        }
    ]


def test_cli_handles_empty_review(repo_root, workflow_screenshot_dir):
    process = _start_cli(repo_root, workflow_screenshot_dir)
    gallery_url, initial_output = _read_gallery_url(process)

    _post_json(f"{gallery_url}/api/done", {})

    stdout, _stderr = process.communicate("", timeout=CLI_FINISH_TIMEOUT_SECONDS)
    full_output = initial_output + stdout

    assert process.returncode == 0
    assert "No comments were submitted." in full_output
    assert "Bugshot session complete. Produced 0 issue drafts." in full_output

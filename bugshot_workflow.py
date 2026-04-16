"""Standalone bugshot review workflow."""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass

from bugshot_tracker import AttachmentNotSupportedError, IssueTracker

DEFAULT_BIND_ADDRESS = "127.0.0.1"
DEFAULT_BROWSER_OPEN_ENABLED = False
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
HTTP_SUCCESS_STATUS = 200
TITLE_SEPARATOR = ": "
TITLE_MAXIMUM_LENGTH = 72
TITLE_SUFFIX_LENGTH = 3
ISSUE_DIVIDER = "------------------------------------------------------------"


class ShellIO:
    """Shell-facing input and output adapter."""

    def __init__(self, input_stream=None, output_stream=None, error_stream=None):
        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout
        self.error_stream = error_stream or sys.stderr

    def write(self, message: str = "") -> None:
        self.output_stream.write(f"{message}\n")
        self.output_stream.flush()

    def write_error(self, message: str) -> None:
        self.error_stream.write(f"{message}\n")
        self.error_stream.flush()

    def prompt(self, message: str) -> str:
        self.output_stream.write(message)
        self.output_stream.flush()
        response = self.input_stream.readline()
        if response == "":
            return ""
        return response.strip()

    def confirm(self, message: str, default: bool = True) -> bool:
        response = self.prompt(message).strip().lower()
        if not response:
            return default
        return response not in NEGATIVE_RESPONSES


@dataclass
class ReviewSummary:
    filed_count: int
    skipped_count: int


def run_review_session(
    screenshot_dir: str,
    tracker: IssueTracker,
    io: ShellIO,
    bind_address: str = DEFAULT_BIND_ADDRESS,
    open_browser: bool = DEFAULT_BROWSER_OPEN_ENABLED,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> int:
    server_process = _start_server(screenshot_dir, bind_address)
    try:
        startup_info = _read_startup(server_process)
        gallery_url = startup_info["url"]

        io.write(f"Gallery is running at {gallery_url}")
        if open_browser:
            browser_opened = webbrowser.open(gallery_url)
            if not browser_opened:
                io.write(f"Open this URL in your browser: {gallery_url}")

        io.write(
            "Bugshot gallery is open. Review the screenshots, type comments on any issues "
            "you see, then click \"Done Reviewing\" when finished."
        )

        completion_reason = _wait_for_completion(gallery_url, io, poll_interval_seconds)
        if completion_reason in {"timeout", "closed"}:
            should_continue = io.confirm(
                f'Gallery session ended with reason "{completion_reason}". '
                "Continue processing comments? [Y/n]: ",
                default=True,
            )
            if not should_continue:
                io.write("Review cancelled before filing issues.")
                return 0

        comments = _fetch_comments(gallery_url)
        summary = _process_comments(comments, screenshot_dir, tracker, io)
        io.write(
            f"Bugshot session complete. Filed {summary.filed_count} issues, "
            f"skipped {summary.skipped_count}."
        )
        return 0
    finally:
        _stop_server(server_process)


def _start_server(screenshot_dir: str, bind_address: str) -> subprocess.Popen:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    command = [
        "python3",
        os.path.join(script_dir, "gallery_server.py"),
        screenshot_dir,
        "--bind",
        bind_address,
    ]
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=script_dir,
    )


def _read_startup(server_process: subprocess.Popen) -> dict[str, object]:
    startup_line = server_process.stdout.readline().strip()
    if startup_line:
        payload = json.loads(startup_line)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload

    stderr_output = server_process.stderr.read().strip()
    if server_process.poll() is not None:
        raise RuntimeError(stderr_output or "gallery server exited before startup")
    raise RuntimeError("gallery server did not emit startup JSON")


def _wait_for_completion(gallery_url: str, io: ShellIO, poll_interval_seconds: float) -> str | None:
    status_url = f"{gallery_url}/api/status"
    while True:
        status = _get_json(status_url)
        if status["done"]:
            return status["reason"]
        time.sleep(poll_interval_seconds)
        if _terminal_input_is_ready(io):
            user_line = io.prompt("")
            if user_line.strip().lower() == "done":
                return "terminal"


def _terminal_input_is_ready(io: ShellIO) -> bool:
    if not hasattr(io.input_stream, "isatty") or not io.input_stream.isatty():
        return False
    if not hasattr(io.input_stream, "fileno"):
        return False

    ready_streams, _, _ = select.select([io.input_stream], [], [], 0)
    return bool(ready_streams)


def _fetch_comments(gallery_url: str) -> list[dict[str, object]]:
    return _get_json(f"{gallery_url}/api/comments")


def _process_comments(
    comments: list[dict[str, object]],
    screenshot_dir: str,
    tracker: IssueTracker,
    io: ShellIO,
) -> ReviewSummary:
    if not comments:
        io.write("No comments were submitted.")
        return ReviewSummary(filed_count=0, skipped_count=0)

    filed_count = 0
    skipped_count = 0

    for comment in comments:
        title = _compose_title(comment)
        body = _compose_body(comment)
        screenshot_path = os.path.join(screenshot_dir, comment["image"])
        duplicate_matches = tracker.search_issues(f"{title}\n{body}")

        if duplicate_matches:
            io.write(f"Found potential duplicates for {comment['image']}:")
            for match in duplicate_matches:
                io.write(f"- #{match.id}: {match.title}")

        io.write("")
        io.write(ISSUE_DIVIDER)
        io.write(f"Issue for {comment['image']}:")
        io.write(title)
        io.write(body)
        io.write("")

        issue = tracker.create_issue(title, body)
        try:
            tracker.attach_file(issue.id, screenshot_path)
        except AttachmentNotSupportedError:
            io.write(
                f"Note: Could not attach screenshot to #{issue.id} "
                "(attachment not supported by tracker)."
            )
        io.write(f"Filed: #{issue.id} - {issue.title}")
        filed_count += 1

    return ReviewSummary(filed_count=filed_count, skipped_count=skipped_count)


def _compose_title(comment: dict[str, object]) -> str:
    image_stem = os.path.splitext(comment["image"])[0].replace("-", " ")
    prefix = image_stem.strip().title()
    suffix = comment["body"].strip()
    candidate = f"{prefix}{TITLE_SEPARATOR}{suffix}"
    if len(candidate) <= TITLE_MAXIMUM_LENGTH:
        return candidate
    truncated_length = TITLE_MAXIMUM_LENGTH - TITLE_SUFFIX_LENGTH
    return f"{candidate[:truncated_length]}..."


def _compose_body(comment: dict[str, object]) -> str:
    return "\n".join(
        [
            "## Current Behavior",
            comment["body"],
            "",
            "## Screenshot Description",
            f"Screenshot under review: {comment['image']}",
            "",
            "## Additional Context",
            f"- Screenshot: {comment['image']}",
            f'- User comment: "{comment["body"]}"',
        ]
    )


def _get_json(url: str) -> dict[str, object] | list[dict[str, object]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request) as response:
            if response.status != HTTP_SUCCESS_STATUS:
                raise RuntimeError(f"unexpected status code: {response.status}")
            return json.loads(response.read())
    except urllib.error.URLError as error:
        raise RuntimeError(f"failed to reach {url}: {error}") from error


def _stop_server(server_process: subprocess.Popen) -> None:
    if server_process.poll() is not None:
        return
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait(timeout=5)

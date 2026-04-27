"""Standalone bugshot review workflow."""

from __future__ import annotations

import datetime
import json
import os
import select
import sqlite3
import sys
import time
import webbrowser
from dataclasses import dataclass

import gallery_server

DEFAULT_BIND_ADDRESS = "0.0.0.0"
LOOPBACK_BIND_ADDRESS = "127.0.0.1"
DEFAULT_BROWSER_OPEN_ENABLED = False
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
ISSUE_DIVIDER = "------------------------------------------------------------"
NEGATIVE_RESPONSES = {"n", "no"}


class ShellIO:
    """Shell-facing input and output adapter."""

    def __init__(
        self,
        input_stream=None,
        output_stream=None,
        error_stream=None,
        json_output: bool = False,
    ):
        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout
        self.error_stream = error_stream or sys.stderr
        self.json_output = json_output

    def write(self, message: str = "") -> None:
        stream = self.error_stream if self.json_output else self.output_stream
        stream.write(f"{message}\n")
        stream.flush()

    def write_json(self, payload: object) -> None:
        self.output_stream.write(json.dumps(payload) + "\n")
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
    draft_count: int
    drafts: list[dict[str, object]]


def run_review_session(
    screenshot_dir: str,
    io: ShellIO,
    bind_address: str = DEFAULT_BIND_ADDRESS,
    open_browser: bool = DEFAULT_BROWSER_OPEN_ENABLED,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    json_output: bool = False,
) -> int:
    try:
        server = gallery_server.create_server(screenshot_dir, bind_address=bind_address)
    except ValueError as error:
        io.write_error(str(error))
        return 1

    try:
        io.write(f"Gallery is running at {server.url}")
        if open_browser:
            browser_opened = webbrowser.open(server.url)
            if not browser_opened:
                io.write(f"Open this URL in your browser: {server.url}")

        io.write(
            "Bugshot gallery is open. Review the screenshots, type comments on any issues "
            "you see, then click \"Done Reviewing\" when finished."
        )

        _wait_for_completion(server.db_path, io, poll_interval_seconds)
        comments = _fetch_comments(server.db_path)
        summary = _process_comments(
            comments,
            server.units,
            os.path.abspath(screenshot_dir),
            io,
            json_output=json_output,
        )
        io.write(f"Bugshot session complete. Produced {summary.draft_count} issue drafts.")
        if json_output:
            io.write_json({
                "draft_count": summary.draft_count,
                "drafts": summary.drafts,
            })
        return 0
    finally:
        server.shutdown()
        if os.path.exists(server.db_path):
            os.unlink(server.db_path)


def _wait_for_completion(db_path: str, io: ShellIO, poll_interval_seconds: float) -> str | None:
    while True:
        done, reason = _read_session_state(db_path)
        if done:
            return reason
        time.sleep(poll_interval_seconds)
        if _terminal_input_is_ready(io):
            user_line = io.prompt("")
            if user_line.strip().lower() == "done":
                return "terminal"


def _read_session_state(db_path: str) -> tuple[bool, str | None]:
    """Read session state directly from SQLite, applying heartbeat timeout."""
    conn = sqlite3.connect(db_path)
    try:
        rows = {
            key: value
            for key, value in conn.execute("SELECT key, value FROM session").fetchall()
        }
    finally:
        conn.close()

    done = rows.get("done") == "true"
    reason = rows.get("done_reason") or None

    if not done:
        last_heartbeat = rows.get("last_heartbeat")
        if last_heartbeat:
            try:
                last_hb = datetime.datetime.fromisoformat(last_heartbeat)
                elapsed = (datetime.datetime.now() - last_hb).total_seconds()
                if elapsed > gallery_server.HEARTBEAT_TIMEOUT_SECONDS:
                    return True, "timeout"
            except (ValueError, TypeError):
                pass

    return done, reason


def _terminal_input_is_ready(io: ShellIO) -> bool:
    if not hasattr(io.input_stream, "isatty") or not io.input_stream.isatty():
        return False
    if not hasattr(io.input_stream, "fileno"):
        return False

    ready_streams, _, _ = select.select([io.input_stream], [], [], 0)
    return bool(ready_streams)


def _fetch_comments(db_path: str) -> list[dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, unit_id, body, region, created_at FROM comments ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        item = dict(row)
        item["region"] = json.loads(item["region"]) if item["region"] else None
        items.append(item)
    return items


def _format_region(region: dict[str, object]) -> str:
    region_type = region.get("type")
    if region_type == "rect":
        return (
            f"rect (x={region['x']:.2f}, y={region['y']:.2f}, "
            f"w={region['w']:.2f}, h={region['h']:.2f})"
        )
    if region_type == "ellipse":
        return (
            f"ellipse (cx={region['cx']:.2f}, cy={region['cy']:.2f}, "
            f"rx={region['rx']:.2f}, ry={region['ry']:.2f})"
        )
    if region_type == "path":
        points = region.get("points", [])
        return f"path ({len(points)} points)"
    return str(region)


def _process_comments(
    comments: list[dict[str, object]],
    units: list[dict[str, object]],
    screenshot_dir: str,
    io: ShellIO,
    json_output: bool = False,
) -> ReviewSummary:
    if not comments:
        io.write("No comments were submitted.")
        return ReviewSummary(draft_count=0, drafts=[])

    units_by_id = {unit["id"]: unit for unit in units}
    drafts: list[dict[str, object]] = []

    for comment in comments:
        unit_id = comment["unit_id"]
        unit = units_by_id.get(unit_id)
        if unit is None:
            continue

        user_comment = comment["body"]
        region = comment.get("region")
        unit_path = (
            os.path.join(screenshot_dir, unit["relative_dir"])
            if unit["relative_dir"]
            else screenshot_dir
        )
        assets = [
            {
                "name": asset["name"],
                "path": os.path.join(screenshot_dir, asset["relative_path"]),
                "type": asset["type"],
            }
            for asset in unit["assets"]
        ]
        metadata = [
            {
                "name": item["name"],
                "path": os.path.join(screenshot_dir, item["relative_path"]),
            }
            for item in unit["metadata"]
        ]
        reference_asset_relative_path = unit.get("reference_asset_relative_path")
        reference_asset = None
        if reference_asset_relative_path:
            reference_asset = next(
                (
                    asset
                    for asset in assets
                    if asset["path"] == os.path.join(screenshot_dir, reference_asset_relative_path)
                ),
                None,
            )

        if len(assets) == 1:
            draft = {
                "image_name": assets[0]["name"],
                "image_path": assets[0]["path"],
                "user_comment": user_comment,
                "region": region,
            }
        else:
            draft = {
                "unit_id": unit["id"],
                "unit_label": unit["label"],
                "unit_path": unit_path,
                "asset_names": [asset["name"] for asset in assets],
                "asset_paths": [asset["path"] for asset in assets],
                "metadata_names": [item["name"] for item in metadata],
                "metadata_paths": [item["path"] for item in metadata],
                "user_comment": user_comment,
            }
            if reference_asset is not None:
                draft["reference_asset_name"] = reference_asset["name"]
                draft["reference_asset_path"] = reference_asset["path"]

        drafts.append(draft)

        if not json_output:
            io.write("")
            io.write(ISSUE_DIVIDER)
            if len(assets) == 1:
                io.write(f"Image name: {assets[0]['name']}")
                io.write(f"Image path: {assets[0]['path']}")
                if region is not None:
                    io.write(f"Region: {_format_region(region)}")
            else:
                io.write(f"Unit id: {unit['id']}")
                io.write(f"Unit path: {unit_path}")
                io.write(f"Assets: {', '.join(draft['asset_names'])}")
                if reference_asset is not None:
                    io.write(f"Reference asset: {reference_asset['name']}")
                if draft["metadata_names"]:
                    io.write(f"Metadata: {', '.join(draft['metadata_names'])}")
            io.write(f"User comment: {user_comment}")
            io.write("")

    return ReviewSummary(draft_count=len(drafts), drafts=drafts)

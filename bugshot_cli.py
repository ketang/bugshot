#!/usr/bin/env python3

"""Command-line entrypoint for standalone bugshot review sessions."""

from __future__ import annotations

import argparse
import os

from bugshot_tracker import MockIssueTracker
from bugshot_workflow import (
    DEFAULT_BIND_ADDRESS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    ShellIO,
    run_review_session,
)

SUPPORTED_TRACKERS = ("mock",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bugshot standalone CLI")
    parser.add_argument("directory", help="Path to screenshot directory")
    parser.add_argument(
        "--tracker",
        choices=SUPPORTED_TRACKERS,
        default="mock",
        help="Tracker backend to use",
    )
    parser.add_argument(
        "--mock-state",
        help="Path to the mock tracker JSON state file",
    )
    parser.add_argument(
        "--bind",
        default=DEFAULT_BIND_ADDRESS,
        help=f"Address to bind to (default: {DEFAULT_BIND_ADDRESS})",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds for review completion",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the gallery URL in the default browser",
    )
    return parser.parse_args()


def build_tracker(args: argparse.Namespace) -> MockIssueTracker:
    if args.tracker != "mock":
        raise ValueError(f"unsupported tracker: {args.tracker}")
    if not args.mock_state:
        raise ValueError("--mock-state is required when --tracker=mock")
    return MockIssueTracker(args.mock_state)


def main() -> int:
    args = parse_args()
    io = ShellIO()

    if not os.path.isdir(args.directory):
        io.write_error(f"Not a directory: {args.directory}")
        return 2

    try:
        tracker = build_tracker(args)
        return run_review_session(
            screenshot_dir=os.path.abspath(args.directory),
            tracker=tracker,
            io=io,
            bind_address=args.bind,
            open_browser=args.open_browser,
            poll_interval_seconds=args.poll_interval,
        )
    except Exception as error:  # pragma: no cover - top-level CLI handling
        io.write_error(f"Bugshot CLI failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

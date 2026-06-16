#!/usr/bin/env python3
"""Vizdiff CLI: capture HEAD, diff against baseline, open the review gallery."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import bugshot_workflow
import vizdiff_workflow

LOOPBACK_BIND_ADDRESS = "127.0.0.1"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bugshot vizdiff review session")
    parser.add_argument("feature_worktree", type=Path, nargs="?")
    parser.add_argument("--manifest", type=Path,
                        help="Open a prebuilt non-interactive vizdiff manifest")
    parser.add_argument("--check-review-manifest", type=Path,
                        help="Exit 0 only when a vizdiff review manifest is complete")
    parser.add_argument("--base", default=None,
                        help="Base ref name (used for the no-baseline error message)")
    parser.add_argument("--base-dir", default=None, type=Path,
                        help="Bypass baseline lookup and use this directory as the base side")
    parser.add_argument("--head-only", action="store_true",
                        help="Capture HEAD only, no comparison (degraded plain-bugshot mode)")
    bind_group = parser.add_mutually_exclusive_group()
    bind_group.add_argument("--bind")
    bind_group.add_argument("--local-only", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="JSON output instead of markdown")
    return parser.parse_args(argv)


def bind_selector_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "select-bind-address",
        script_dir / "skills" / "bugshot" / "select-bind-address",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("select-bind-address helper is missing")


def select_bind_address() -> str:
    result = subprocess.run(
        [str(bind_selector_path())],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def resolve_bind_address(args: argparse.Namespace) -> str:
    if args.local_only:
        return LOOPBACK_BIND_ADDRESS
    if args.bind is not None:
        return args.bind
    return select_bind_address()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.check_review_manifest is not None:
        ok, errors = vizdiff_workflow.check_review_manifest(args.check_review_manifest)
        for error in errors:
            print(error, file=sys.stderr)
        return 0 if ok else 1

    bind_address = resolve_bind_address(args)
    if args.manifest is None and args.feature_worktree is None:
        print("feature_worktree is required unless --manifest is supplied", file=sys.stderr)
        return 2
    try:
        if args.manifest is not None:
            review_root = vizdiff_workflow.build_review_root_from_manifest(args.manifest)
            review_manifest_path = vizdiff_workflow.default_review_manifest_path(
                input_manifest=args.manifest
            )
        else:
            review_root = vizdiff_workflow.build_review_root(
                feature_worktree=args.feature_worktree,
                base_ref=args.base,
                base_dir=args.base_dir,
                head_only=args.head_only,
            )
            review_manifest_path = vizdiff_workflow.default_review_manifest_path(
                feature_worktree=args.feature_worktree
            )
    except vizdiff_workflow.VizdiffError as error:
        print(str(error), file=sys.stderr)
        return 1

    io = bugshot_workflow.ShellIO(json_output=args.json)
    def on_session_complete(server, done_reason):
        try:
            written_path = vizdiff_workflow.write_review_manifest(
                review_manifest_path,
                server,
                done_reason=done_reason,
            )
        except OSError as error:
            raise vizdiff_workflow.VizdiffError(
                f"Failed to write vizdiff review manifest: {error}"
            ) from error
        io.write(f"Vizdiff review manifest written to {written_path}")

    try:
        return bugshot_workflow.run_review_session(
            screenshot_dir=str(review_root),
            io=io,
            bind_address=bind_address,
            json_output=args.json,
            on_session_complete=on_session_complete,
        )
    except vizdiff_workflow.VizdiffError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

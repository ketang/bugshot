#!/usr/bin/env python3
"""Vizline CLI: capture a baseline image set into a feature worktree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import vizline_workflow


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a bugshot baseline")
    parser.add_argument("--feature-worktree", required=True, type=Path,
                        help="Path to the feature worktree (target of the baseline)")
    parser.add_argument("--base-ref", default=None,
                        help="Base ref to capture from (default: origin/HEAD or main or master)")
    parser.add_argument("--ephemeral-root", default=None, type=Path,
                        help="Directory in which to place the ephemeral base-ref worktree")
    parser.add_argument("--task-title", default=None)
    parser.add_argument("--task-description", default=None)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--force", action="store_true",
                        help="Ignore should-baseline; always create the baseline")
    parser.add_argument("--refresh", action="store_true",
                        help="Overwrite an existing baseline")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        result = vizline_workflow.run(
            feature_worktree=args.feature_worktree,
            base_ref=args.base_ref,
            ephemeral_root_override=args.ephemeral_root,
            task_title=args.task_title,
            task_description=args.task_description,
            task_id=args.task_id,
            force=args.force,
            refresh=args.refresh,
        )
    except vizline_workflow.VizlineError as error:
        print(str(error), file=sys.stderr)
        return 1

    if result.skipped:
        print(result.skip_reason)
    else:
        print(
            f"Baseline written: {result.image_count} images, "
            f"base={result.base_sha}, dir={result.baseline_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

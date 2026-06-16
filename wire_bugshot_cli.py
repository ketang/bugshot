#!/usr/bin/env python3
"""Wire a worktree with a Bugshot viz capture command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import wire_bugshot_workflow


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create .agent-plugins/bento/bugshot/viz/capture-command"
    )
    parser.add_argument(
        "--worktree",
        default=Path.cwd(),
        type=Path,
        help="Git worktree root to wire (default: current directory)",
    )
    parser.add_argument(
        "--capture-command",
        required=True,
        help=(
            "Screenshot command template. Use {output_dir} where the output "
            "directory belongs; if omitted, the output directory is appended."
        ),
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Base ref recorded in an optional seeded baseline",
    )
    parser.add_argument(
        "--seed-baseline",
        action="store_true",
        help="After writing capture-command, capture an initial .bugshot/baseline",
    )
    parser.add_argument(
        "--refresh-baseline",
        action="store_true",
        help="Overwrite an existing baseline when used with --seed-baseline",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print validation and output details",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.refresh_baseline and not args.seed_baseline:
        print("--refresh-baseline requires --seed-baseline", file=sys.stderr)
        return 1
    try:
        result = wire_bugshot_workflow.wire(
            worktree=args.worktree,
            capture_command=args.capture_command,
            base_ref=args.base_ref,
            seed_baseline=args.seed_baseline,
            refresh_baseline=args.refresh_baseline,
        )
    except wire_bugshot_workflow.WireBugshotError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"Wrote capture-command: {result.capture_command}")
    if args.verbose:
        print(f"Validated deterministic capture paths: {result.image_count}")
    if result.baseline_dir is not None:
        print(f"Seeded baseline: {result.baseline_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

---
name: vizdiff
description: TRIGGER at handoff or before landing when `.bugshot/baseline/manifest.json` exists in the worktree. Captures HEAD, diffs against vizline's baseline, opens a review gallery, emits issue drafts. Run vizline first if no baseline exists.
arguments:
  - name: feature_worktree
    description: Path to the feature worktree to diff
    required: true
---

# Vizdiff — Bugshot Visual Diff Skill

Capture HEAD screenshots, classify against `.bugshot/baseline/`, assemble a
grouped review root under `.bugshot/review-root/`, open the bugshot gallery in
diff mode, and emit issue drafts on stdout. Alternatively, consume a
prewritten non-interactive manifest with `--manifest`.

## When to use

At handoff time or before landing, when feature edits may have changed
rendered output. Vizdiff requires a baseline produced upstream by `vizline`.

Skip when:

- No baseline exists at `.bugshot/baseline/manifest.json` (run `bento:vizline`
  first, or pass `--head-only` for plain HEAD capture without comparison).
- The branch is verifiably non-rendering — backend-only changes with no UI,
  template, or design-system impact.

## Prerequisites

- The feature worktree must be a git worktree.
- `.agent-plugins/bento/bugshot/viz/capture-command` must exist and be executable.
- A baseline at `.bugshot/baseline/` (created via `bento:vizline`) is required
  unless `--head-only` or `--base-dir` is passed.
- For manifest mode, none of the capture prerequisites are required. The
  manifest contract is documented in
  `docs/specs/2026-05-01-vizdiff-manifest.md`.

## Startup

1. Validate `{{feature_worktree}}` is a git worktree.
2. Find the vizdiff installation directory.
3. Run the CLI with `--json`:

   ```bash
   python3 {{vizdiff_dir}}/vizdiff_cli.py --json {{feature_worktree}}
   ```

   If the user supplies a manifest instead of a feature worktree, run:

   ```bash
   python3 {{vizdiff_dir}}/vizdiff_cli.py --json --manifest {{manifest_path}}
   ```

4. Read the first line of the CLI's stderr — `Gallery is running at <url>`.
   Print the URL to the user. The gallery binds to `0.0.0.0` by default; pass
   `--local-only` for loopback-only.
5. Wait for the CLI to exit; it handles polling and browser lifecycle.
6. Parse the trailing JSON line on stdout: `{"draft_count": N, "drafts": [...]}`.

## CLI flags

- positional `feature_worktree` — required.
- positional `feature_worktree` — required unless `--manifest` is supplied.
- `--manifest <path>` — consume a non-interactive vizdiff manifest and open the
  prebuilt review in the gallery.
- `--base <ref>` — informational; used only in the no-baseline error message.
- `--base-dir <path>` — bypass the baseline lookup; use this directory as the
  base side.
- `--head-only` — skip comparison; treat every HEAD image as `added`.
- `--bind <addr>` — default `0.0.0.0`.
- `--local-only` — shortcut for `--bind 127.0.0.1`.
- `--json` — JSON drafts on stdout instead of markdown.

## Process drafts

Each draft is a grouped-unit draft with these fields:

- `unit_id`, `unit_label`, `unit_path`
- `asset_names`, `asset_paths`
- `metadata_names`, `metadata_paths`
- `reference_asset_name`, `reference_asset_path` (the base image, when present)
- `user_comment`

To recover the vizdiff-specific metadata for a draft, read
`<unit_path>/bugshot-metadata.json`. Its `schema` field is `bugshot.vizdiff/v1`
and it carries:

- `classification` — one of `changed`, `added`, `removed`, `unchanged`.
- `relative_path` — the original capture-command relative path.
- `base_asset`, `head_asset` — which asset filenames play which role.
- `base_ref`, `base_sha`, `head_sha`.
- `base_sha256`, `head_sha256`.
- Manifest mode also preserves `branch`, `changeset`, and `expected_change`
  when present.

## Sharp edges

- Re-running vizdiff overwrites `.bugshot/head/` and `.bugshot/review-root/`,
  invalidating asset paths in older drafts. Consume drafts before re-running.
- Stale baseline (`base_sha` mismatch with current `git rev-parse <ref>`) is a
  hard error. Fix it via `bento:vizline --feature-worktree <path> --refresh`.
- vizdiff holds `.bugshot/head.lock` via `fcntl.flock`. Concurrent vizdiff runs
  on the same worktree refuse with a clear message.

---
name: vizdiff
description: TRIGGER at handoff or before landing when `.bugshot/baseline/manifest.json` exists in the worktree. Captures HEAD, diffs against vizline's baseline, opens a review gallery, emits issue drafts. Run vizline first if no baseline exists.
arguments:
  - name: feature_worktree
    description: Path to the feature worktree to diff in default mode; omit when using --manifest
    required: false
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

- No baseline exists at `.bugshot/baseline/manifest.json` (run `bugshot:vizline`
  first at branch start. If work has already begun, run
  `bugshot:vizline --feature-worktree <path> --from-base-ref` instead. Pass
  `--head-only` only for plain HEAD capture without comparison).
- The branch is verifiably non-rendering — backend-only changes with no UI,
  template, or design-system impact.

## Prerequisites

- In default (non-manifest) mode, `feature_worktree` is required and must be a
  git worktree.
- In default (non-manifest) mode,
  `.agent-plugins/bento/bugshot/viz/capture-command` must exist and be
  executable.
- In default (non-manifest) mode, a baseline at `.bugshot/baseline/` (created
  via `bugshot:vizline`) is required unless `--head-only` or `--base-dir` is
  passed.
- Default vizline baselines are branch-start captures from a clean feature
  worktree. When vizdiff finds no baseline after feature edits already exist,
  create one with vizline's explicit `--from-base-ref` mode so the baseline
  comes from the base ref, not from modified HEAD.
- For manifest mode, none of the capture prerequisites are required. The
  manifest contract is documented at the plugin root:
  `{{vizdiff_dir}}/docs/specs/2026-05-01-vizdiff-manifest.md`.

## Startup

1. Choose invocation mode. If `--manifest {{manifest_path}}` is supplied, do
   not require or validate `{{feature_worktree}}`. Otherwise, require
   `{{feature_worktree}}` and validate it is a git worktree.
2. Find the vizdiff installation directory.
3. Run the CLI with `--json`:

   ```bash
   python3 {{vizdiff_dir}}/vizdiff_cli.py --json {{feature_worktree}}
   ```

   If the user supplies a manifest instead of a feature worktree, run:

   ```bash
   python3 {{vizdiff_dir}}/vizdiff_cli.py --json --manifest {{manifest_path}}
   ```

4. Scan the CLI's stderr for `Gallery is running at <url>` and print that URL
   to the user. By default, the CLI selects the bind address with the same
   `select-bind-address` helper used by the bugshot skill; that helper writes
   its explanatory bind-selection message to stderr before the gallery URL.
   Pass `--bind <addr>` or `--local-only` only when the user explicitly
   requests a bind mode.
5. Wait for the CLI to exit; it handles polling and browser lifecycle.
6. Parse the trailing JSON line on stdout: `{"draft_count": N, "drafts": [...]}`.
7. Treat the review-completion manifest as the machine-checkable proof that the
   visual diff was actually reviewed:

   ```bash
   python3 {{vizdiff_dir}}/vizdiff_cli.py --check-review-manifest {{feature_worktree}}/.bugshot/review-manifest.json
   ```

   For `--manifest {{manifest_path}}` mode, the review-completion manifest is
   written as `review-manifest.json` beside `{{manifest_path}}`.

## CLI flags

- positional `feature_worktree` — required unless `--manifest` is supplied.
- `--manifest <path>` — consume a non-interactive vizdiff manifest and open the
  prebuilt review in the gallery.
- `--base <ref>` — informational; used only in the no-baseline error message.
- `--base-dir <path>` — bypass the baseline lookup; use this directory as the
  base side.
- `--head-only` — skip comparison; treat every HEAD image as `added`.
- `--bind <addr>` — explicit bind-address override.
- `--local-only` — explicit loopback-only override.
- `--json` — JSON drafts on stdout instead of markdown.
- `--check-review-manifest <path>` — validate a vizdiff review-completion
  manifest and exit 0 only when every expected review unit has a matching
  `seen: true` entry. This mode does not require `feature_worktree`.

## Review-completion manifest

Vizdiff writes `review-manifest.json` after the Bugshot gallery session ends.
The file is written for explicit Done, browser close, and timeout completion.
Browser-close or partial review still produces the file, but the checker fails
conservatively when any expected unit is missing or not seen.

Completeness is:

- manifest exists and uses schema `bugshot.vizdiff-review/v1`
- `unit_count` matches the number of `expected_units`
- every expected unit id has exactly one entry in `units`
- every entry for an expected unit has `seen: true`

`commented` is informational only. It records whether a unit produced at least
one Bugshot comment, but it is not required for the completion marker.

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
  invalidating asset paths in older drafts and replacing
  `.bugshot/review-manifest.json`. Consume drafts and check the manifest before
  re-running.
- Stale baseline (`base_sha` mismatch with current `git rev-parse <ref>`) is a
  hard error. Fix it via `bugshot:vizline --feature-worktree <path> --refresh`.
- vizdiff holds `.bugshot/head.lock` via `fcntl.flock`. Concurrent vizdiff runs
  on the same worktree refuse with a clear message.

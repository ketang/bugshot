# Vizdiff Manifest Contract

## Purpose

This document defines the non-interactive caller contract for vizdiff. A caller
that has already captured base and head visual artifacts can write this manifest
and hand it to a human reviewer. The reviewer can later run:

```bash
python3 vizdiff_cli.py --manifest /path/to/manifest.json
```

The command opens the normal Bugshot gallery with one review unit per manifest
surface. It does not run a capture command, inspect a specific orchestrator, or
require a live automation process.

## End-To-End Flow

1. Capture base images and head images with any workflow.
2. Write `manifest.json` next to those artifacts.
3. Hand the manifest path to the reviewer through the caller's normal channel.
4. The reviewer runs `vizdiff_cli.py --manifest <path>`.
5. The reviewer comments in the gallery and clicks "Done Reviewing".
6. The caller or reviewer routes the emitted drafts through their normal issue
   or review channel.

## Manifest Shape

Example:

```json
{
  "schema": "bugshot.vizdiff-manifest/v1",
  "branch": "feature/login-polish",
  "base_ref": "main",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "changeset": {
    "url": "https://example.test/pull/123",
    "commits": ["bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
  },
  "surfaces": [
    {
      "name": "Login desktop",
      "base_png": "base/login-desktop.png",
      "head_png": "head/login-desktop.png",
      "expected_change": "Only the primary button color should change."
    }
  ]
}
```

## Top-Level Fields

- `schema`: optional string. When present, must be
  `bugshot.vizdiff-manifest/v1`.
- `branch`: required string naming the branch or changeset under review.
- `base_ref`: optional string naming the human-readable base ref.
- `base_sha`: required string identifying the base commit or source revision.
- `head_sha`: required string identifying the head commit or source revision.
- `changeset`: optional object with caller-defined pointers such as a URL or
  commit list. Bugshot preserves it as metadata and does not interpret it.
- `surfaces`: required non-empty list of surface objects.

## Surface Fields

- `name`: required string shown as the Bugshot unit label.
- `base_png`: optional path to the base-side artifact.
- `head_png`: optional path to the head-side artifact.
- `expected_change`: optional one-line string written by the caller for the
  human reviewer.

`base` and `head` are accepted aliases for `base_png` and `head_png`.

Paths may be absolute or relative to the manifest file's directory. At least one
of `base_png` or `head_png` must be present. Supported file extensions match the
vizdiff review asset set: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, and
`.ansi`.

## Gallery Semantics

Vizdiff converts the manifest into a grouped Bugshot review root next to the
manifest at `review-root/`. Existing contents of that generated directory are
replaced.

Each surface becomes one review unit:

- base artifact copied as `reference.<ext>` when present
- head artifact copied as `candidate.<ext>` when present
- `bugshot-metadata.json` containing the manifest context
- `bugshot-unit.json` preserving the label, asset order, and reference asset

The metadata schema is `bugshot.vizdiff/v1`. It includes:

- `classification`: `changed`, `unchanged`, `added`, or `removed`
- `surface` and `relative_path`: the manifest surface name
- `expected_change`: the caller-provided summary, when present
- `branch`, `base_ref`, `base_sha`, `head_sha`
- `changeset`: the optional object from the manifest
- `base_asset`, `head_asset`, `base_sha256`, `head_sha256`

## Compatibility

The existing interactive vizdiff flow is unchanged. Running `vizdiff_cli.py`
with a feature worktree still captures HEAD, compares it with the baseline, and
opens the generated review root. `--manifest` is a separate input mode for
callers that already produced review artifacts.

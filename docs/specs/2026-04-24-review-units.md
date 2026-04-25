# Bugshot Review Unit Spec

## Purpose

This document defines the filesystem contract for inputs that Bugshot can
review. Upstream producers should target this spec when generating artifacts for
Bugshot.

This is the current implemented contract. It documents what Bugshot accepts
today.

## Terminology

- `review root`: The top-level filesystem path passed to `bugshot_cli.py` or
  `gallery_server.py`.
- `review unit`: The smallest reviewable item in Bugshot. One comment is always
  attached to exactly one review unit.
- `gallery`: The browser UI used to review units. Use this term for the web
  surface, not for the on-disk input format.

Recommended usage:

- Say "review root" for the larger input collection.
- Say "review unit" for the subunit.
- Say "gallery" for the Bugshot web UI.

## Supported Input Layouts

Bugshot accepts exactly two input layouts.

### 1. Flat Review Root

In flat mode, each recognized top-level file becomes its own single-asset review
unit.

Example:

```text
review-root/
  login-clipped-button.png
  settings-overlap.png
  terminal-output.ansi
```

This produces three review units with ids:

- `login-clipped-button.png`
- `settings-overlap.png`
- `terminal-output.ansi`

### 2. Grouped Review Root

In grouped mode, each child directory of the review root becomes one review
unit if that child directory contains at least one recognized asset file.

Example:

```text
review-root/
  login-button/
    reference.png
    candidate.png
    report.json
  settings-panel/
    reference.png
    candidate.png
    report.json
```

This produces two review units with ids:

- `login-button`
- `settings-panel`

## Mode Selection

Mode selection is automatic and mutually exclusive:

- If the review root contains any recognized top-level asset files, Bugshot
  uses flat mode.
- Otherwise, Bugshot scans child directories and uses grouped mode.

Important implication:

- Mixed roots are not supported. If the top level contains recognized asset
  files, Bugshot does not also scan child directories for grouped units.

## Recognized Files

### Review Assets

Files with these extensions are review assets:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.webp`
- `.svg`
- `.ansi`

### Metadata Files

In grouped mode, `.json` files inside a unit directory are treated as metadata
attachments and displayed in the detail view.

Bugshot currently treats metadata JSON as opaque:

- there is no required metadata schema
- Bugshot does not interpret fields semantically beyond pretty-printing JSON

Reserved filename:

- `bugshot-unit.json` is the optional per-unit manifest file. It is not treated
  as display metadata.

## Unit Manifest

Grouped units may include an optional `bugshot-unit.json` manifest to make the
contract explicit and avoid relying on filename heuristics.

Example:

```json
{
  "label": "Login Button Review",
  "assets": ["reference.png", "final.svg", "difference-overlay.png"],
  "reference_asset": "reference.png",
  "metadata": ["bugshot-metadata.json"]
}
```

### Manifest Fields

- `label`: optional string shown in the Bugshot UI and emitted in grouped-unit
  drafts as `unit_label`
- `assets`: optional non-empty list of direct child asset filenames
- `reference_asset`: optional direct child asset filename naming the canonical
  reference asset for the unit
- `metadata`: optional non-empty list of direct child metadata filenames

### Manifest Semantics

- If `assets` is present, Bugshot uses that exact asset order.
- If `reference_asset` is present, Bugshot treats that exact asset as the
  unit's canonical reference asset.
- If `metadata` is present, Bugshot uses that exact metadata list and order.
- If `label` is absent, the unit label defaults to the directory name.
- If `assets` is absent, Bugshot falls back to heuristic asset discovery.
- If `reference_asset` is absent, Bugshot does not guess.
- If `metadata` is absent, Bugshot falls back to discovering `.json` files other
  than `bugshot-unit.json`.
- Unit id remains the directory name even when `label` is present.

### Manifest Validation

Manifest entries must be direct child filenames, not nested relative paths.

Invalid manifests are fatal for that review root. Bugshot raises an error when:

- the manifest is not valid JSON
- the manifest root is not a JSON object
- `label` is not a string
- `reference_asset` is present but is not a string direct child asset filename
- `assets` or `metadata` is present but is not a non-empty list of strings
- a listed file does not exist
- a listed file has the wrong extension for its field
- `reference_asset` does not name one of the unit's assets

## Review Unit Rules

### Flat Mode

- Unit id = filename
- Unit label = filename
- Unit path = review root
- Asset count = 1
- Metadata count = 0

### Grouped Mode

- Unit id = child directory name
- Unit label = `bugshot-unit.json.label` when present, otherwise child directory name
- Unit path = `<review-root>/<unit-id>`
- Assets = either:
  - `bugshot-unit.json.assets` in manifest order, or
  - recognized asset files directly inside that child directory
- Metadata = either:
  - `bugshot-unit.json.metadata` in manifest order, or
  - `.json` files directly inside that child directory other than `bugshot-unit.json`
- Canonical reference asset = `bugshot-unit.json.reference_asset` when present,
  otherwise unspecified

### Depth Rules

Bugshot currently supports only one grouping level below the review root:

- supported: `review-root/unit-a/reference.png`
- not supported: `review-root/batch-1/unit-a/reference.png`

Nested subdirectories inside a review unit are ignored for discovery.

## Asset Ordering

When no manifest asset list is provided, Bugshot renders grouped-unit assets in
a stable heuristic order:

1. Filenames whose stem is one of:
   - `reference`
   - `source`
   - `original`
   - `input`
   - `baseline`
2. All remaining assets, sorted alphabetically by filename

This is only a fallback heuristic. Producers should prefer an explicit manifest
when asset order matters.

## Recommended Metadata Summary

Bugshot treats metadata as opaque JSON, but producers should prefer a concise
human-facing summary file over dumping only a large raw report into the detail
view.

Recommended filename:

- `bugshot-metadata.json`

Recommended use:

- include the concise summary in `bugshot-unit.json.metadata`
- keep large raw producer reports on disk for traceability, but do not
  necessarily list them in manifest metadata

Recommended fields:

```json
{
  "schema": "bugshot.logo2svg-metadata/v1",
  "input_name": "logo-sample.png",
  "output_name": "logo-sample.svg",
  "mode": "balanced",
  "text_mode": "auto",
  "trimmed_width": 209,
  "trimmed_height": 213,
  "warnings": [],
  "selected_backend": "boundary-smoothed-bezier-contours",
  "selected_visual_error": 0.0487,
  "selected_bytes": 3886,
  "raw_report_file": "report.json"
}
```

This is a recommended summary shape, not a required schema for all producers.

Producer guidance:

- Prefer a flat top-level object so Bugshot can render metadata as a compact
  table.
- If a field naturally needs structured data, keep that structure in the value
  for that one field rather than nesting the whole document.
- If you have a canonical reference image, name it `reference.png` when
  possible.
- Keep the number of assets per unit small enough to review holistically.

## Comment and Draft Semantics

Bugshot stores comments per review unit, not per individual asset.

Consequences:

- In flat mode, a comment still effectively applies to one file because the unit
  contains one asset.
- In grouped mode, a comment applies to the whole unit and should describe the
  issue holistically across the asset set and metadata.

Draft output shape:

- Flat mode preserves the legacy output:
  - `image_name`
  - `image_path`
  - `user_comment`
- Grouped mode emits unit-oriented output:
  - `unit_id`
  - `unit_label`
  - `unit_path`
  - `asset_names`
  - `asset_paths`
  - `metadata_names`
  - `metadata_paths`
  - `reference_asset_name` when the producer explicitly provides a canonical
    reference asset in `bugshot-unit.json.reference_asset`
  - `reference_asset_path` when the producer explicitly provides a canonical
    reference asset in `bugshot-unit.json.reference_asset`
  - `user_comment`

## Compliance Checklist For Producers

A producer is Bugshot-compliant today if it does all of the following:

- Emits either a flat review root or a grouped review root
- Uses only supported asset extensions for reviewable images/text renders
- Keeps grouped units to one directory level beneath the review root
- Uses `.json` for optional metadata files
- Avoids mixing top-level assets with grouped child directories in the same
  review root

Recommended, but not required:

- Include `bugshot-unit.json` for grouped units so labels and asset ordering are
  explicit
- Include `bugshot-unit.json.reference_asset` whenever a grouped unit has a
  canonical reference asset and downstream tooling should know which asset it is
- Include `bugshot-metadata.json` or an equivalent concise metadata summary
  instead of surfacing only a large raw report
- Keep unit directory names stable and human-readable, since they become unit ids
- Keep metadata concise enough to be legible in the detail page

## Example: Recommended Grouped Layout

```text
review-root/
  checkout-button/
    bugshot-unit.json
    reference.png
    final.svg
    diff-overlay.png
    bugshot-metadata.json
    report.json
  settings-header/
    bugshot-unit.json
    reference.png
    final.svg
    bugshot-metadata.json
    report.json
```

## Unsupported Or Future Work

These are not part of the current contract:

- mixed flat-and-grouped review roots
- nested grouped hierarchies
- semantic metadata fields understood directly by Bugshot
- explicit asset roles beyond filename ordering and selection

If Bugshot later expands the manifest format, it should be documented as a new
spec revision rather than changing this contract silently.

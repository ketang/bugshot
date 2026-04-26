# Bugshot

Ephemeral gallery for visual bug review and issue filing across either single
screenshots or grouped review units made of related images plus metadata.

## Quick Start

```bash
python3 bugshot_cli.py /path/to/review-root
```

Runs an in-process gallery server, prints the URL, waits for the user to
review, then emits issue drafts. Add `--json` for a structured single-line
output instead of markdown.

The review root can be either:

- a flat directory of recognized screenshot files
- a directory of child review units, where each child directory contains one or
  more recognized screenshots plus optional JSON metadata files

Grouped review units can include `bugshot-unit.json` to make labels, asset
order, and metadata selection explicit. The full contract lives in
`docs/specs/2026-04-24-review-units.md`.

Recognized review assets now include native `.svg`, which Bugshot serves
directly without rasterization.

Binds to `0.0.0.0` by default (reachable from other hosts). Pass `--local-only` for loopback only.

Input-format details for upstream producers live in
`docs/specs/2026-04-24-review-units.md`.

## Project Structure

- `bugshot_cli.py` — CLI entry point; orchestrates a review session.
- `bugshot_workflow.py` — review loop: starts the gallery in-process, polls SQLite for completion, emits drafts.
- `gallery_server.py` — HTTP server + `create_server()` factory. Runs standalone or in a background thread inside the workflow.
- `ansi_render.py` — ANSI escape sequence to HTML converter.
- `static/`, `templates/` — CSS/JS and HTML served to the browser.
- `skills/bugshot/SKILL.md` — Claude Code skill definition (agent-facing contract). Hand-edited; copied alongside the python files into the plugin distribution by `scripts/build-plugin`.
- `docs/specs/2026-04-24-review-units.md` — filesystem contract for Bugshot review roots and review units.
- `tests/` — pytest unit tests and `e2e_test.sh`.

## Running Tests

```bash
python -m pytest tests/ -v
bash tests/e2e_test.sh
```

## Key Design Decisions

- Zero external runtime dependencies — stdlib only.
- Gallery server runs in the same process as the workflow (background thread); only the browser talks to it over HTTP.
- SQLite for ephemeral session state (temp file, cleaned up on exit). The workflow reads the session and comments tables directly — there are no GET endpoints.
- ANSI rendering is server-side (`ansi_render.py` converts to styled HTML).
- Comments stored per review unit, one comment = one potential issue draft.
- Flat screenshot mode is preserved by treating each top-level image as a
  single-asset review unit keyed by its filename.
- Session lifecycle: heartbeat + `beforeunload` beacon + Done button + optional `done` keyword on stdin.

## Documentation Sync Rules

`skills/bugshot/SKILL.md` is the contract consumed by an agent invoking bugshot. It must stay aligned with the code:

- Changing `bugshot_cli.py` flags, stdout/stderr output format, or exit behavior → update `SKILL.md`.
- Changing recognized extensions in `gallery_server.py` → update `SKILL.md`.
- Changing the JSON draft schema produced by `bugshot_workflow.py` → update `SKILL.md`.
- Changing the default bind address or adding bind-related flags → update `SKILL.md` and the Quick Start section above.

Make these updates in the same commit as the code change.

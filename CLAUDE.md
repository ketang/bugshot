# Bugshot

Ephemeral screenshot gallery for visual bug review and issue filing.

## Quick Start

```bash
python3 bugshot_cli.py /path/to/screenshots
```

Runs an in-process gallery server, prints the URL, waits for the user to review, then emits issue drafts. Add `--json` for a structured single-line output instead of markdown.

Binds to `0.0.0.0` by default (reachable from other hosts). Pass `--local-only` for loopback only.

## Project Structure

- `bugshot_cli.py` — CLI entry point; orchestrates a single review session.
- `bugshot_workflow.py` — review loop: starts the gallery in-process, polls SQLite for completion, emits drafts.
- `gallery_server.py` — HTTP server + `create_server()` factory. Runs standalone or in a background thread inside the workflow.
- `ansi_render.py` — ANSI escape sequence to HTML converter.
- `static/`, `templates/` — CSS/JS and HTML served to the browser.
- `SKILL.md` — Claude Code skill definition (agent-facing contract).
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
- Comments stored per-image, one comment = one potential issue draft.
- Session lifecycle: heartbeat + `beforeunload` beacon + Done button + optional `done` keyword on stdin.

## Documentation Sync Rules

`SKILL.md` is the contract consumed by an agent invoking bugshot. It must stay aligned with the code:

- Changing `bugshot_cli.py` flags, stdout/stderr output format, or exit behavior → update `SKILL.md`.
- Changing recognized extensions in `gallery_server.py` → update `SKILL.md`.
- Changing the JSON draft schema produced by `bugshot_workflow.py` → update `SKILL.md`.
- Changing the default bind address or adding bind-related flags → update `SKILL.md` and the Quick Start section above.

Make these updates in the same commit as the code change.

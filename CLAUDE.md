# Bugshot

Ephemeral screenshot gallery for visual bug review and issue filing.

## Quick Start

```bash
python3 gallery_server.py /path/to/screenshots
```

The server prints startup JSON to stdout and serves the gallery on a random local port.

## Project Structure

- `gallery_server.py` — HTTP server (Python 3 stdlib, zero external deps)
- `ansi_render.py` — ANSI escape sequence to HTML converter
- `static/` — CSS and JS served to the browser
- `templates/` — HTML templates for index and detail views
- `SKILL.md` — Claude Code skill definition
- `tests/` — pytest unit tests and e2e bash script

## Running Tests

```bash
python -m pytest tests/ -v
bash tests/e2e_test.sh
```

## Key Design Decisions

- Zero external runtime dependencies — stdlib only
- SQLite for ephemeral session state (temp file, cleaned up on exit)
- ANSI rendering is server-side (ansi_render.py converts to styled HTML)
- Comments stored per-image, one comment = one potential issue
- Session lifecycle: heartbeat + beforeunload + done button

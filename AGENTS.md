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

Non-interactive visual-diff handoff manifests for `vizdiff --manifest` are
documented in `docs/specs/2026-05-01-vizdiff-manifest.md`.

## Project Structure

- `bugshot_cli.py` — CLI entry point; orchestrates a review session.
- `bugshot_workflow.py` — review loop: starts the gallery in-process, polls SQLite for completion, emits drafts.
- `gallery_server.py` — HTTP server + `create_server()` factory. Runs standalone or in a background thread inside the workflow.
- `ansi_render.py` — ANSI escape sequence to HTML converter.
- `static/`, `templates/` — CSS, compiled JS, TypeScript source, and HTML served to the browser.
- `static/gallery.ts` — source of truth for the gallery frontend; compiled to
  `static/gallery.js` by `npm run build:frontend` and `scripts/build-plugin`.
- `skills/bugshot/SKILL.md` — canonical, agent-neutral skill definition. Hand-edited; copied alongside the python files into source skill directories by `scripts/build-plugin`.
- `skills/bugshot/overlays/` — agent-specific skill guidance appended to generated Claude and Codex payloads.
- `.claude/skills/`, `.codex-plugin/skills/` — generated agent-specific skill payloads. Do not hand-edit generated files.
- `docs/specs/2026-04-24-review-units.md` — filesystem contract for Bugshot review roots and review units.
- `tests/` — pytest unit tests and `e2e_test.sh`.

## Running Tests

```bash
python -m pytest tests/ -v
npm run build:frontend
npm run test:frontend
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

`skills/bugshot/SKILL.md` is the canonical contract consumed by an agent invoking bugshot. Agent-specific behavior belongs in `skills/bugshot/overlays/`, and `scripts/build-plugin` emits the Claude and Codex payloads. These files must stay aligned with the code:

- Changing `bugshot_cli.py` flags, stdout/stderr output format, or exit behavior → update `SKILL.md`.
- Changing recognized extensions in `gallery_server.py` → update `SKILL.md`.
- Changing the JSON draft schema produced by `bugshot_workflow.py` → update `SKILL.md`.
- Changing the default bind address or adding bind-related flags → update `SKILL.md` and the Quick Start section above.
- Changing agent-specific invocation behavior → update the matching overlay and rebuild generated skill payloads.

Make these updates in the same commit as the code change.

<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->

# Vizdiff & Vizline Design Spec

## Overview

Two new skills in the bugshot plugin family for visual regression review:

- **`bento:vizline`** — captures a *baseline* set of screenshots at a base ref and stores it inside a feature worktree.
- **`bento:vizdiff`** — captures HEAD screenshots, compares against the baseline, and opens a diff-aware gallery for human review. Comments (with optional spatial regions) flow out as issue drafts in the same shape bugshot already uses.

The existing `bento:bugshot` skill is unchanged in purpose, but its draft schema and SQLite comments table gain a nullable `region` field shared with vizdiff.

A target project opts into the family by shipping a small contract under `.agent-plugins/bento/bugshot/viz/`:

```
.agent-plugins/bento/bugshot/viz/
  capture-command       # required — produces screenshots
  should-baseline       # optional — policy gate, vizline only
  ephemeral-root        # optional — overrides ephemeral worktree placement, vizline only
```

## Actors

- **Human user**: reviews diffs in the browser, draws optional regions, types comments, signals done.
- **Vizdiff / vizline skills**: agent-side orchestrators in Claude Code (or any compatible agent).
- **Gallery server**: existing Python 3 HTTP server, extended with diff-mode routes and a regions-aware comment schema.
- **Capture-command**: project-owned executable; produces screenshots into a directory the skill provides.
- **Launching skill** (e.g., `bento:launch-work`, the user's own equivalent, or none): optionally invokes vizline when starting a feature workspace; not required by vizline.

## System Architecture

```
+---------------------+       feature-worktree path        +---------------------+
|   Launching skill   |---- triggers (optional) ---------->|       vizline       |
|   (launch-work etc) |                                     |    (CLI + skill)    |
+---------------------+                                     +----------+----------+
                                                                       |
                                                                       | git worktree add (ephemeral, base ref)
                                                                       | run capture-command
                                                                       | manifest + images
                                                                       v
                                                            <feature-worktree>/.bugshot/baseline/
                                                                       |
                                                                       v
+---------------------+                                     +----------+----------+
|        Agent        |---- invokes ---------------------->|       vizdiff       |
|    (Claude Code)    |                                     |    (CLI + skill)    |
+---------------------+                                     +----------+----------+
                                                                       |
                                                                       | run capture-command in CWD
                                                                       | classify (SHA), pair, diff
                                                                       | spin up gallery server
                                                                       v
                                                            +---------------------+
                                                            |   Gallery server    |
                                                            |  (existing, ext'd)  |
                                                            +----------+----------+
                                                                       |
                                                                       v
                                                            Browser: review + comments + regions
                                                                       |
                                                                       v
                                                            JSON drafts on stdout
```

Code-level layout in the bugshot repo:

```
bugshot/
  bugshot_cli.py             # existing
  bugshot_workflow.py        # existing
  vizdiff_cli.py             # new
  vizdiff_workflow.py        # new
  vizline_cli.py             # new
  baseline_manifest.py       # shared — read/write/validate manifest
  capture_runner.py          # shared — locate + execute capture-command
  image_diff.py              # shared — pair, classify, SHA helpers
  gallery_server.py          # existing — extended with diff-mode handlers
  templates/, static/        # extended with diff views and region-drawing JS
  skills/
    bugshot/SKILL.md         # moved from repo-root /SKILL.md — canonical source
    vizdiff/SKILL.md         # new
    vizline/SKILL.md         # new
```

#### SKILL.md layout migration

Today the canonical bugshot SKILL.md lives at the repo root, and `scripts/build-plugin` copies it into `skills/bugshot/SKILL.md` as a build artifact. This work moves the canonical file under `skills/bugshot/SKILL.md` so all three skills share a symmetric layout. Implications:

- Update `scripts/build-plugin` so the source is `skills/bugshot/SKILL.md` (and the per-file copy of `static/`, `templates/`, and the python files goes into the same skills directory it already targets, but keyed off the new source location).
- Confirm `.codex-plugin/plugin.json`'s `"skills": "."` entry still resolves correctly. If Codex requires SKILL.md at the path named by `"skills"`, change the value to `"./skills/bugshot"`. If Codex doesn't accept that, keep the root file as a copy emitted by the build script, with the canonical edit-target still under `skills/bugshot/`.
- Delete the now-redundant root `/SKILL.md` only after the build script change lands and both plugin manifests still produce a working artifact.

Browser-side Canvas handles all pixel-level diff rendering (overlay, standalone diff image). Python stays stdlib-only — `hashlib` is sufficient on the server side because changed-vs-unchanged classification is SHA-based.

## Project Contract: `.agent-plugins/bento/bugshot/viz/`

Three files at this path; one required, two optional. All are project-owned and project-authored.

### `capture-command` (required)

Executable. Produces screenshots.

- **Invocation**: `<path>/capture-command <output-dir>`. CWD is the worktree the skill is operating in.
- **Output**: writes images (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) into `<output-dir>` under any directory layout the project chooses.
- **Exit**: 0 on success, non-zero on failure (skill surfaces stderr verbatim).
- **No skill-side timeout.** Capture can take as long as it takes; the project owns its own runtime budget.
- **Determinism requirement**: relative paths must be stable across runs in the same working tree. Random IDs, timestamps, or hostnames in paths break pairing.

### `should-baseline` (optional, vizline only)

Policy gate. Determines whether vizline runs `capture-command` at all.

- **Invocation**: `<path>/should-baseline`. CWD is the feature worktree root.
- **Env vars set by vizline**:

| Var | Value | Always set? |
|---|---|---|
| `BUGSHOT_REPO_ROOT` | abs path of feature worktree | yes |
| `BUGSHOT_BRANCH` | current branch | yes |
| `BUGSHOT_BASE_REF` | resolved base ref name | yes |
| `BUGSHOT_BASE_SHA` | full SHA of resolved base | yes |
| `BUGSHOT_HEAD_SHA` | full SHA of HEAD | yes |
| `BUGSHOT_TASK_TITLE` | passed-through from launching skill | optional |
| `BUGSHOT_TASK_DESCRIPTION` | passed-through from launching skill | optional |
| `BUGSHOT_TASK_ID` | passed-through (issue/ticket id) | optional |

- **Exit codes**: `0` → create baseline, `1` → skip cleanly, anything else → error.
- **Stdout**: optional one-line reason; vizline echoes to its caller.
- **Stderr**: diagnostic; surfaced on error.
- **No skill-side timeout** (project owns runtime). Soft norm documented in SKILL.md: should typically return well under a second.
- **Absent file** = "always create baseline" (default behavior).

### `ephemeral-root` (optional, vizline only)

Locates the worktree-placement convention the target project wants vizline to use for its throwaway base-ref worktree.

- **Invocation**: `<path>/ephemeral-root`. CWD is the feature worktree root.
- **Stdout**: a single line, an absolute path under which vizline will create a directory like `bugshot-baseline-<short-sha>-<pid>/`.
- **Exit 0** required for the path to be honored.
- **Absent file** = vizline falls back to `tempfile.mkdtemp(prefix="bugshot-baseline-")`. This is safe because the worktree is ephemeral and skill-owned (created → captured → removed within one invocation); the prohibition on placing user-facing feature worktrees in `/tmp` does not apply here.

## Skill: `bento:vizline`

### CLI surface

```
vizline_cli.py \
  --feature-worktree <path>            # required
  [--base-ref <ref>]                    # default: merge-base with main
  [--ephemeral-root <path>]             # override discovery cascade
  [--task-title <str>]                  # forwarded as BUGSHOT_TASK_TITLE
  [--task-description <str>]            # forwarded as BUGSHOT_TASK_DESCRIPTION
  [--task-id <str>]                     # forwarded as BUGSHOT_TASK_ID
  [--force]                             # ignore should-baseline; always create
  [--refresh]                           # overwrite an existing baseline
```

### Workflow

1. Validate `--feature-worktree` exists and is a git worktree. Resolve `--base-ref` to a SHA via `git rev-parse` inside the feature worktree.
2. If `<feature-worktree>/.agent-plugins/bento/bugshot/viz/should-baseline` exists and `--force` was not passed, run it with the env-var contract above. Exit 1 → skip cleanly with reason on stdout. Other non-zero → error.
3. Determine ephemeral root via discovery cascade:
   1. `--ephemeral-root <path>` flag
   2. `BUGSHOT_EPHEMERAL_ROOT` env var
   3. `<feature-worktree>/.agent-plugins/bento/bugshot/viz/ephemeral-root` script output
   4. `tempfile.mkdtemp(prefix="bugshot-baseline-")`
4. Acquire lock at `<feature-worktree>/.bugshot/baseline.lock` via `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on an open-and-held file descriptor; refuse to start if held. The kernel releases the lock automatically when the process exits for any reason (clean exit, exception, SIGKILL, OOM, host crash) — no stale-lock cleanup needed. The lock file itself is left on disk; it's the file descriptor that holds the lock, not the file's existence.
5. `git worktree add --detach <ephemeral>/<short-sha>-<pid> <base-sha>` from inside the feature worktree.
6. Locate `capture-command` in the ephemeral worktree at the same `.agent-plugins/bento/bugshot/viz/` path. Missing → error: *"capture-command does not exist at base ref `<ref>`. Land it on the base branch first, or pass `--base <ref-with-capture-command>`."*
7. `mkdir <ephemeral>/.bugshot-output/`. Run `capture-command <output-dir>` with stdout/stderr streamed through to vizline's caller.
8. Capture-command non-zero exit → error, surface stderr, clean up ephemeral worktree before exiting.
9. Compute SHA-256 for each captured image; build `manifest.json`.
10. Atomic write: assemble in `<feature-worktree>/.bugshot/baseline.tmp/`, then `os.rename()` to `.bugshot/baseline/`. `--refresh` removes the existing target *only after* `.tmp/` is fully written.
11. `git worktree remove --force <ephemeral>` (cleanup runs on every exit path, success or failure).
12. Release lock; print summary: `Baseline written: 42 images, base=<sha>, dir=<feature-worktree>/.bugshot/baseline/`.

### Errors — single rule

**No partial baselines.** Any failure deletes both the ephemeral worktree and `.bugshot/baseline.tmp/` before exit, leaving the feature worktree as it was. The `.bugshot/baseline/` directory only ever appears as a complete, manifest-validated set.

### Trigger model

Vizline ships with **no enforced trigger.** The launching skill (or the agent operating without one) decides when to invoke vizline based on task context.

The `should-baseline` script is the project's own per-task gate; it complements the launching skill's gate without replacing it. Two-stage gating is fine.

The bugshot SKILL.md explicitly documents this so launching-skill authors and agents both know they own the trigger.

## Skill: `bento:vizdiff`

### CLI surface

```
vizdiff_cli.py \
  <feature-worktree>                    # positional, required
  [--base <ref>]                        # only meaningful for the "no baseline" error message
  [--base-dir <path>]                   # bypass baseline lookup; use this directory directly
  [--head-only]                         # capture HEAD only, no comparison (degraded plain-bugshot mode)
  [--bind <addr>]                       # default 0.0.0.0
  [--local-only]                        # shortcut for --bind 127.0.0.1
  [--json]                              # JSON output instead of markdown
```

Vizdiff intentionally does **not** support `--refresh-baseline` or `--no-baseline`. Refreshing is vizline's job; the equivalent of "no baseline" is `--base-dir <path>` or `--head-only`.

### Workflow

1. Resolve baseline source:
   - If `--base-dir <path>` given, use that directory as the base side.
   - Else if `--head-only`, skip comparison entirely (gallery behaves like plain bugshot on HEAD images).
   - Else require `<feature-worktree>/.bugshot/baseline/` to exist with a valid manifest. Validate `manifest.base_sha == git rev-parse <resolved-base-ref>`.
   - On any of (no baseline, stale baseline) → exit non-zero with the guidance message:

     ```
     No baseline found at .bugshot/baseline/ (or stale: captured at <old-sha>, base now <new-sha>).
       Create one via:        bento:vizline --feature-worktree <path>
       Or supply manually:    --base-dir <path-to-prebuilt-base-screenshots>
       Or skip diff entirely: --head-only
     ```

2. Acquire lock at `<feature-worktree>/.bugshot/head.lock` via `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Refuse to start if held — message: *"Another vizdiff run is in progress on this worktree. Wait for it to finish or kill the holder, then retry."* Same kernel-managed semantics as the baseline lock: auto-released on any process exit.
3. Locate `<feature-worktree>/.agent-plugins/bento/bugshot/viz/capture-command`. Missing → error.
4. Capture HEAD: run `capture-command <feature-worktree>/.bugshot/head/`. CWD is the feature worktree (uncommitted edits included). Streams stdout/stderr.
5. Pair-and-classify (see Image Pairing below). SHA computed for each HEAD image; compared against `manifest.images[].sha256` from the baseline.
6. Spin up gallery server in diff mode. Browser opens.
7. User reviews, optionally draws regions, types comments, hits Done.
8. On done: emit drafts (markdown or JSON per `--json`). Lock is held for the entire session — released only when the vizdiff process exits.

### HEAD-image storage

Captured HEAD images live at `<feature-worktree>/.bugshot/head/`, persistent across the session so `head_image_path` in drafts remains valid for the agent to act on. Overwritten on every vizdiff run.

`<feature-worktree>/.bugshot/.gitignore` (a single `*` line, written by vizline if it doesn't already exist) keeps the directory out of git regardless of what the parent repo's root `.gitignore` looks like.

### Sharp edge

The agent must consume vizdiff's drafts before re-running vizdiff; a re-run overwrites `.bugshot/head/`, invalidating any `head_image_path` strings in older drafts. Documented in the SKILL.md.

## Baseline Data Model

### Location

Per-worktree, inside the worktree:

```
<worktree-root>/.bugshot/
  baseline/
    manifest.json
    images/
      <whatever layout capture-command produced>
  .gitignore           # contains: *
```

Per-worktree scope aligns with launch-work's "one task = one branch = one linked worktree" rule. Lifecycle is trivial: gone when the worktree is removed.

### Manifest format

```jsonc
{
  "schema_version": 1,
  "base_ref": "main",
  "base_sha": "abc123...",
  "created_at": "2026-04-25T12:34:56Z",
  "capture_command_path": ".agent-plugins/bento/bugshot/viz/capture-command",
  "capture_command_sha256": "def456...",
  "image_count": 42,
  "images": [
    {"path": "pages/login/desktop.png", "sha256": "..."},
    {"path": "pages/login/mobile.png",  "sha256": "..."}
  ]
}
```

`image_count` + per-file SHAs let vizdiff detect partial-write corruption on load. `capture_command_sha256` is informational, not used for invalidation.

### Invalidation — single rule

A baseline is valid **iff** `manifest.base_sha == git rev-parse <currently-resolved base ref>`.

- Rebase moves merge-base → SHA mismatch → vizdiff errors with guidance.
- Capture-command changes do **not** invalidate. The baseline represents *how it looked at that committed state* using whatever script existed at that ref. Newer scripts on HEAD are what we're comparing against, not what regenerates.
- Running vizdiff outside a linked worktree (e.g., directly on main) → no baseline lookup, requires `--base-dir` or `--head-only`.

## Image Pairing & Classification

### Pairing

By relative path within each side. `base_dir/pages/login/desktop.png` matches `head_dir/pages/login/desktop.png`. No flat-namespace requirement; any subdirectory layout the capture-command chose works.

### Four classes

| Class | Definition | Visual treatment |
|---|---|---|
| `unchanged` | Both sides present, SHA-equal | Muted (greyscale + reduced opacity) |
| `changed`   | Both sides present, SHA differs | CHANGED badge |
| `added`     | HEAD only | ADDED badge |
| `removed`   | Base only | REMOVED badge with hatched overlay |

SHA comparison happens once at session start, in Python via `hashlib`. Per-pixel diff visualization is deferred to the browser (Canvas API) on detail-page mount.

### ANSI tiles

Recognized ANSI files (`.ansi`) classify on **raw byte content**: SHA-256 of the file as written, with no whitespace stripping, no line-ending normalization, no escape-sequence canonicalization. Same primitive as image classification, just a different content type. Pairing rules are unchanged (relative path, case-sensitive).

Diff visualization for ANSI tiles is limited to **side-by-side text rendering** (BASE-rendered HTML alongside HEAD-rendered HTML, both produced by the existing `ansi_render.py`). The Canvas-backed modes — swipe slider, onion skin, standalone diff image, and the pixel-diff overlay toggle — are disabled for ANSI tiles because there is no rendered pixel canvas to subtract from. The mode toolbar disables those buttons with a tooltip when an ANSI tile is open.

### Sharp edges

1. Capture-command **must** produce stable relative paths. Random IDs, timestamps, or hostnames in paths cause every image to be classified `added`+`removed`.
2. Cross-extension pairs (`pages/login.png` ↔ `pages/login.webp`) are treated as `removed`+`added`. No automatic extension resolution.
3. Case-sensitive matching on the relative path. If two files differ only in case, surface a warning at session start; let them through as separate paths.
4. Pixel-grid comparison only. EXIF, color profile, and embedded text are not compared.

## Gallery UI

### Index page (image list)

- **Filter chips at top**: CHANGED / ADDED / REMOVED / UNCHANGED. First three on by default; UNCHANGED off.
- **Empty-state override**: if `changed + added + removed == 0` at page load, all four chips default to ON. (User has otherwise nothing meaningful to look at — show everything instead of an empty grid.)
- **Counts pills** alongside chips show totals across all classes regardless of filter, so the unchanged total is always visible.
- **Tile badges** color-coded (amber/green/red/gray) by classification.
- **Removed tiles** rendered with diagonal-hatched overlay + reduced opacity ("no longer present").
- **Changed tiles** rendered with subtle red diff overlay baked into the thumbnail.
- **Comment count** rendered as a small `✎ N` pill on tiles that have at least one comment.
- **Unchanged tiles** (when shown) are visually muted: `filter: grayscale(0.65)`, `opacity: 0.65`, dashed border, compact `UNCHANGED` badge. Hover restores full color and opacity for inspection.
- **Sort**: alphabetical by relative path. Unchanged tiles, when visible, sort *after* changed/added/removed so the eye lands on the meaningful set first.
- **Filter persistence** in `localStorage`.
- **Keyboard**: existing bugshot shortcuts; add `u` to toggle the UNCHANGED filter (analogous to existing `s` size toggle).

### Detail page

```
┌─────────────────────────────────────────────────────────────┐
│  ← prev    pages/login/desktop.png    [CHANGED]   next →    │
├─────────────────────────────────────────────────────────────┤
│  Mode:   [Side-by-side*]  [Swipe]  [Onion]  [Diff image]    │
│  Tools:  [Off*]  [▭]  [✎]              Overlay: [✓ Diff px] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    [   VIEWER PANE   ]                      │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [Describe an issue...                            ] [Submit]│
│  Region: rect attached   ✕                                  │
├─────────────────────────────────────────────────────────────┤
│  ① rect  — "Submit button color regression…"        ✕ ✎    │
│  ② path  — "Headline shifted 4px right."            ✕ ✎    │
│  ⬚ image — "Whole-page check..."                    ✕ ✎    │
└─────────────────────────────────────────────────────────────┘
```

- **Mode toolbar** (radio): Side-by-side (default), Swipe, Onion, Diff image. Selected mode persists in `localStorage` across navigation. Mode change is a JS swap of the viewer pane; no page reload.
- **Tools toolbar** (radio with Off): drawing tool active state determines whether dragging on the viewer creates a region.
- **Overlay toggle**: pixel-diff overlay on HEAD. Visible / meaningful in modes where HEAD is shown (side-by-side, swipe). Hidden in onion + standalone diff image modes.
- **Comment area**: matches existing bugshot pattern (single `<input>` + Submit + stacked list below). Drawing a region with a tool active creates a *pending region* outline on the image; a small "Region: rect attached  ✕" indicator appears above the input. The pending region attaches to the next submitted comment, then clears. Image-level comments (no tool active, no region drawn) work bit-for-bit as today.
- **Comments list**: each comment shows a small region-type badge (`▭ rect`, `✎ path`, `⬚ image-level`).
- **Keyboard**: existing bugshot shortcuts unchanged. Additions:
  - `m` — cycle to next mode (Side-by-side → Swipe → Onion → Diff image → Side-by-side).
  - `M` — cycle backwards.
  - `m` is suppressed while typing in the comment input, same pattern as other letter shortcuts.

### Diff highlighting methods

Four primary view modes, mutually exclusive in the viewer:

1. **Side-by-side**. BASE and HEAD as two panels. Eye does the diffing.
2. **Swipe slider**. One image, draggable vertical divider; left of handle = BASE, right of handle = HEAD. Drag to scrub. Only meaningful when both images are the same dimensions; degrades for `added`/`removed` (no counterpart).
3. **Onion skin**. Stack BASE and HEAD; user drags an opacity slider 0%→100%. Highlights small movements.
4. **Standalone difference image**. Black canvas; only differing pixels glow (per-channel `|base − head|`). Computed in browser via Canvas `ImageData`.

**Pixel-diff overlay** is a separate boolean toggle (not a primary mode): when on and HEAD is visible, differing pixels are painted in semi-transparent red on top of HEAD. Same Canvas calculation as the standalone diff image, rendered with HEAD beneath instead of black.

### User-drawn regions (comments enhancement, applies to bugshot + vizdiff both)

Two drawing tools selectable in the detail-page tools toolbar:

- **Rectangle** (`▭`): click-drag → bounding rect.
- **Freehand** (`✎`): click-drag → closed lasso path.

Coordinates are normalized to `[0, 1]` so rectangles/paths survive image resizing.

### Comments table schema delta

```sql
ALTER TABLE comments ADD COLUMN region TEXT NULL;
```

Payload:

```jsonc
// image-level (no region):
NULL

// rectangle:
{"type":"rect","x":0.12,"y":0.55,"w":0.34,"h":0.08}

// freehand path:
{"type":"path","points":[[0.12,0.55],[0.13,0.56],[0.15,0.57], ...]}
```

This delta applies to **both** bugshot and vizdiff — they share the same comments table. Image-level comments (existing bugshot behavior) leave the column NULL.

## Output Drafts

### Vizdiff JSON output (`--json`)

```jsonc
{
  "draft_count": 2,
  "summary": {
    "changed": 12,
    "added": 3,
    "removed": 2,
    "unchanged": 47
  },
  "drafts": [
    {
      "image_name": "pages/login/desktop.png",
      "classification": "changed",
      "base_image_path": "/abs/<feature-worktree>/.bugshot/baseline/images/pages/login/desktop.png",
      "head_image_path": "/abs/<feature-worktree>/.bugshot/head/pages/login/desktop.png",
      "user_comment": "Submit button color regression — should still be blue.",
      "region": {"type":"rect","x":0.12,"y":0.55,"w":0.34,"h":0.08}
    },
    {
      "image_name": "pages/welcome/desktop.png",
      "classification": "added",
      "base_image_path": null,
      "head_image_path": "/abs/<feature-worktree>/.bugshot/head/pages/welcome/desktop.png",
      "user_comment": "Whole-page check: does this match the spec mock?",
      "region": null
    }
  ]
}
```

- `image_name` is the relative path used for pairing.
- `base_image_path` is `null` for `classification: "added"`; `head_image_path` is `null` for `classification: "removed"`.
- `summary` reflects all classified pairs regardless of which were filtered in the gallery.

### Vizdiff markdown output (default)

```
------------------------------------------------------------
Image name: pages/login/desktop.png
Classification: changed
Base path:  /abs/<feature-worktree>/.bugshot/baseline/images/pages/login/desktop.png
Head path:  /abs/<feature-worktree>/.bugshot/head/pages/login/desktop.png
Region: rect (x=0.12, y=0.55, w=0.34, h=0.08)
User comment: Submit button color regression — should still be blue.
------------------------------------------------------------
```

### Bugshot JSON output (existing schema, `region` field added)

```jsonc
{"draft_count": 2, "drafts": [
  {"image_name": "login-page.png",
   "image_path": "/abs/path/login-page.png",
   "user_comment": "Submit button is clipped",
   "region": null}
]}
```

Backward compatible — existing consumers ignore the field; image-level comments produce `null`.

## Cross-Cutting Concerns

### Stdlib-only Python preserved

Python responsibilities: process orchestration, git-CLI shelling, SQLite I/O, hashlib for SHA, file copy. No PIL, numpy, or external image libraries.

Pixel-level diff rendering happens in the browser via Canvas `ImageData`. The server only delivers raw image bytes plus the per-image SHA classification.

### Base ref default

Default base = `git merge-base HEAD <main-branch>`. Main branch resolved via `git symbolic-ref refs/remotes/origin/HEAD`, falling back to local `main` then `master`. Override accepts any valid git ref via `--base <ref>` on vizline / vizdiff.

If HEAD *is* the main branch, merge-base == HEAD and the diff is trivially empty; vizline exits with a clear message.

### Worktree ownership

- **Feature worktrees** (where the user works) — created and owned by the launching skill. Vizline and vizdiff operate inside one as input; they never create one.
- **Ephemeral base-ref worktree** — created and destroyed by vizline within one invocation. Placement determined by the discovery cascade documented in the contract section.
- **Vizdiff** never creates a worktree.

### Concurrent invocations

Both skills use `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on a held file descriptor. The kernel releases the lock when the process exits for any reason — clean shutdown, unhandled exception, SIGKILL, OOM, or host crash — so no stale-lock recovery path is needed and the lock file is allowed to remain on disk between runs.

- Two simultaneous vizline runs on the same feature worktree race on `.bugshot/baseline.lock`; the second exits non-zero with a "lock held" message.
- Two simultaneous vizdiff runs on the same feature worktree race on `.bugshot/head.lock`; the second exits non-zero with a "another vizdiff run is in progress" message. Prevents silent corruption of `.bugshot/head/` and the drafts that reference it.
- vizline and vizdiff use different lock files, so a baseline refresh and a HEAD review do not block each other.

## Open Items

- **Skill triggers**: not enforced. The user (or their launching skill) decides when to invoke vizline. Documented in SKILL.md but not wired into any specific launcher.
- **Windows support**: `capture-command` discovery currently looks for an executable file with no extension. Native Windows support (looking for `capture-command.cmd` / `.ps1`) is deferred — bugshot itself is stdlib-only Python and runs on Windows; projects using it on Windows can rely on WSL for the contract scripts.
- **Per-image diff metadata**: currently nothing beyond classification + SHA. If we later want diff-pixel counts or affected-area percentages for sorting, we add a small computation pass at session start. Not required for v1.

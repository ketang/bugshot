# Bugshot Design Spec

## Overview

Bugshot is an ephemeral screenshot gallery viewer for filing bugs. A human reviews screenshots of a target application in a browser, types comments describing issues, and a controlling LLM agent (Claude Code / Codex) files those comments as issues in the target project's issue tracker.

Invoked as `/bugshot /path/to/screenshots` in a Claude Code session.

## Actors

- **Human user**: Reviews screenshots in the browser, types comments, signals when done.
- **Bugshot skill**: Agent-side orchestrator running in Claude Code. Launches the gallery server, waits for the user to finish, processes comments into issues.
- **Gallery server**: Python 3 HTTP server. Serves the gallery frontend, stores comments in SQLite, tracks session lifecycle.
- **Issue-flow skill**: External skill (github-issue-flow, beads-issue-flow, etc.) that the bugshot skill delegates to for actually creating issues in the tracker.

## System Architecture

```
+------------------+       stdout JSON        +-----------------+
|  Bugshot Skill   |<-------------------------|  Gallery Server |
|  (Claude Code)   |  GET /api/comments       |  (Python 3)     |
|                  |  GET /api/status          |                 |
|                  |------------------------->|                 |
|  - examines imgs |                           |  serves HTML    |
|  - checks dupes  |                           |  accepts POST   |
|  - files issues  |       HTTP                |  SQLite state   |
|                  |                           |                 |
+------------------+                           +--------+--------+
                                                        |
                                                 HTML/CSS/JS
                                                        |
                                                +-------v--------+
                                                |    Browser     |
                                                |    (User)      |
                                                +----------------+
```

Communication between skill and server:
- **Startup**: Server prints JSON to stdout: `{"port": N, "url": "http://...", "images": [...]}`
- **Comments**: Skill reads `GET /api/comments` after the user signals done.
- **Lifecycle**: Skill polls `GET /api/status` to detect when the user is done.

## Gallery Server

### Technology

- Python 3, stdlib only (`http.server`, `socketserver`, `sqlite3`, `json`, `os`, `urllib`, `webbrowser`).
- Zero external dependencies.
- `ThreadingMixIn` for concurrent request handling.
- SQLite database (file-backed via `tempfile.NamedTemporaryFile` in the system temp directory) for comment storage and session state. Database is ephemeral — deleted when the server stops via an `atexit` handler.

### Startup

1. Accepts a directory path as a command-line argument.
2. Validates the directory exists and contains at least one recognized file.
3. Discovers files: image extensions (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`) and `.ansi` for terminal screenshots.
4. Sorts files alphabetically by filename.
5. Binds to `127.0.0.1:0` (OS-assigned port). For collaborator sharing, a flag (e.g., `--bind 0.0.0.0`) overrides this.
6. Initializes the SQLite database.
7. Prints startup JSON to stdout: `{"port": N, "url": "http://127.0.0.1:N", "images": ["file1.png", "file2.ansi", ...]}`.
8. Begins serving requests.

### Routes

#### Page Routes

| Method | Path              | Purpose                          |
|--------|-------------------|----------------------------------|
| GET    | `/`               | Index page — thumbnail grid      |
| GET    | `/view/<filename>` | Detail page for a single image   |
| GET    | `/static/<path>`  | Static assets (CSS, JS)          |

#### API Routes

| Method | Path                  | Purpose                                      |
|--------|-----------------------|----------------------------------------------|
| POST   | `/api/comments`       | Submit a comment (image + body)              |
| GET    | `/api/comments`       | Batch read all comments                      |
| PATCH  | `/api/comments/<id>`  | Edit a comment                               |
| DELETE | `/api/comments/<id>`  | Delete a comment                             |
| POST   | `/api/heartbeat`      | Browser pings periodically (every 5s)        |
| POST   | `/api/done`           | User clicked "Done Reviewing"                |
| POST   | `/api/closed`         | `beforeunload` signal — browser closing      |
| GET    | `/api/status`         | Skill polls this for session state            |

#### API Details

**POST /api/comments**
- Request: `{"image": "login-page.png", "body": "Submit button is clipped"}`
- Response: `{"id": 1, "image": "...", "body": "...", "created_at": "..."}`

**GET /api/comments**
- Response: `[{"id": 1, "image": "login-page.png", "body": "Submit button is clipped", "created_at": "2026-04-15T10:30:00"}, ...]`

**PATCH /api/comments/\<id\>**
- Request: `{"body": "Updated text"}`
- Response: `{"id": 1, "image": "...", "body": "Updated text", "created_at": "..."}`

**DELETE /api/comments/\<id\>**
- Response: `204 No Content`

**GET /api/status**
- Response: `{"done": false, "reason": null}` or `{"done": true, "reason": "button"|"timeout"|"closed"}`

### SQLite Schema

```sql
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE session (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Rows: ("done", "false"), ("done_reason", ""), ("last_heartbeat", "<isotimestamp>")
```

### Heartbeat and Browser Close Detection

- Browser sends `POST /api/heartbeat` every 5 seconds from every page.
- Server updates `last_heartbeat` in the session table.
- `beforeunload` fires `POST /api/closed` via `navigator.sendBeacon` — sets done=true, reason="closed".
- When the skill polls `GET /api/status`, the server checks: if `last_heartbeat` is older than 15 seconds and done is not already true, it returns `{"done": true, "reason": "timeout"}`.

### Shutdown

The skill terminates the server subprocess when processing is complete. The SQLite temp file is cleaned up on exit.

## Gallery Frontend

### File Structure

```
static/
    style.css           # Dark theme, grid layout, detail page styles
    gallery.js          # Heartbeat, comment CRUD, keyboard shortcuts,
                        #   size toggle, beforeunload, done button
templates/
    index.html          # Thumbnail grid, size toggle, done button
    detail.html         # Image/ANSI view, nav, comment input, comment list
```

### Index Page (`/`)

- Grid of thumbnails (CSS-scaled full images).
- Each thumbnail labeled with its filename.
- Size toggle: switches between thumbnail size and full size in place.
- ANSI files: displayed as a preview of the rendered HTML (first ~20 lines, monospace, styled), CSS-clipped to match thumbnail dimensions.
- Click a thumbnail to navigate to its detail page.
- "Done Reviewing" button — prominently placed with a confirmation dialog to prevent accidental clicks.

### Detail Page (`/view/<filename>`)

- Full-size image, or full ANSI rendering for `.ansi` files.
- Filename displayed.
- Navigation: Previous / Next / Back to Index.
- Comment input: text field + submit button. Enter to submit.
- List of previously submitted comments for this image, displayed below the input. Each comment has edit and delete controls.
- Server injects the image source (URL for images, rendered HTML for ANSI files) and the navigation links (previous/next filenames) into the template.

### Keyboard Shortcuts

| Key         | Action                        |
|-------------|-------------------------------|
| Left arrow  | Previous image (detail view)  |
| Right arrow | Next image (detail view)      |
| Escape      | Back to index                 |
| `c`         | Focus comment input           |
| Enter       | Submit comment (when focused) |

Shortcuts are suppressed when the comment input is focused (except Enter for submit and Escape to blur).

### Visual Style

- Dark theme (dark background, light text).
- Monospace font for ANSI rendering.
- Minimal chrome — the screenshots are the focus.

### JavaScript Behavior

- `gallery.js` runs on every page.
- Starts heartbeat interval (`POST /api/heartbeat` every 5s).
- Registers `beforeunload` handler to fire `POST /api/closed` via `navigator.sendBeacon`.
- On index page: handles size toggle.
- On detail page: handles comment CRUD (fetch-based), keyboard shortcuts, navigation.
- Done button: shows confirmation dialog, then `POST /api/done`.

## ANSI Rendering

A separate Python module (`ansi_render.py`) that converts ANSI escape sequences to HTML.

### Interface

```python
def ansi_to_html(text: str) -> str:
    """Convert text with ANSI escape sequences to styled HTML.

    Returns a string of HTML with <span> elements carrying inline
    styles for colors and attributes. Intended to be placed inside
    a <pre> block.
    """
```

### Supported SGR Attributes

- Bold, dim, italic, underline, strikethrough, inverse.
- Reset (code 0).
- 8/16 foreground colors (codes 30-37, 90-97).
- 8/16 background colors (codes 40-47, 100-107).
- 256-color: `38;5;N` (foreground), `48;5;N` (background).
- 24-bit truecolor: `38;2;R;G;B` (foreground), `48;2;R;G;B` (background).

### Out of Scope

- Cursor positioning, cursor visibility, alternate screen buffer, scrolling regions — these sequences are stripped.
- Hyperlink sequences (OSC 8) — stripped.

### Rendering Approach

Stateful parser: walk through the text character by character, tracking current SGR state. On each SGR sequence, update the state. On printable characters, emit them wrapped in a `<span>` with inline CSS reflecting the current state. Emit a new `<span>` only when the state changes, to keep the output compact.

## Bugshot Skill

### Invocation

```
/bugshot /path/to/screenshots
```

### Lifecycle

**1. Launch**
- Validate that the directory exists and contains recognized files.
- Start `gallery-server.py` as a subprocess, passing the directory path.
- Read startup JSON from stdout.
- Attempt `webbrowser.open(url)`. If it fails (headless, SSH), print the URL for the user.

**2. Wait**
- Poll `GET /api/status` every 3 seconds.
- Three done signals:
  - Done button in the gallery UI (`reason: "button"`).
  - Browser close via `beforeunload` or heartbeat timeout (`reason: "closed"` or `reason: "timeout"`).
  - User says "done" or equivalent in the terminal — skill sets its own done flag.
- On `reason: "timeout"` or `reason: "closed"`, skill confirms with the user: "It looks like you closed the browser. Are you done reviewing?"

**3. Process Comments**
- `GET /api/comments` to read all comments.
- If no comments, report "No comments submitted" and proceed to shutdown.
- For each comment:
  1. **Examine screenshot**: Read the image file (or `.ansi` file) using LLM vision. Extract visual details to enrich the issue — what's depicted, UI elements involved, specific visual defects observed.
  2. **Compose issue**: Combine the user's comment (core observation) with the LLM's visual analysis. Use project issue templates if available, otherwise default structure: Current Behavior / Expected Behavior / Steps to Reproduce / Screenshot Description / Additional Context.
  3. **Check duplicates**: Search existing issues (open and closed) using keywords from the composed issue. If potential duplicates found, present them to the user and ask whether to proceed.
  4. **Confirm**: Show the composed issue to the user in the terminal, ask for confirmation to file.
  5. **File**: Delegate to the project's issue-flow skill (github-issue-flow, beads-issue-flow, etc.).
  6. **Attach screenshot**: Attempt to attach the image to the filed issue. If attachment fails, report concisely in the terminal.
  7. **Report**: Print the filed issue number/URL.

**4. Shutdown**
- Terminate the gallery server subprocess.
- Temp SQLite file is cleaned up.

### Screenshot Selection

The skill does not need to guess which screenshot a comment refers to — each comment is bound to a specific image by the gallery UI. The `image` field in the comment payload is the filename.

### Issue-Flow Delegation

The skill does not own issue tracker integration. It delegates to whatever issue-flow skill the project uses. It uses that skill's documented create command to file the issue.

## File Structure

```
bugshot/
├── gallery-server.py       # HTTP server, routing, SQLite setup, startup
├── ansi_render.py          # ANSI escape sequence to HTML converter
├── static/
│   ├── style.css           # Dark theme, grid layout, detail page styles
│   └── gallery.js          # Heartbeat, comment CRUD, keyboard shortcuts,
│                           #   size toggle, beforeunload, done button
├── templates/
│   ├── index.html          # Thumbnail grid, size toggle, done button
│   └── detail.html         # Image/ANSI view, nav, comment input, comment list
└── SKILL.md                # Skill definition for Claude Code
```

## Distribution

Primary: distributed as a Claude Code skill. The skill bundles all files. No external dependencies, no build step, no container. Requires Python 3 on the host machine.

Alternative: container image for environments where Python is unavailable. Not in MVP scope.

## Collaborator Sharing

The server binds to `127.0.0.1` by default. For sharing, the user passes `--bind 0.0.0.0` and gives the collaborator the machine's hostname/IP and port. No authentication or access control.

## MVP Scope

**In:**
- Gallery server with all routes
- Index and detail views
- ANSI rendering (256-color, truecolor, linear)
- Comment CRUD
- Done button, browser close detection, heartbeat
- Batch comment read
- Skill orchestration (launch, wait, process, file, shutdown)
- Duplicate detection
- Issue composition with LLM vision enrichment
- Browser auto-launch
- Collaborator sharing via `--bind`

**Out (future):**
- Real-time comment polling (agent processes comments as they arrive)
- Filed-issue status reflected back in gallery UI
- Container distribution
- Region/annotation markup on screenshots

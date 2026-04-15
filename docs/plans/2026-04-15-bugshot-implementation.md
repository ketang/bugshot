# Bugshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ephemeral screenshot gallery viewer that lets a human review screenshots and type bug comments, which a Claude Code skill then processes into filed issues.

**Architecture:** Python 3 stdlib HTTP server with SQLite for ephemeral state. Separate static frontend files (HTML/CSS/JS). ANSI-to-HTML rendering in a standalone Python module. A Claude Code skill (SKILL.md) orchestrates the full lifecycle.

**Tech Stack:** Python 3 stdlib only (http.server, socketserver, sqlite3, json, os, urllib, webbrowser, tempfile, atexit). No external runtime dependencies. pytest for testing.

**Spec:** `docs/specs/2026-04-15-bugshot-design.md`

**Security note on innerHTML:** The frontend uses `innerHTML` in two controlled contexts: (1) rendering gallery item structure from server-provided JSON, and (2) injecting server-rendered ANSI HTML. All user-supplied text (filenames, comment bodies) is escaped via `escapeHtml()` or rendered via `textContent`. ANSI HTML originates from local `.ansi` files processed by `ansi_render.py` on the server. For a local-only ephemeral tool this is acceptable. Use `textContent` or DOM construction methods everywhere user content is displayed.

---

## File Structure

```
bugshot/
├── gallery_server.py       # HTTP server, routing, SQLite setup, startup
├── ansi_render.py          # ANSI escape sequence to HTML converter
├── static/
│   ├── style.css           # Dark theme, grid layout, detail page styles
│   └── gallery.js          # Heartbeat, comment CRUD, keyboard shortcuts,
│                           #   size toggle, beforeunload, done button
├── templates/
│   ├── index.html          # Thumbnail grid, size toggle, done button
│   └── detail.html         # Image/ANSI view, nav, comment input, comment list
├── tests/
│   ├── conftest.py         # Shared fixtures (temp dirs with test images, server instance)
│   ├── test_ansi_render.py # Unit tests for ANSI rendering
│   └── test_server.py      # HTTP-level tests for all server routes
├── SKILL.md                # Skill definition for Claude Code
└── docs/
    ├── specs/
    │   └── 2026-04-15-bugshot-design.md
    └── plans/
        └── 2026-04-15-bugshot-implementation.md
```

Note: the spec uses `gallery-server.py` (hyphen) but Python module imports require underscores. Use `gallery_server.py` for the filename.

---

## Part 1: ANSI Renderer

Self-contained module with no dependency on the server. Can be built and tested in complete isolation.

### Task 1.1: ANSI Renderer — Basic SGR (reset, bold, dim, italic, underline, strikethrough, inverse)

**Files:**
- Create: `ansi_render.py`
- Create: `tests/test_ansi_render.py`

- [ ] **Step 1: Write failing tests for basic attributes**

Create `tests/test_ansi_render.py`:

```python
from ansi_render import ansi_to_html

ESC = "\x1b"


def test_plain_text():
    assert ansi_to_html("hello world") == "hello world"


def test_empty_string():
    assert ansi_to_html("") == ""


def test_html_entities_escaped():
    assert ansi_to_html("<div>&amp;</div>") == "&lt;div&gt;&amp;amp;&lt;/div&gt;"


def test_bold():
    result = ansi_to_html(f"{ESC}[1mbold{ESC}[0m")
    assert 'font-weight:bold' in result
    assert "bold" in result


def test_dim():
    result = ansi_to_html(f"{ESC}[2mdim{ESC}[0m")
    assert 'opacity:0.5' in result


def test_italic():
    result = ansi_to_html(f"{ESC}[3mitalic{ESC}[0m")
    assert 'font-style:italic' in result


def test_underline():
    result = ansi_to_html(f"{ESC}[4munderline{ESC}[0m")
    assert 'text-decoration:underline' in result


def test_strikethrough():
    result = ansi_to_html(f"{ESC}[9mstrike{ESC}[0m")
    assert 'text-decoration:line-through' in result


def test_inverse():
    # Inverse with fg=red should produce bg=red and fg=default-bg
    result = ansi_to_html(f"{ESC}[31;7minverse{ESC}[0m")
    # Red foreground (#c91b00) becomes background when inverted
    assert 'background-color:#c91b00' in result


def test_reset_clears_all():
    result = ansi_to_html(f"{ESC}[1mbold{ESC}[0m plain")
    assert "plain" in result
    # "plain" should not be inside a styled span
    assert result.endswith(" plain")


def test_newlines_preserved():
    result = ansi_to_html("line1\nline2")
    assert "line1\nline2" in result


def test_non_sgr_sequences_stripped():
    # Cursor movement \x1b[H should be stripped
    result = ansi_to_html(f"{ESC}[Hhello")
    assert result == "hello"
    # Cursor position \x1b[5;10H should be stripped
    result = ansi_to_html(f"{ESC}[5;10Hhello")
    assert result == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_ansi_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ansi_render'`

- [ ] **Step 3: Implement the ANSI renderer with basic SGR support**

Create `ansi_render.py`:

```python
"""Convert text with ANSI escape sequences to styled HTML.

Supports SGR attributes (bold, dim, italic, underline, strikethrough,
inverse), 8/16 colors, 256-color, and 24-bit truecolor. Non-SGR
sequences (cursor movement, screen control, etc.) are stripped.
"""

import html
import re

# Standard 8-color palette (normal intensity)
COLORS_16 = [
    "#000000",  # 0 black
    "#c91b00",  # 1 red
    "#00c200",  # 2 green
    "#c7c400",  # 3 yellow
    "#0225c7",  # 4 blue
    "#c930c7",  # 5 magenta
    "#00c5c7",  # 6 cyan
    "#c7c7c7",  # 7 white
    "#686868",  # 8 bright black
    "#ff6e67",  # 9 bright red
    "#5ffa68",  # 10 bright green
    "#fffc67",  # 11 bright yellow
    "#6871ff",  # 12 bright blue
    "#ff77ff",  # 13 bright magenta
    "#60fdff",  # 14 bright cyan
    "#ffffff",  # 15 bright white
]

DEFAULT_FG = "#e0e0e0"
DEFAULT_BG = "#1a1a1a"

# Regex matching any ANSI escape sequence (CSI, OSC, etc.)
_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-9;]*[A-Za-z]|\][^\x07]*\x07|\[[\x20-\x2f]*[\x40-\x7e])"
)

# Regex matching only SGR sequences: ESC [ <params> m
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _color_256(n):
    """Return a hex color string for a 256-color palette index."""
    if n < 16:
        return COLORS_16[n]
    if n < 232:
        # 6x6x6 color cube
        n -= 16
        b = (n % 6) * 51
        n //= 6
        g = (n % 6) * 51
        r = (n // 6) * 51
        return f"#{r:02x}{g:02x}{b:02x}"
    # Grayscale ramp
    v = 8 + (n - 232) * 10
    return f"#{v:02x}{v:02x}{v:02x}"


class _State:
    """Tracks the current SGR state."""

    __slots__ = ("bold", "dim", "italic", "underline", "strikethrough",
                 "inverse", "fg", "bg")

    def __init__(self):
        self.reset()

    def reset(self):
        self.bold = False
        self.dim = False
        self.italic = False
        self.underline = False
        self.strikethrough = False
        self.inverse = False
        self.fg = None  # None means default
        self.bg = None

    def to_style(self):
        """Return a CSS style string for the current state, or empty string."""
        parts = []
        fg = self.fg or DEFAULT_FG
        bg = self.bg or DEFAULT_BG
        if self.inverse:
            fg, bg = bg, fg

        if fg != DEFAULT_FG:
            parts.append(f"color:{fg}")
        if bg != DEFAULT_BG:
            parts.append(f"background-color:{bg}")
        if self.bold:
            parts.append("font-weight:bold")
        if self.dim:
            parts.append("opacity:0.5")
        if self.italic:
            parts.append("font-style:italic")

        decorations = []
        if self.underline:
            decorations.append("underline")
        if self.strikethrough:
            decorations.append("line-through")
        if decorations:
            parts.append(f"text-decoration:{' '.join(decorations)}")

        return ";".join(parts)

    def __eq__(self, other):
        if not isinstance(other, _State):
            return NotImplemented
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in self.__slots__
        )

    def copy(self):
        new = _State.__new__(_State)
        for attr in self.__slots__:
            setattr(new, attr, getattr(self, attr))
        return new


def _parse_sgr(params_str, state):
    """Apply SGR parameter string to state."""
    if not params_str:
        state.reset()
        return

    params = [int(p) if p else 0 for p in params_str.split(";")]
    i = 0
    while i < len(params):
        p = params[i]
        if p == 0:
            state.reset()
        elif p == 1:
            state.bold = True
        elif p == 2:
            state.dim = True
        elif p == 3:
            state.italic = True
        elif p == 4:
            state.underline = True
        elif p == 9:
            state.strikethrough = True
        elif p == 7:
            state.inverse = True
        elif p == 22:
            state.bold = False
            state.dim = False
        elif p == 23:
            state.italic = False
        elif p == 24:
            state.underline = False
        elif p == 27:
            state.inverse = False
        elif p == 29:
            state.strikethrough = False
        elif 30 <= p <= 37:
            state.fg = COLORS_16[p - 30]
        elif p == 38:
            # Extended foreground
            if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
                state.fg = _color_256(params[i + 2])
                i += 2
            elif i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
                r, g, b = params[i + 2], params[i + 3], params[i + 4]
                state.fg = f"#{r:02x}{g:02x}{b:02x}"
                i += 4
        elif p == 39:
            state.fg = None
        elif 40 <= p <= 47:
            state.bg = COLORS_16[p - 40]
        elif p == 48:
            # Extended background
            if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
                state.bg = _color_256(params[i + 2])
                i += 2
            elif i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
                r, g, b = params[i + 2], params[i + 3], params[i + 4]
                state.bg = f"#{r:02x}{g:02x}{b:02x}"
                i += 4
        elif p == 49:
            state.bg = None
        elif 90 <= p <= 97:
            state.fg = COLORS_16[p - 90 + 8]
        elif 100 <= p <= 107:
            state.bg = COLORS_16[p - 100 + 8]
        i += 1


def ansi_to_html(text):
    """Convert text with ANSI escape sequences to styled HTML.

    Returns a string of HTML with <span> elements carrying inline
    styles for colors and attributes. Intended to be placed inside
    a <pre> block.
    """
    if not text:
        return ""

    state = _State()
    prev_style = ""
    output = []
    in_span = False

    pos = 0
    for match in _ANSI_RE.finditer(text):
        start, end = match.span()

        # Emit text before this escape
        if start > pos:
            chunk = html.escape(text[pos:start])
            style = state.to_style()
            if style != prev_style:
                if in_span:
                    output.append("</span>")
                if style:
                    output.append(f'<span style="{style}">')
                    in_span = True
                else:
                    in_span = False
                prev_style = style
            output.append(chunk)

        # Process SGR sequences, strip everything else
        sgr_match = _SGR_RE.fullmatch(match.group())
        if sgr_match:
            _parse_sgr(sgr_match.group(1), state)

        pos = end

    # Emit remaining text
    if pos < len(text):
        chunk = html.escape(text[pos:])
        style = state.to_style()
        if style != prev_style:
            if in_span:
                output.append("</span>")
            if style:
                output.append(f'<span style="{style}">')
                in_span = True
            else:
                in_span = False
        output.append(chunk)

    if in_span:
        output.append("</span>")

    return "".join(output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_ansi_render.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add ansi_render.py tests/test_ansi_render.py
git commit -m "feat: add ANSI escape sequence to HTML renderer with basic SGR support"
```

### Task 1.2: ANSI Renderer — Colors (8/16, 256, truecolor)

**Files:**
- Modify: `tests/test_ansi_render.py`
- (Implementation already in `ansi_render.py` from Task 1.1 — these tests validate it)

- [ ] **Step 1: Write tests for color support**

Append to `tests/test_ansi_render.py`:

```python
def test_fg_red():
    result = ansi_to_html(f"{ESC}[31mred{ESC}[0m")
    assert "color:#c91b00" in result
    assert "red" in result


def test_bg_green():
    result = ansi_to_html(f"{ESC}[42mgreenbg{ESC}[0m")
    assert "background-color:#00c200" in result


def test_bright_fg():
    result = ansi_to_html(f"{ESC}[91mbright red{ESC}[0m")
    assert "color:#ff6e67" in result


def test_bright_bg():
    result = ansi_to_html(f"{ESC}[102mbright green bg{ESC}[0m")
    assert "background-color:#5ffa68" in result


def test_256_color_fg():
    # Color index 196 is red in the 6x6x6 cube
    result = ansi_to_html(f"{ESC}[38;5;196mred256{ESC}[0m")
    assert "color:#ff0000" in result


def test_256_color_bg():
    result = ansi_to_html(f"{ESC}[48;5;21mblue256{ESC}[0m")
    assert "background-color:#0000ff" in result


def test_256_grayscale():
    # Index 240 should be a mid-gray
    result = ansi_to_html(f"{ESC}[38;5;240mgray{ESC}[0m")
    assert "color:#58" in result  # 8 + (240-232)*10 = 88 = 0x58


def test_truecolor_fg():
    result = ansi_to_html(f"{ESC}[38;2;255;128;0morange{ESC}[0m")
    assert "color:#ff8000" in result


def test_truecolor_bg():
    result = ansi_to_html(f"{ESC}[48;2;0;0;128mnavybg{ESC}[0m")
    assert "background-color:#000080" in result


def test_default_fg_reset():
    result = ansi_to_html(f"{ESC}[31mred{ESC}[39mdefault")
    # After ESC[39m, color should return to default (no color style)
    assert "default" in result


def test_combined_attributes():
    result = ansi_to_html(f"{ESC}[1;31;42mboldredgreen{ESC}[0m")
    assert "font-weight:bold" in result
    assert "color:#c91b00" in result
    assert "background-color:#00c200" in result
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_ansi_render.py -v`
Expected: all PASS (the implementation from Task 1.1 already handles colors)

If any fail, fix the implementation in `ansi_render.py` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ansi_render.py
git commit -m "test: add color tests for ANSI renderer (8/16, 256, truecolor)"
```

---

## Part 2: Gallery Server — Static Gallery

Build the HTTP server that serves a browsable gallery. No comments, no session lifecycle yet — just images and navigation.

### Task 2.1: Server Skeleton with Image Discovery and Startup JSON

**Files:**
- Create: `gallery_server.py`
- Create: `tests/conftest.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for startup and image discovery**

Create `tests/conftest.py`:

```python
import json
import os
import shutil
import subprocess
import tempfile

import pytest


@pytest.fixture
def screenshot_dir():
    """Create a temp directory with test images and an ANSI file."""
    d = tempfile.mkdtemp(prefix="bugshot_test_")

    # Create minimal valid PNG files (1x1 pixel)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    for name in ["alpha.png", "beta.png", "gamma.jpg"]:
        with open(os.path.join(d, name), "wb") as f:
            f.write(png_bytes)

    # Create an ANSI file
    with open(os.path.join(d, "delta.ansi"), "w") as f:
        f.write("\x1b[31mRed text\x1b[0m\n")

    yield d
    shutil.rmtree(d)


@pytest.fixture
def server(screenshot_dir):
    """Start the gallery server and yield (url, info, process)."""
    proc = subprocess.Popen(
        ["python3", "gallery_server.py", screenshot_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    # Read startup JSON from stdout
    line = proc.stdout.readline().decode().strip()
    info = json.loads(line)
    url = info["url"]

    yield url, info, proc

    proc.terminate()
    proc.wait(timeout=5)
```

Create `tests/test_server.py`:

```python
import json
import urllib.request
import urllib.error
import urllib.parse


def _post_json(url, data):
    """POST JSON to a URL and return (status, parsed_body)."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _patch_json(url, data):
    """PATCH JSON to a URL and return (status, parsed_body)."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _delete(url):
    """DELETE a URL and return the status code."""
    req = urllib.request.Request(url, method="DELETE")
    try:
        resp = urllib.request.urlopen(req)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def _get_json(url):
    """GET a URL and return (status, parsed_body)."""
    resp = urllib.request.urlopen(url)
    return resp.status, json.loads(resp.read())


def test_startup_json(server):
    url, info, proc = server
    assert "port" in info
    assert "url" in info
    assert "images" in info
    assert info["images"] == ["alpha.png", "beta.png", "delta.ansi", "gamma.jpg"]


def test_index_page_returns_200(server):
    url, info, proc = server
    resp = urllib.request.urlopen(f"{url}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert "alpha.png" in body
    assert "beta.png" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_server.py -v`
Expected: FAIL — `gallery_server.py` does not exist or doesn't start

- [ ] **Step 3: Implement server skeleton**

Create `gallery_server.py`:

```python
"""Bugshot gallery server.

Usage: python3 gallery_server.py /path/to/screenshots [--bind ADDRESS]
"""

import argparse
import atexit
import datetime
import json
import os
import sqlite3
import sys
import tempfile
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ANSI_EXTENSION = ".ansi"
RECOGNIZED_EXTENSIONS = IMAGE_EXTENSIONS | {ANSI_EXTENSION}

HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_TIMEOUT_SECONDS = 15


def discover_images(directory):
    """Return sorted list of recognized filenames in directory."""
    names = []
    for name in os.listdir(directory):
        ext = os.path.splitext(name)[1].lower()
        if ext in RECOGNIZED_EXTENSIONS:
            names.append(name)
    names.sort()
    return names


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class GalleryHandler(SimpleHTTPRequestHandler):
    """Routes requests to the appropriate handler."""

    # Set by main() before serving
    screenshot_dir = None
    images = None
    db_path = None
    template_dir = None
    static_dir = None

    def log_message(self, format, *args):
        """Suppress request logging for clean output."""
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/" or path == "":
            self._serve_index()
        elif path.startswith("/view/"):
            filename = path[len("/view/"):]
            self._serve_detail(filename)
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        elif path.startswith("/screenshots/"):
            self._serve_screenshot(path[len("/screenshots/"):])
        elif path == "/api/comments":
            self._serve_comments_list()
        elif path == "/api/status":
            self._serve_status()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/api/comments":
            self._handle_comment_create()
        elif path == "/api/heartbeat":
            self._handle_heartbeat()
        elif path == "/api/done":
            self._handle_done()
        elif path == "/api/closed":
            self._handle_closed()
        else:
            self.send_error(404)

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path.startswith("/api/comments/"):
            comment_id = path[len("/api/comments/"):]
            self._handle_comment_update(comment_id)
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path.startswith("/api/comments/"):
            comment_id = path[len("/api/comments/"):]
            self._handle_comment_delete(comment_id)
        else:
            self.send_error(404)

    # -- Page handlers --

    def _serve_index(self):
        template_path = os.path.join(self.template_dir, "index.html")
        with open(template_path, "r") as f:
            template = f.read()

        image_items = []
        for name in self.images:
            ext = os.path.splitext(name)[1].lower()
            encoded_name = urllib.parse.quote(name)
            if ext == ANSI_EXTENSION:
                from ansi_render import ansi_to_html
                ansi_path = os.path.join(self.screenshot_dir, name)
                with open(ansi_path, "r") as f:
                    ansi_content = f.read()
                rendered_html = ansi_to_html(ansi_content)
                image_items.append({
                    "name": name,
                    "encoded_name": encoded_name,
                    "type": "ansi",
                    "preview_html": rendered_html,
                })
            else:
                image_items.append({
                    "name": name,
                    "encoded_name": encoded_name,
                    "type": "image",
                    "src": f"/screenshots/{encoded_name}",
                })

        content = template.replace("{{images_json}}", json.dumps(image_items))
        self._send_html(content)

    def _serve_detail(self, filename):
        if filename not in self.images:
            self.send_error(404, f"Image not found: {filename}")
            return

        template_path = os.path.join(self.template_dir, "detail.html")
        with open(template_path, "r") as f:
            template = f.read()

        idx = self.images.index(filename)
        prev_name = self.images[idx - 1] if idx > 0 else None
        next_name = self.images[idx + 1] if idx < len(self.images) - 1 else None

        ext = os.path.splitext(filename)[1].lower()
        encoded_name = urllib.parse.quote(filename)

        if ext == ANSI_EXTENSION:
            from ansi_render import ansi_to_html
            ansi_path = os.path.join(self.screenshot_dir, filename)
            with open(ansi_path, "r") as f:
                ansi_content = f.read()
            rendered_html = ansi_to_html(ansi_content)
            content_type = "ansi"
            image_src = ""
        else:
            rendered_html = ""
            content_type = "image"
            image_src = f"/screenshots/{encoded_name}"

        nav = {
            "prev": f"/view/{urllib.parse.quote(prev_name)}" if prev_name else None,
            "next": f"/view/{urllib.parse.quote(next_name)}" if next_name else None,
            "prev_name": prev_name,
            "next_name": next_name,
        }

        replacements = {
            "{{filename}}": filename,
            "{{content_type}}": content_type,
            "{{image_src}}": image_src,
            "{{ansi_html}}": rendered_html,
            "{{nav_json}}": json.dumps(nav),
            "{{encoded_name}}": encoded_name,
        }
        content = template
        for key, value in replacements.items():
            content = content.replace(key, value)

        self._send_html(content)

    def _serve_static(self, filename):
        safe_name = os.path.basename(filename)
        filepath = os.path.join(self.static_dir, safe_name)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return

        ext = os.path.splitext(safe_name)[1].lower()
        content_types = {
            ".css": "text/css",
            ".js": "application/javascript",
        }
        ctype = content_types.get(ext, "application/octet-stream")

        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_screenshot(self, filename):
        safe_name = os.path.basename(urllib.parse.unquote(filename))
        filepath = os.path.join(self.screenshot_dir, safe_name)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return

        ext = os.path.splitext(safe_name)[1].lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        ctype = content_types.get(ext, "application/octet-stream")

        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- API handlers --

    def _serve_comments_list(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        image_filter = query.get("image", [None])[0]

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if image_filter:
            rows = conn.execute(
                "SELECT id, image, body, created_at FROM comments WHERE image = ? ORDER BY id",
                (image_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, image, body, created_at FROM comments ORDER BY id"
            ).fetchall()
        conn.close()
        self._send_json([dict(r) for r in rows])

    def _handle_comment_create(self):
        data = self._read_json_body()
        image = data.get("image")
        body = data.get("body")
        if not image or not body:
            self._send_json({"error": "image and body are required"}, status=400)
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO comments (image, body) VALUES (?, ?)",
            (image, body),
        )
        row = conn.execute(
            "SELECT id, image, body, created_at FROM comments WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        conn.commit()
        conn.close()
        self._send_json(dict(row))

    def _handle_comment_update(self, comment_id):
        data = self._read_json_body()
        body = data.get("body")
        if not body:
            self._send_json({"error": "body is required"}, status=400)
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE comments SET body = ? WHERE id = ?",
            (body, comment_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, image, body, created_at FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone()
        conn.close()

        if row is None:
            self._send_json({"error": "not found"}, status=404)
            return
        self._send_json(dict(row))

    def _handle_comment_delete(self, comment_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            self._send_json({"error": "not found"}, status=404)
            return

        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_heartbeat(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE session SET value = datetime('now') WHERE key = 'last_heartbeat'"
        )
        conn.commit()
        conn.close()
        self._send_json({"ok": True})

    def _handle_done(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE session SET value = 'true' WHERE key = 'done'")
        conn.execute("UPDATE session SET value = 'button' WHERE key = 'done_reason'")
        conn.commit()
        conn.close()
        self._send_json({"ok": True})

    def _handle_closed(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE session SET value = 'true' WHERE key = 'done'")
        conn.execute("UPDATE session SET value = 'closed' WHERE key = 'done_reason'")
        conn.commit()
        conn.close()
        self._send_json({"ok": True})

    def _serve_status(self):
        conn = sqlite3.connect(self.db_path)
        done_row = conn.execute(
            "SELECT value FROM session WHERE key = 'done'"
        ).fetchone()
        reason_row = conn.execute(
            "SELECT value FROM session WHERE key = 'done_reason'"
        ).fetchone()
        heartbeat_row = conn.execute(
            "SELECT value FROM session WHERE key = 'last_heartbeat'"
        ).fetchone()
        conn.close()

        done = done_row[0] == "true" if done_row else False
        reason = reason_row[0] if reason_row and reason_row[0] else None

        # Check heartbeat timeout
        if not done and heartbeat_row and heartbeat_row[0]:
            try:
                last_hb = datetime.datetime.fromisoformat(heartbeat_row[0])
                now = datetime.datetime.now()
                elapsed = (now - last_hb).total_seconds()
                if elapsed > HEARTBEAT_TIMEOUT_SECONDS:
                    done = True
                    reason = "timeout"
            except (ValueError, TypeError):
                pass

        self._send_json({"done": done, "reason": reason})

    # -- Helpers --

    def _send_html(self, content):
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)


def init_db(db_path):
    """Initialize the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("INSERT OR REPLACE INTO session VALUES ('done', 'false')")
    conn.execute("INSERT OR REPLACE INTO session VALUES ('done_reason', '')")
    conn.execute(
        "INSERT OR REPLACE INTO session VALUES ('last_heartbeat', datetime('now'))"
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Bugshot gallery server")
    parser.add_argument("directory", help="Path to screenshot directory")
    parser.add_argument(
        "--bind", default="127.0.0.1",
        help="Address to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    directory = os.path.abspath(args.directory)
    if not os.path.isdir(directory):
        print(json.dumps({"error": f"Not a directory: {directory}"}), flush=True)
        sys.exit(1)

    images = discover_images(directory)
    if not images:
        print(
            json.dumps({"error": f"No recognized images in: {directory}"}),
            flush=True,
        )
        sys.exit(1)

    # Locate template and static directories relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, "templates")
    static_dir = os.path.join(script_dir, "static")

    # Create temp database
    db_fd, db_path = tempfile.mkstemp(prefix="bugshot_", suffix=".db")
    os.close(db_fd)
    atexit.register(lambda: os.unlink(db_path) if os.path.exists(db_path) else None)

    init_db(db_path)

    # Configure handler
    GalleryHandler.screenshot_dir = directory
    GalleryHandler.images = images
    GalleryHandler.db_path = db_path
    GalleryHandler.template_dir = template_dir
    GalleryHandler.static_dir = static_dir

    httpd = ThreadingHTTPServer((args.bind, 0), GalleryHandler)
    port = httpd.server_address[1]
    url = f"http://{args.bind}:{port}"

    print(json.dumps({
        "port": port,
        "url": url,
        "images": images,
    }), flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create template and static files**

Create `templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bugshot</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Bugshot</h1>
        <div class="controls">
            <button id="size-toggle" class="btn">Full Size</button>
            <button id="done-btn" class="btn btn-done">Done Reviewing</button>
        </div>
    </header>
    <div id="gallery" class="gallery thumbnail-mode">
        <!-- Populated by gallery.js -->
    </div>
    <script>
        window.__BUGSHOT_IMAGES__ = {{images_json}};
    </script>
    <script src="/static/gallery.js"></script>
</body>
</html>
```

Create `templates/detail.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bugshot — {{filename}}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <nav class="detail-nav">
            <a href="/" class="btn">Index</a>
            <span class="nav-arrows">
                <!-- Populated by gallery.js using nav data -->
            </span>
            <span class="filename">{{filename}}</span>
        </nav>
    </header>
    <main class="detail-main">
        <div class="detail-content">
            <div id="image-container">
                <!-- Image or ANSI content injected by gallery.js -->
            </div>
        </div>
        <div class="comment-section">
            <form id="comment-form">
                <input type="text" id="comment-input" placeholder="Describe an issue..." autocomplete="off">
                <button type="submit" class="btn">Submit</button>
            </form>
            <div id="comments-list">
                <!-- Populated by gallery.js -->
            </div>
        </div>
    </main>
    <div class="shortcut-hint">&larr; &rarr; navigate &middot; c comment &middot; esc back</div>
    <script>
        window.__BUGSHOT_DETAIL__ = {
            filename: "{{filename}}",
            encodedName: "{{encoded_name}}",
            contentType: "{{content_type}}",
            imageSrc: "{{image_src}}",
            ansiHtml: "{{ansi_html}}",
            nav: {{nav_json}}
        };
    </script>
    <script src="/static/gallery.js"></script>
</body>
</html>
```

Create `static/style.css`:

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    background: #1a1a1a;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
}

header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: #111;
    border-bottom: 1px solid #333;
}

header h1 {
    font-size: 18px;
    font-weight: 600;
}

.controls {
    display: flex;
    gap: 8px;
}

.btn {
    background: #333;
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    text-decoration: none;
    display: inline-block;
}

.btn:hover {
    background: #444;
}

.btn-done {
    background: #2a5a2a;
    border-color: #3a7a3a;
}

.btn-done:hover {
    background: #3a7a3a;
}

/* Index gallery */

.gallery {
    display: grid;
    gap: 16px;
    padding: 20px;
}

.gallery.thumbnail-mode {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.gallery.fullsize-mode {
    grid-template-columns: 1fr;
}

.gallery-item {
    background: #222;
    border: 1px solid #333;
    border-radius: 6px;
    overflow: hidden;
    cursor: pointer;
    transition: border-color 0.15s;
    display: block;
    text-decoration: none;
    color: inherit;
}

.gallery-item:hover {
    border-color: #666;
}

.gallery-item img {
    width: 100%;
    height: auto;
    display: block;
}

.gallery-item .ansi-preview {
    padding: 8px;
    overflow: hidden;
    max-height: 200px;
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;
    font-size: 11px;
    line-height: 1.3;
    background: #1a1a1a;
}

.fullsize-mode .gallery-item .ansi-preview {
    max-height: none;
}

.gallery-item .item-label {
    padding: 8px 12px;
    font-size: 12px;
    color: #999;
    border-top: 1px solid #333;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Detail view */

.detail-nav {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
}

.detail-nav .filename {
    margin-left: auto;
    color: #999;
    font-size: 13px;
}

.nav-arrows {
    display: flex;
    gap: 4px;
}

.detail-main {
    padding: 20px;
    max-width: 1400px;
    margin: 0 auto;
}

.detail-content {
    margin-bottom: 24px;
}

.detail-content img {
    max-width: 100%;
    height: auto;
}

.detail-content .ansi-rendered {
    padding: 16px;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 6px;
    overflow-x: auto;
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;
    font-size: 13px;
    line-height: 1.4;
}

/* Comments */

.comment-section {
    max-width: 800px;
}

#comment-form {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
}

#comment-input {
    flex: 1;
    background: #222;
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 14px;
}

#comment-input:focus {
    outline: none;
    border-color: #888;
}

#comments-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.comment-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 12px;
    background: #222;
    border: 1px solid #333;
    border-radius: 4px;
}

.comment-item .comment-body {
    flex: 1;
    font-size: 14px;
    line-height: 1.4;
}

.comment-item .comment-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
}

.comment-item .comment-actions button {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    font-size: 12px;
    padding: 2px 6px;
}

.comment-item .comment-actions button:hover {
    color: #e0e0e0;
}

/* Keyboard shortcut hint */
.shortcut-hint {
    position: fixed;
    bottom: 12px;
    right: 12px;
    color: #555;
    font-size: 11px;
}
```

Create `static/gallery.js`:

```javascript
(function () {
    "use strict";

    // ---- Constants ----
    var HEARTBEAT_INTERVAL_MS = 5000;

    // ---- Page detection ----
    var isIndex = !!window.__BUGSHOT_IMAGES__;
    var isDetail = !!window.__BUGSHOT_DETAIL__;
    var detail = window.__BUGSHOT_DETAIL__ || null;

    // ---- Heartbeat ----
    setInterval(function () {
        fetch("/api/heartbeat", { method: "POST" }).catch(function () {});
    }, HEARTBEAT_INTERVAL_MS);

    // ---- Browser close detection ----
    window.addEventListener("beforeunload", function () {
        navigator.sendBeacon("/api/closed");
    });

    // ---- Done button (index page) ----
    var doneBtn = document.getElementById("done-btn");
    if (doneBtn) {
        doneBtn.addEventListener("click", function () {
            if (confirm("Done reviewing? This will end the session.")) {
                fetch("/api/done", { method: "POST" })
                    .then(function () {
                        document.body.textContent = "";
                        var msg = document.createElement("div");
                        msg.style.cssText =
                            "display:flex;align-items:center;justify-content:center;" +
                            "height:100vh;color:#e0e0e0;font-size:18px;";
                        msg.textContent = "Session complete. You can close this tab.";
                        document.body.appendChild(msg);
                    });
            }
        });
    }

    // ---- Index page ----
    if (isIndex) {
        initIndex();
    }

    // ---- Detail page ----
    if (isDetail) {
        initDetail();
    }

    // ---- Keyboard shortcuts ----
    document.addEventListener("keydown", function (e) {
        var isTyping = document.activeElement &&
            (document.activeElement.tagName === "INPUT" ||
             document.activeElement.tagName === "TEXTAREA");

        if (isTyping) {
            if (e.key === "Escape") {
                document.activeElement.blur();
                e.preventDefault();
            }
            return;
        }

        if (isDetail) {
            if (e.key === "ArrowLeft" && detail.nav.prev) {
                window.location.href = detail.nav.prev;
                e.preventDefault();
            } else if (e.key === "ArrowRight" && detail.nav.next) {
                window.location.href = detail.nav.next;
                e.preventDefault();
            } else if (e.key === "Escape") {
                window.location.href = "/";
                e.preventDefault();
            } else if (e.key === "c") {
                var input = document.getElementById("comment-input");
                if (input) {
                    input.focus();
                    e.preventDefault();
                }
            }
        }
    });

    // ---- Index functions ----

    function initIndex() {
        var images = window.__BUGSHOT_IMAGES__;
        var gallery = document.getElementById("gallery");
        var sizeToggle = document.getElementById("size-toggle");

        // Render gallery items using DOM methods
        images.forEach(function (img) {
            var item = document.createElement("a");
            item.className = "gallery-item";
            item.href = "/view/" + img.encoded_name;

            if (img.type === "image") {
                var imgEl = document.createElement("img");
                imgEl.src = img.src;
                imgEl.alt = img.name;
                item.appendChild(imgEl);
            } else {
                // ANSI preview: server-rendered HTML, safe to inject
                var previewDiv = document.createElement("div");
                previewDiv.className = "ansi-preview";
                var pre = document.createElement("pre");
                pre.innerHTML = img.preview_html;
                previewDiv.appendChild(pre);
                item.appendChild(previewDiv);
            }

            var label = document.createElement("div");
            label.className = "item-label";
            label.textContent = img.name;
            item.appendChild(label);

            gallery.appendChild(item);
        });

        // Size toggle
        var isFullSize = false;
        sizeToggle.addEventListener("click", function () {
            isFullSize = !isFullSize;
            gallery.classList.toggle("thumbnail-mode", !isFullSize);
            gallery.classList.toggle("fullsize-mode", isFullSize);
            sizeToggle.textContent = isFullSize ? "Thumbnails" : "Full Size";
        });
    }

    // ---- Detail functions ----

    function initDetail() {
        var container = document.getElementById("image-container");
        var navArrows = document.querySelector(".nav-arrows");

        // Render image or ANSI content
        if (detail.contentType === "image") {
            var img = document.createElement("img");
            img.src = detail.imageSrc;
            img.alt = detail.filename;
            container.appendChild(img);
        } else {
            // ANSI content: server-rendered HTML, safe to inject
            var ansiDiv = document.createElement("div");
            ansiDiv.className = "ansi-rendered";
            var pre = document.createElement("pre");
            pre.innerHTML = detail.ansiHtml;
            ansiDiv.appendChild(pre);
            container.appendChild(ansiDiv);
        }

        // Render nav arrows using DOM methods
        if (detail.nav.prev) {
            var prevLink = document.createElement("a");
            prevLink.href = detail.nav.prev;
            prevLink.className = "btn";
            prevLink.id = "prev-btn";
            prevLink.textContent = "\u2190 " + detail.nav.prev_name;
            navArrows.appendChild(prevLink);
        }
        if (detail.nav.next) {
            var nextLink = document.createElement("a");
            nextLink.href = detail.nav.next;
            nextLink.className = "btn";
            nextLink.id = "next-btn";
            nextLink.textContent = detail.nav.next_name + " \u2192";
            navArrows.appendChild(nextLink);
        }

        // ---- Comments ----
        var commentForm = document.getElementById("comment-form");
        var commentInput = document.getElementById("comment-input");
        var commentsList = document.getElementById("comments-list");

        loadComments();

        commentForm.addEventListener("submit", function (e) {
            e.preventDefault();
            var body = commentInput.value.trim();
            if (!body) return;

            fetch("/api/comments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image: detail.filename, body: body }),
            })
                .then(function (r) { return r.json(); })
                .then(function (comment) {
                    commentInput.value = "";
                    appendComment(comment);
                });
        });

        function loadComments() {
            fetch("/api/comments?image=" + encodeURIComponent(detail.filename))
                .then(function (r) { return r.json(); })
                .then(function (comments) {
                    commentsList.textContent = "";
                    comments.forEach(appendComment);
                });
        }

        function appendComment(comment) {
            var item = document.createElement("div");
            item.className = "comment-item";
            item.dataset.id = comment.id;

            var bodyEl = document.createElement("span");
            bodyEl.className = "comment-body";
            bodyEl.textContent = comment.body;

            var actions = document.createElement("span");
            actions.className = "comment-actions";

            var editBtn = document.createElement("button");
            editBtn.textContent = "edit";
            editBtn.addEventListener("click", function () {
                var newBody = prompt("Edit comment:", comment.body);
                if (newBody !== null && newBody.trim()) {
                    fetch("/api/comments/" + comment.id, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ body: newBody.trim() }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (updated) {
                            bodyEl.textContent = updated.body;
                            comment.body = updated.body;
                        });
                }
            });

            var deleteBtn = document.createElement("button");
            deleteBtn.textContent = "delete";
            deleteBtn.addEventListener("click", function () {
                if (confirm("Delete this comment?")) {
                    fetch("/api/comments/" + comment.id, { method: "DELETE" })
                        .then(function () {
                            item.remove();
                        });
                }
            });

            actions.appendChild(editBtn);
            actions.appendChild(deleteBtn);
            item.appendChild(bodyEl);
            item.appendChild(actions);
            commentsList.appendChild(item);
        }
    }
})();
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_server.py -v`
Expected: all PASS

- [ ] **Step 6: Manual smoke test**

```bash
cd /home/ketan/project/bugshot
mkdir -p /tmp/test-screenshots
printf '\x1b[1;31mBold Red\x1b[0m\nPlain text\n\x1b[38;2;100;200;255mTruecolor\x1b[0m\n' > /tmp/test-screenshots/terminal.ansi
python3 gallery_server.py /tmp/test-screenshots
```
Expected: JSON printed to stdout. Open the URL — index page shows the ANSI preview. Click it to see the detail page with navigation and comment form.

- [ ] **Step 7: Commit**

```bash
git add gallery_server.py ansi_render.py static/ templates/ tests/
git commit -m "feat: gallery server with index, detail views, comments, ANSI rendering"
```

---

## Part 3: Comment System Tests

The comment API and UI were implemented in Part 2's monolithic server task. This part adds focused tests.

### Task 3.1: Comment CRUD Tests

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add comment CRUD tests**

Append to `tests/test_server.py`:

```python
def test_create_comment(server):
    url, info, proc = server
    status, body = _post_json(f"{url}/api/comments", {
        "image": "alpha.png",
        "body": "Button is misaligned",
    })
    assert status == 200
    assert body["id"] == 1
    assert body["image"] == "alpha.png"
    assert body["body"] == "Button is misaligned"
    assert "created_at" in body


def test_list_comments(server):
    url, info, proc = server
    _post_json(f"{url}/api/comments", {"image": "alpha.png", "body": "Issue 1"})
    _post_json(f"{url}/api/comments", {"image": "beta.png", "body": "Issue 2"})

    status, body = _get_json(f"{url}/api/comments")
    assert status == 200
    assert len(body) == 2
    assert body[0]["body"] == "Issue 1"
    assert body[1]["body"] == "Issue 2"


def test_list_comments_filtered_by_image(server):
    url, info, proc = server
    _post_json(f"{url}/api/comments", {"image": "alpha.png", "body": "Alpha issue"})
    _post_json(f"{url}/api/comments", {"image": "beta.png", "body": "Beta issue"})

    status, body = _get_json(f"{url}/api/comments?image=alpha.png")
    assert status == 200
    assert len(body) == 1
    assert body[0]["image"] == "alpha.png"

    # Without filter, returns all
    status, body = _get_json(f"{url}/api/comments")
    assert len(body) == 2


def test_update_comment(server):
    url, info, proc = server
    _post_json(f"{url}/api/comments", {"image": "alpha.png", "body": "Original"})

    status, body = _patch_json(f"{url}/api/comments/1", {"body": "Updated"})
    assert status == 200
    assert body["body"] == "Updated"

    status, comments = _get_json(f"{url}/api/comments")
    assert comments[0]["body"] == "Updated"


def test_delete_comment(server):
    url, info, proc = server
    _post_json(f"{url}/api/comments", {"image": "alpha.png", "body": "Delete me"})

    status = _delete(f"{url}/api/comments/1")
    assert status == 204

    status, comments = _get_json(f"{url}/api/comments")
    assert len(comments) == 0


def test_create_comment_missing_fields(server):
    url, info, proc = server
    status, body = _post_json(f"{url}/api/comments", {"image": "alpha.png"})
    assert status == 400


def test_update_nonexistent_comment(server):
    url, info, proc = server
    status, body = _patch_json(f"{url}/api/comments/999", {"body": "Nope"})
    assert status == 404


def test_delete_nonexistent_comment(server):
    url, info, proc = server
    status = _delete(f"{url}/api/comments/999")
    assert status == 404
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_server.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_server.py
git commit -m "test: add comment CRUD tests"
```

---

## Part 4: Session Lifecycle Tests

### Task 4.1: Lifecycle Endpoint Tests

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add lifecycle tests**

Append to `tests/test_server.py`:

```python
def test_heartbeat(server):
    url, info, proc = server
    status, body = _post_json(f"{url}/api/heartbeat", {})
    assert status == 200
    assert body["ok"] is True


def test_status_initially_not_done(server):
    url, info, proc = server
    status, body = _get_json(f"{url}/api/status")
    assert status == 200
    assert body["done"] is False
    assert body["reason"] is None


def test_done_button(server):
    url, info, proc = server
    _post_json(f"{url}/api/done", {})

    status, body = _get_json(f"{url}/api/status")
    assert body["done"] is True
    assert body["reason"] == "button"


def test_closed_signal(server):
    url, info, proc = server
    _post_json(f"{url}/api/closed", {})

    status, body = _get_json(f"{url}/api/status")
    assert body["done"] is True
    assert body["reason"] == "closed"


def test_heartbeat_keeps_session_alive(server):
    url, info, proc = server
    # Send a heartbeat
    _post_json(f"{url}/api/heartbeat", {})

    # Immediately check status — should not be timed out
    status, body = _get_json(f"{url}/api/status")
    assert body["done"] is False
```

- [ ] **Step 2: Run tests**

Run: `cd /home/ketan/project/bugshot && python -m pytest tests/test_server.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_server.py
git commit -m "test: add session lifecycle tests"
```

---

## Part 5: Skill Definition

### Task 5.1: Write SKILL.md

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: Write the skill definition**

Create `SKILL.md`:

````markdown
---
name: bugshot
description: Launch a screenshot gallery for visual bug review and issue filing
arguments:
  - name: directory
    description: Path to the directory containing screenshots
    required: true
---

# Bugshot — Screenshot Bug Filing Skill

Review screenshots in a browser gallery and file issues from user comments.

## Startup

1. Validate that `{{directory}}` exists and contains recognized files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ansi`).
2. Find the bugshot installation directory (the directory containing this SKILL.md).
3. Launch the gallery server:

```bash
python3 {{bugshot_dir}}/gallery_server.py {{directory}}
```

4. Read the startup JSON from stdout. It will be a single line:

```json
{"port": N, "url": "http://127.0.0.1:N", "images": ["file1.png", ...]}
```

5. Attempt to open the URL in the user's browser:

```python
import webbrowser
webbrowser.open(url)
```

If this fails (headless environment, SSH), tell the user the URL:
> Gallery is running at `http://127.0.0.1:<port>` — open this URL to review screenshots.

6. Tell the user:
> Bugshot gallery is open. Review the screenshots, type comments on any issues you see, then click "Done Reviewing" when finished.

## Wait for User

Poll `GET http://127.0.0.1:<port>/api/status` every 3 seconds.

The response will be:
```json
{"done": true, "reason": "button"|"timeout"|"closed"}
```

- If `reason` is `"button"`: user clicked Done. Proceed to processing.
- If `reason` is `"timeout"` or `"closed"`: the browser was closed. Confirm with the user:
  > It looks like you closed the browser. Are you done reviewing, or would you like to reopen the gallery?
  - If done: proceed to processing.
  - If reopen: open the URL again and resume polling.
- The user may also say "done" or equivalent in the terminal. If so, proceed to processing.

## Process Comments

1. Fetch all comments: `GET http://127.0.0.1:<port>/api/comments`

Response:
```json
[
  {"id": 1, "image": "login-page.png", "body": "Submit button is clipped", "created_at": "..."},
  ...
]
```

2. If no comments, report "No comments were submitted." and proceed to shutdown.

3. For each comment:

   **a. Examine the screenshot.**
   Read the image file at `{{directory}}/<comment.image>` using your vision capability. Identify:
   - What screen/page/view is shown
   - What UI elements are relevant to the user's comment
   - What specifically appears wrong or unexpected

   **b. Compose the issue.**
   Combine the user's comment with your visual analysis. If the project has issue templates, follow them. Otherwise use this structure:

   ```
   ## Current Behavior
   [What is happening, based on your examination of the screenshot + user's comment]

   ## Expected Behavior
   [What should happen instead, inferred from context]

   ## Screenshot Description
   [Detailed description of what the screenshot shows, sufficient for someone without access to the image]

   ## Additional Context
   - Screenshot: <comment.image>
   - User comment: "<comment.body>"
   ```

   **c. Check for duplicates.**
   Search existing issues (open and closed) using keywords from the composed issue. Use the project's issue-flow skill search capability.

   If potential duplicates are found, present them:
   > Found potential duplicates:
   > - #42: "Login button overflow on mobile" (open)
   > - #31: "Submit button CSS issue" (closed)
   >
   > File anyway, or skip?

   If the user says skip, move to the next comment.

   **d. Confirm with the user.**
   Show the composed issue in the terminal:
   > **Filing issue for `login-page.png`:**
   > [composed issue text]
   >
   > File this issue?

   If the user says no, allow them to edit or skip.

   **e. File the issue.**
   Delegate to the project's issue-flow skill to create the issue.

   **f. Attempt image attachment.**
   If the issue-flow skill or tracker supports attachments, attach the screenshot file. If attachment fails, report concisely:
   > Note: Could not attach screenshot to #42 (attachment not supported by tracker).

   **g. Report.**
   > Filed: #42 — "Login submit button is clipped on right edge"

4. After all comments are processed, summarize:
   > Bugshot session complete. Filed N issues, skipped M.

## Shutdown

Terminate the gallery server process. The temporary database is cleaned up automatically.

## Error Handling

- If the server fails to start, report the error from stderr and exit.
- If the server dies during the session, report it and offer to restart.
- If an issue fails to file, report the error and continue with the remaining comments.
````

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "feat: add bugshot skill definition"
```

---

## Part 6: Integration Testing and Project Setup

### Task 6.1: End-to-End Test Script

**Files:**
- Create: `tests/e2e_test.sh`

- [ ] **Step 1: Write the e2e test script**

Create `tests/e2e_test.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# End-to-end test for bugshot gallery server.
# Creates test data, starts the server, exercises all API endpoints,
# and verifies responses.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMPDIR="$(mktemp -d)"
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$TMPDIR"
}
trap cleanup EXIT

echo "=== Setting up test data ==="
python3 -c "
import os, struct, zlib
def make_png(path):
    raw = b'\x00\xff\x00\x00'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', zlib.compress(raw)))
        f.write(chunk(b'IEND', b''))
make_png('$TMPDIR/alpha.png')
make_png('$TMPDIR/beta.png')
"
printf '\x1b[1;31mBold Red Error\x1b[0m\n\x1b[32mGreen OK\x1b[0m\n' > "$TMPDIR/gamma.ansi"

echo "=== Starting server ==="
python3 "$SCRIPT_DIR/gallery_server.py" "$TMPDIR" > "$TMPDIR/server_output.txt" 2>&1 &
SERVER_PID=$!
sleep 1

STARTUP_JSON=$(head -1 "$TMPDIR/server_output.txt")
URL=$(echo "$STARTUP_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['url'])")
echo "Server running at $URL"

PASS=0
FAIL=0

check() {
    local name="$1" result="$2"
    if [ "$result" = "true" ]; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "=== Testing routes ==="

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/")
check "Index returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/view/alpha.png")
check "Detail returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/screenshots/alpha.png")
check "Screenshot returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/view/gamma.ansi")
check "ANSI detail returns 200" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)"

BODY=$(curl -s "$URL/view/gamma.ansi")
check "ANSI content rendered" "$(echo "$BODY" | grep -q "Bold Red Error" && echo true || echo false)"

echo ""
echo "=== Testing comment CRUD ==="

RESP=$(curl -s -X POST "$URL/api/comments" -H "Content-Type: application/json" -d '{"image":"alpha.png","body":"Test issue"}')
check "Comment created" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('id')==1 and d.get('body')=='Test issue' else 'false')")"

RESP=$(curl -s "$URL/api/comments")
check "Comment list" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if len(d)==1 else 'false')")"

RESP=$(curl -s "$URL/api/comments?image=alpha.png")
check "Comment filter" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if len(d)==1 else 'false')")"

RESP=$(curl -s -X PATCH "$URL/api/comments/1" -H "Content-Type: application/json" -d '{"body":"Updated issue"}')
check "Comment updated" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('body')=='Updated issue' else 'false')")"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$URL/api/comments/1")
check "Comment deleted" "$([ "$HTTP_CODE" = "204" ] && echo true || echo false)"

echo ""
echo "=== Testing session lifecycle ==="

RESP=$(curl -s -X POST "$URL/api/heartbeat" -H "Content-Type: application/json" -d '{}')
check "Heartbeat" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('ok') else 'false')")"

RESP=$(curl -s "$URL/api/status")
check "Status not done" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if not d.get('done') else 'false')")"

curl -s -X POST "$URL/api/done" -H "Content-Type: application/json" -d '{}' > /dev/null
RESP=$(curl -s "$URL/api/status")
check "Done after button" "$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('done') and d.get('reason')=='button' else 'false')")"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

- [ ] **Step 2: Run the e2e test**

```bash
chmod +x tests/e2e_test.sh
cd /home/ketan/project/bugshot && bash tests/e2e_test.sh
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e_test.sh
git commit -m "test: add end-to-end test script"
```

### Task 6.2: Project CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Create CLAUDE.md**

Create `CLAUDE.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with project overview and dev instructions"
```

---

## Execution Summary

| Part | Session Focus | Tasks | Key Deliverable |
|------|---------------|-------|-----------------|
| 1 | ANSI Renderer | 1.1, 1.2 | `ansi_render.py` with full color support, tested |
| 2 | Gallery Server + Frontend | 2.1 | Browsable gallery with comments, ANSI rendering, all routes |
| 3 | Comment Tests | 3.1 | Focused test coverage for comment CRUD |
| 4 | Lifecycle Tests | 4.1 | Focused test coverage for session lifecycle |
| 5 | Skill | 5.1 | SKILL.md for Claude Code integration |
| 6 | Integration + Setup | 6.1, 6.2 | E2E test script, CLAUDE.md |

Each part produces a working, committed increment. Parts can be executed in separate sessions. Later parts depend on earlier parts being complete. A fresh agent starting Part N should read the spec at `docs/specs/2026-04-15-bugshot-design.md` and this plan, then pick up at Part N.

"""Convert ANSI escape sequences to styled HTML spans."""

import html
import re
from dataclasses import dataclass
from typing import Optional

# --- Color palettes ---------------------------------------------------------

COLORS_16 = [
    "#000000", "#c91b00", "#00c200", "#c7c400",
    "#0225c7", "#c930c7", "#00c5c7", "#c7c7c7",
    "#686868", "#ff6e67", "#5ffa68", "#fffc67",
    "#6871ff", "#ff77ff", "#60fdff", "#ffffff",
]

DEFAULT_FG = "#e0e0e0"
DEFAULT_BG = "#1a1a1a"

# --- Regex patterns ---------------------------------------------------------

# Matches any ANSI escape sequence (SGR, cursor movement, OSC, etc.)
_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-9;?<=>]*[A-Za-z]|\][^\x07]*\x07|\[[\x20-\x2f]*[\x40-\x7e])"
)

# Matches only SGR sequences (ESC [ ... m)
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# --- 256-color palette constants --------------------------------------------

_CUBE_START = 16          # First 256-color cube index
_CUBE_SIZE = 216          # Number of cube colors (6*6*6)
_CUBE_STEPS = 6           # Steps per channel
_CUBE_CHANNEL_OFFSET = 55 # Xterm cube channel base for non-zero values
_CUBE_CHANNEL_STEP = 40   # Xterm cube channel step
_GRAYSCALE_START = 232    # First grayscale index
_GRAYSCALE_BASE = 8       # First grayscale luminance value
_GRAYSCALE_STEP = 10      # Grayscale luminance step

# --- Color lookup -----------------------------------------------------------

def _color_256(index: int) -> str:
    """Return a CSS hex color string for a 256-color palette index."""
    if index < 16:
        return COLORS_16[index]
    if index < _GRAYSCALE_START:
        # 6x6x6 color cube: indices 16-231
        cube_index = index - _CUBE_START
        b = cube_index % _CUBE_STEPS
        g = (cube_index // _CUBE_STEPS) % _CUBE_STEPS
        r = cube_index // (_CUBE_STEPS * _CUBE_STEPS)
        r_val = 0 if r == 0 else _CUBE_CHANNEL_OFFSET + r * _CUBE_CHANNEL_STEP
        g_val = 0 if g == 0 else _CUBE_CHANNEL_OFFSET + g * _CUBE_CHANNEL_STEP
        b_val = 0 if b == 0 else _CUBE_CHANNEL_OFFSET + b * _CUBE_CHANNEL_STEP
        return f"#{r_val:02x}{g_val:02x}{b_val:02x}"
    # Grayscale ramp: indices 232-255
    value = _GRAYSCALE_BASE + (index - _GRAYSCALE_START) * _GRAYSCALE_STEP
    return f"#{value:02x}{value:02x}{value:02x}"

# --- State ------------------------------------------------------------------

@dataclass
class _State:
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    inverse: bool = False
    fg: Optional[str] = None  # None means default
    bg: Optional[str] = None  # None means default

    def reset(self) -> None:
        self.bold = False
        self.dim = False
        self.italic = False
        self.underline = False
        self.strikethrough = False
        self.inverse = False
        self.fg = None
        self.bg = None

    def effective_fg(self) -> str:
        fg = self.fg if self.fg is not None else DEFAULT_FG
        bg = self.bg if self.bg is not None else DEFAULT_BG
        return bg if self.inverse else fg

    def effective_bg(self) -> str:
        fg = self.fg if self.fg is not None else DEFAULT_FG
        bg = self.bg if self.bg is not None else DEFAULT_BG
        return fg if self.inverse else bg

    def css(self) -> str:
        """Build a CSS style string for the current state (empty if default)."""
        parts: list[str] = []

        if self.bold:
            parts.append("font-weight:bold")
        if self.dim:
            parts.append("opacity:0.5")
        if self.italic:
            parts.append("font-style:italic")

        text_decorations: list[str] = []
        if self.underline:
            text_decorations.append("underline")
        if self.strikethrough:
            text_decorations.append("line-through")
        if text_decorations:
            parts.append(f"text-decoration:{' '.join(text_decorations)}")

        # Colors (apply inverse via effective_* helpers only when non-default)
        eff_fg = self.effective_fg()
        eff_bg = self.effective_bg()

        if eff_fg != DEFAULT_FG:
            parts.append(f"color:{eff_fg}")
        if eff_bg != DEFAULT_BG:
            parts.append(f"background-color:{eff_bg}")

        return ";".join(parts)

# --- SGR parameter processing -----------------------------------------------

def _apply_sgr(state: _State, params: list[int]) -> None:
    """Apply a list of SGR parameter integers to a state object in-place."""
    i = 0
    while i < len(params):
        code = params[i]

        if code == 0:
            state.reset()
        elif code == 1:
            state.bold = True
        elif code == 2:
            state.dim = True
        elif code == 3:
            state.italic = True
        elif code == 4:
            state.underline = True
        elif code == 9:
            state.strikethrough = True
        elif code == 7:
            state.inverse = True
        elif code == 22:
            state.bold = False
            state.dim = False
        elif code == 23:
            state.italic = False
        elif code == 24:
            state.underline = False
        elif code == 27:
            state.inverse = False
        elif code == 29:
            state.strikethrough = False
        elif 30 <= code <= 37:
            state.fg = COLORS_16[code - 30]
        elif code == 38:
            color, consumed = _parse_extended_color(params, i + 1)
            if color is not None:
                state.fg = color
            i += consumed
        elif code == 39:
            state.fg = None
        elif 40 <= code <= 47:
            state.bg = COLORS_16[code - 40]
        elif code == 48:
            color, consumed = _parse_extended_color(params, i + 1)
            if color is not None:
                state.bg = color
            i += consumed
        elif code == 49:
            state.bg = None
        elif 90 <= code <= 97:
            state.fg = COLORS_16[8 + (code - 90)]
        elif 100 <= code <= 107:
            state.bg = COLORS_16[8 + (code - 100)]

        i += 1


def _parse_extended_color(params: list[int], start: int) -> tuple[Optional[str], int]:
    """Parse 256-color or 24-bit color params starting at ``start``.

    Returns ``(color_hex, number_of_extra_params_consumed)``.
    """
    if start >= len(params):
        return None, 0

    mode = params[start]

    if mode == 5:
        # 256-color: 38;5;N
        if start + 1 < len(params):
            return _color_256(params[start + 1]), 2
        return None, 1

    if mode == 2:
        # 24-bit truecolor: 38;2;R;G;B
        if start + 3 < len(params):
            r, g, b = params[start + 1], params[start + 2], params[start + 3]
            return f"#{r:02x}{g:02x}{b:02x}", 4
        return None, len(params) - start

    return None, 1


# --- Public API -------------------------------------------------------------

def ansi_to_html(text: str) -> str:
    """Convert a string containing ANSI escape sequences to HTML.

    Text content is HTML-escaped. ANSI SGR sequences are translated to
    ``<span style="...">`` elements. All other ANSI sequences are stripped.
    """
    state = _State()
    span_open = False
    output: list[str] = []

    def close_span() -> None:
        nonlocal span_open
        if span_open:
            output.append("</span>")
            span_open = False

    def open_span() -> None:
        nonlocal span_open
        css = state.css()
        if css:
            output.append(f'<span style="{css}">')
            span_open = True

    pos = 0
    for match in _ANSI_RE.finditer(text):
        start, end = match.start(), match.end()

        # Emit any plain text before this escape sequence
        if pos < start:
            close_span()
            open_span()
            output.append(html.escape(text[pos:start]))

        # Is this an SGR sequence?
        sgr_match = _SGR_RE.fullmatch(match.group())
        if sgr_match:
            raw = sgr_match.group(1)
            if raw == "" or raw == "0":
                close_span()
                state.reset()
            else:
                close_span()
                params = [int(p) for p in raw.split(";") if p != ""]
                _apply_sgr(state, params)
        # Non-SGR sequences are silently dropped.

        pos = end

    # Emit any trailing plain text
    if pos < len(text):
        close_span()
        open_span()
        output.append(html.escape(text[pos:]))

    close_span()
    return "".join(output)

"""Bugshot gallery server.

Usage: python3 gallery_server.py /path/to/review-root [--bind ADDRESS | --local-only]
"""

import argparse
import atexit
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ANSI_EXTENSION = ".ansi"
METADATA_EXTENSION = ".json"
UNIT_MANIFEST_FILENAME = "bugshot-unit.json"
RECOGNIZED_EXTENSIONS = IMAGE_EXTENSIONS | {ANSI_EXTENSION}

HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_TIMEOUT_SECONDS = 15


def discover_images(directory):
    """Return sorted list of recognized filenames in directory.

    Only regular files count. A directory whose name happens to end in a
    recognized extension (e.g. vizdiff's per-unit `pages__login.png/`) is
    not a flat-mode image.
    """
    names = []
    for name in os.listdir(directory):
        ext = os.path.splitext(name)[1].lower()
        if ext not in RECOGNIZED_EXTENSIONS:
            continue
        if not os.path.isfile(os.path.join(directory, name)):
            continue
        names.append(name)
    names.sort()
    return names


def discover_review_units(directory):
    """Return review units from a flat image directory or grouped child directories."""
    flat_images = discover_images(directory)
    if flat_images:
        return [_build_single_image_unit(name) for name in flat_images]

    units = []
    for child_name in sorted(os.listdir(directory)):
        child_path = os.path.join(directory, child_name)
        if not os.path.isdir(child_path):
            continue

        manifest = _load_unit_manifest(child_path, child_name)
        asset_names = _discover_manifest_assets(child_path, child_name, manifest)
        if not asset_names:
            continue

        assets = [_build_asset(relative_dir=child_name, name=name) for name in asset_names]
        metadata = _discover_manifest_metadata(
            child_path,
            child_name,
            manifest,
        )
        units.append(_build_grouped_unit(child_name, assets, metadata, manifest))

    return units


def _build_single_image_unit(name):
    asset = _build_asset(relative_dir="", name=name)
    return {
        "id": name,
        "label": name,
        "relative_dir": "",
        "assets": [asset],
        "metadata": [],
        "primary_asset_relative_path": asset["relative_path"],
        "reference_asset_relative_path": None,
    }


def _build_grouped_unit(unit_id, assets, metadata, manifest):
    if manifest and manifest.get("assets") is not None:
        ordered_assets = assets
    else:
        ordered_assets = sorted(
            assets,
            key=lambda asset: (_asset_priority(asset["name"]), asset["name"]),
        )
    return {
        "id": unit_id,
        "label": manifest.get("label") or unit_id if manifest else unit_id,
        "relative_dir": unit_id,
        "assets": ordered_assets,
        "metadata": metadata,
        "primary_asset_relative_path": ordered_assets[0]["relative_path"],
        "reference_asset_relative_path": _manifest_reference_asset_relative_path(
            unit_id,
            ordered_assets,
            manifest,
        ),
    }


def _build_asset(relative_dir, name):
    relative_path = name if not relative_dir else f"{relative_dir}/{name}"
    ext = os.path.splitext(name)[1].lower()
    return {
        "name": name,
        "relative_path": relative_path,
        "type": _asset_type_for_extension(ext),
    }


def _asset_type_for_extension(ext):
    if ext == ANSI_EXTENSION:
        return "ansi"
    if ext == ".svg":
        return "svg"
    return "image"


def _discover_metadata_files(directory, relative_dir):
    metadata = []
    for name in sorted(os.listdir(directory)):
        if name == UNIT_MANIFEST_FILENAME:
            continue
        if os.path.splitext(name)[1].lower() != METADATA_EXTENSION:
            continue

        absolute_path = os.path.join(directory, name)
        relative_path = name if not relative_dir else f"{relative_dir}/{name}"
        metadata.append(_build_metadata(relative_path, name, absolute_path))
    return metadata


def _load_unit_manifest(directory, unit_id):
    manifest_path = os.path.join(directory, UNIT_MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid manifest for unit {unit_id}: {error}") from error

    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid manifest for unit {unit_id}: root must be an object")

    label = manifest.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(f"Invalid manifest for unit {unit_id}: label must be a string")

    assets = _validate_manifest_entries(
        manifest.get("assets"),
        unit_id,
        field_name="assets",
        required_extension_set=RECOGNIZED_EXTENSIONS,
    )
    metadata = _validate_manifest_entries(
        manifest.get("metadata"),
        unit_id,
        field_name="metadata",
        required_extension_set={METADATA_EXTENSION},
    )
    reference_asset = _validate_manifest_reference_asset(
        manifest.get("reference_asset"),
        unit_id,
    )

    return {
        "label": label,
        "assets": assets,
        "metadata": metadata,
        "reference_asset": reference_asset,
    }


def _validate_manifest_entries(value, unit_id, field_name, required_extension_set):
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"Invalid manifest for unit {unit_id}: {field_name} must be a non-empty list"
        )

    entries = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"Invalid manifest for unit {unit_id}: {field_name} entries must be strings"
            )
        if item != os.path.basename(item) or "/" in item or "\\" in item:
            raise ValueError(
                f"Invalid manifest for unit {unit_id}: {field_name} entries must be direct child filenames"
            )
        ext = os.path.splitext(item)[1].lower()
        if ext not in required_extension_set:
            raise ValueError(
                f"Invalid manifest for unit {unit_id}: unsupported {field_name[:-1]} file {item}"
            )
        entries.append(item)
    return entries


def _validate_manifest_reference_asset(value, unit_id):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid manifest for unit {unit_id}: reference_asset must be a string"
        )
    if value != os.path.basename(value) or "/" in value or "\\" in value:
        raise ValueError(
            f"Invalid manifest for unit {unit_id}: reference_asset must be a direct child filename"
        )
    ext = os.path.splitext(value)[1].lower()
    if ext not in RECOGNIZED_EXTENSIONS:
        raise ValueError(
            f"Invalid manifest for unit {unit_id}: unsupported reference_asset file {value}"
        )
    return value


def _discover_manifest_assets(directory, unit_id, manifest):
    asset_names = manifest.get("assets") if manifest else None
    if asset_names is None:
        return discover_images(directory)

    for name in asset_names:
        absolute_path = os.path.join(directory, name)
        if not os.path.isfile(absolute_path):
            raise ValueError(
                f"Invalid manifest for unit {unit_id}: asset file not found: {name}"
            )
    return asset_names


def _manifest_reference_asset_relative_path(unit_id, assets, manifest):
    if not manifest:
        return None
    reference_asset = manifest.get("reference_asset")
    if reference_asset is None:
        return None

    asset_relative_paths = {asset["name"]: asset["relative_path"] for asset in assets}
    if reference_asset not in asset_relative_paths:
        raise ValueError(
            f"Invalid manifest for unit {unit_id}: reference_asset must name one of the unit assets"
        )
    return asset_relative_paths[reference_asset]


def _discover_manifest_metadata(directory, relative_dir, manifest):
    metadata_names = manifest.get("metadata") if manifest else None
    if metadata_names is None:
        return _discover_metadata_files(directory, relative_dir=relative_dir)

    metadata = []
    for name in metadata_names:
        absolute_path = os.path.join(directory, name)
        if not os.path.isfile(absolute_path):
            unit_id = relative_dir or os.path.basename(directory)
            raise ValueError(
                f"Invalid manifest for unit {unit_id}: metadata file not found: {name}"
            )
        relative_path = name if not relative_dir else f"{relative_dir}/{name}"
        metadata.append(_build_metadata(relative_path, name, absolute_path))
    return metadata


def _build_metadata(relative_path, name, absolute_path):
    content_text = ""
    parsed_content = None
    parse_error = None

    try:
        with open(absolute_path, "r", encoding="utf-8") as f:
            content_text = f.read()
        parsed_content = json.loads(content_text)
        display_text = json.dumps(parsed_content, indent=2, sort_keys=True)
    except (OSError, json.JSONDecodeError) as error:
        parse_error = str(error)
        display_text = content_text

    return {
        "name": name,
        "relative_path": relative_path,
        "content": parsed_content,
        "display_text": display_text,
        "parse_error": parse_error,
    }


def _asset_priority(name):
    stem = os.path.splitext(name)[0].lower()
    if stem in ("reference", "source", "original", "input", "baseline"):
        return 0
    return 1


def _render_ansi(absolute_path):
    from ansi_render import ansi_to_html

    with open(absolute_path, "r", encoding="utf-8") as f:
        return ansi_to_html(f.read())


def _read_svg_info(absolute_path):
    with open(absolute_path, "r", encoding="utf-8") as f:
        svg_markup = f.read()
    return {
        "markup": svg_markup,
        "primary_color": _primary_svg_color(svg_markup),
    }


def _primary_svg_color(svg_markup):
    counts = {}
    for match in re.finditer(r'\b(fill|stroke)="([^"]+)"', svg_markup):
        color = _normalize_svg_color(match.group(2))
        if color:
            counts[color] = counts.get(color, 0) + 1

    for match in re.finditer(r'\bstyle="([^"]+)"', svg_markup):
        for declaration in match.group(1).split(";"):
            if ":" not in declaration:
                continue
            key, value = declaration.split(":", 1)
            if key.strip() not in {"fill", "stroke"}:
                continue
            color = _normalize_svg_color(value.strip())
            if color:
                counts[color] = counts.get(color, 0) + 1

    if not counts:
        return None
    return max(sorted(counts), key=lambda item: counts[item])


def _normalize_svg_color(value):
    if not value:
        return None

    normalized = value.strip().lower()
    if normalized in {"none", "transparent", "currentcolor", "inherit"}:
        return None

    if re.match(r"^#[0-9a-f]{3}$", normalized):
        return "#" + "".join(ch * 2 for ch in normalized[1:])

    if re.match(r"^#[0-9a-f]{6}$", normalized):
        return normalized

    rgb_match = re.match(
        r"^rgb\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*\)$",
        normalized,
    )
    if rgb_match:
        channels = [max(0, min(255, int(group))) for group in rgb_match.groups()]
        return "#{:02x}{:02x}{:02x}".format(*channels)

    return None


def _safe_relative_path(path):
    normalized = os.path.normpath(urllib.parse.unquote(path)).replace("\\", "/")
    if normalized in {".", ""}:
        return ""
    if normalized.startswith("../") or normalized == ".." or os.path.isabs(normalized):
        return None
    return normalized.lstrip("/")


def _absolute_path(root, relative_path):
    root = os.path.abspath(root)
    path = os.path.abspath(os.path.join(root, relative_path))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return path


VIZDIFF_SCHEMA = "bugshot.vizdiff/v1"
VIZDIFF_FIELDS = (
    "classification",
    "relative_path",
    "base_asset",
    "head_asset",
    "base_sha256",
    "head_sha256",
    "base_ref",
    "base_sha",
    "head_sha",
)


def _vizdiff_block(unit):
    """Return a flat dict of vizdiff fields if the unit carries the schema, else None."""
    for meta in unit.get("metadata", []):
        content = meta.get("content")
        if isinstance(content, dict) and content.get("schema") == VIZDIFF_SCHEMA:
            return {field: content.get(field) for field in VIZDIFF_FIELDS}
    return None


def _serialize_asset_payload(asset, review_root):
    absolute_path = _absolute_path(review_root, asset["relative_path"])
    payload = {
        "name": asset["name"],
        "relative_path": asset["relative_path"],
        "type": asset["type"],
        "src": f"/screenshots/{urllib.parse.quote(asset['relative_path'])}",
    }
    if asset["type"] == "ansi":
        payload["rendered_html"] = _render_ansi(absolute_path)
    elif asset["type"] == "svg":
        svg_info = _read_svg_info(absolute_path)
        payload["svg_markup"] = svg_info["markup"]
        payload["primary_color"] = svg_info["primary_color"]
    return payload


def unit_index_payload(unit, review_root):
    """Serialize a unit for the index-page client payload.

    Adds a `vizdiff` block when the unit carries the bugshot.vizdiff/v1 schema.
    """
    asset = _serialize_asset_payload(unit["assets"][0], review_root)
    payload = {
        "id": unit["id"],
        "label": unit["label"],
        "encoded_id": urllib.parse.quote(unit["id"]),
        "asset_count": len(unit["assets"]),
        "metadata_count": len(unit["metadata"]),
        "primary_asset": asset,
    }
    vizdiff = _vizdiff_block(unit)
    if vizdiff is not None:
        payload["vizdiff"] = vizdiff
    return payload


def unit_detail_payload(unit, review_root):
    """Serialize a unit for the detail-page client payload."""
    payload = {
        "id": unit["id"],
        "label": unit["label"],
        "assets": [_serialize_asset_payload(a, review_root) for a in unit["assets"]],
        "metadata": [
            {
                "name": item["name"],
                "relative_path": item["relative_path"],
                "content": item["content"],
                "display_text": item["display_text"],
                "parse_error": item["parse_error"],
            }
            for item in unit["metadata"]
        ],
    }
    vizdiff = _vizdiff_block(unit)
    if vizdiff is not None:
        payload["vizdiff"] = vizdiff
    return payload


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class GalleryHandler(SimpleHTTPRequestHandler):
    """Routes requests to the appropriate handler."""

    review_root = None
    units = None
    units_by_id = None
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
        elif path == "/api/comments":
            self._handle_comment_list(parsed.query)
        elif path.startswith("/view/"):
            unit_id = path[len("/view/"):]
            self._serve_detail(unit_id)
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        elif path.startswith("/screenshots/"):
            self._serve_asset(path[len("/screenshots/"):])
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

    def _serve_index(self):
        template_path = os.path.join(self.template_dir, "index.html")
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        unit_items = [self._serialize_unit_for_index(unit) for unit in self.units]
        content = template.replace("{{units_json}}", json.dumps(unit_items))
        self._send_html(content)

    def _serve_detail(self, unit_id):
        unit = self.units_by_id.get(unit_id)
        if unit is None:
            self.send_error(404, f"Unit not found: {unit_id}")
            return

        template_path = os.path.join(self.template_dir, "detail.html")
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        idx = self.units.index(unit)
        prev_unit = self.units[idx - 1] if idx > 0 else None
        next_unit = self.units[idx + 1] if idx < len(self.units) - 1 else None

        nav = {
            "prev": f"/view/{urllib.parse.quote(prev_unit['id'])}" if prev_unit else None,
            "next": f"/view/{urllib.parse.quote(next_unit['id'])}" if next_unit else None,
            "prev_label": prev_unit["label"] if prev_unit else None,
            "next_label": next_unit["label"] if next_unit else None,
        }
        detail_units = [
            {
                "id": item["id"],
                "label": item["label"],
                "encoded_id": urllib.parse.quote(item["id"]),
            }
            for item in self.units
        ]

        replacements = {
            "{{unit_label}}": unit["label"],
            "{{unit_json}}": json.dumps(self._serialize_unit_for_detail(unit)),
            "{{nav_json}}": json.dumps(nav),
            "{{units_json}}": json.dumps(detail_units),
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

    def _serve_asset(self, relative_path):
        safe_relative_path = _safe_relative_path(relative_path)
        if not safe_relative_path:
            self.send_error(404)
            return

        filepath = _absolute_path(self.review_root, safe_relative_path)
        if filepath is None or not os.path.isfile(filepath):
            self.send_error(404)
            return

        ext = os.path.splitext(filepath)[1].lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        ctype = content_types.get(ext, "application/octet-stream")

        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_comment_list(self, query):
        params = urllib.parse.parse_qs(query)
        unit_id = (
            params.get("unit_id", [None])[0]
            or params.get("unit", [None])[0]
            or params.get("image", [None])[0]
        )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if unit_id:
                rows = conn.execute(
                    "SELECT id, unit_id, body, region, created_at FROM comments "
                    "WHERE unit_id = ? ORDER BY id",
                    (unit_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, unit_id, body, region, created_at FROM comments ORDER BY id"
                ).fetchall()
        finally:
            conn.close()

        items = []
        for row in rows:
            item = dict(row)
            item["region"] = json.loads(item["region"]) if item["region"] else None
            items.append(item)
        self._send_json(items)

    def _handle_comment_create(self):
        data = self._read_json_body()
        unit_id = data.get("unit_id") or data.get("unit") or data.get("image")
        body = data.get("body")
        if not unit_id or not body:
            self._send_json({"error": "unit_id and body are required"}, status=400)
            return
        if unit_id not in self.units_by_id:
            self._send_json({"error": f"unknown unit_id: {unit_id}"}, status=400)
            return

        region = data.get("region")
        region_text = json.dumps(region) if region is not None else None

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO comments (unit_id, body, region) VALUES (?, ?, ?)",
            (unit_id, body, region_text),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, unit_id, body, region, created_at FROM comments WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        conn.close()

        item = dict(row)
        item["region"] = json.loads(item["region"]) if item["region"] else None
        self._send_json(item)

    def _handle_comment_update(self, comment_id):
        data = self._read_json_body()
        body = data.get("body")
        if not body:
            self._send_json({"error": "body is required"}, status=400)
            return

        region_supplied = "region" in data
        region_text = (
            json.dumps(data["region"])
            if region_supplied and data["region"] is not None
            else None
        )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if region_supplied:
            conn.execute(
                "UPDATE comments SET body = ?, region = ? WHERE id = ?",
                (body, region_text, comment_id),
            )
        else:
            conn.execute(
                "UPDATE comments SET body = ? WHERE id = ?",
                (body, comment_id),
            )
        conn.commit()
        row = conn.execute(
            "SELECT id, unit_id, body, region, created_at FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone()
        conn.close()

        if row is None:
            self._send_json({"error": "not found"}, status=404)
            return

        item = dict(row)
        item["region"] = json.loads(item["region"]) if item["region"] else None
        self._send_json(item)

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

    def _serialize_unit_for_index(self, unit):
        return unit_index_payload(unit, self.review_root)

    def _serialize_unit_for_detail(self, unit):
        return unit_detail_payload(unit, self.review_root)

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            body TEXT NOT NULL,
            region TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute("INSERT OR REPLACE INTO session VALUES ('done', 'false')")
    conn.execute("INSERT OR REPLACE INTO session VALUES ('done_reason', '')")
    conn.execute(
        "INSERT OR REPLACE INTO session VALUES ('last_heartbeat', datetime('now'))"
    )
    conn.commit()
    conn.close()


class GalleryServer:
    """Running gallery server. Holds httpd, serving thread, and resources."""

    def __init__(self, httpd, thread, url, db_path, units, review_root):
        self.httpd = httpd
        self.thread = thread
        self.url = url
        self.db_path = db_path
        self.units = units
        self.images = [unit["id"] for unit in units]
        self.screenshot_dir = review_root

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def create_server(screenshot_dir, bind_address="0.0.0.0"):
    """Create and start a gallery server in a background thread."""
    directory = os.path.abspath(screenshot_dir)
    if not os.path.isdir(directory):
        raise ValueError(f"Not a directory: {directory}")

    units = discover_review_units(directory)
    if not units:
        raise ValueError(f"No recognized review units in: {directory}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, "templates")
    static_dir = os.path.join(script_dir, "static")

    db_fd, db_path = tempfile.mkstemp(prefix="bugshot_", suffix=".db")
    os.close(db_fd)
    init_db(db_path)

    handler_cls = type(
        "BoundGalleryHandler",
        (GalleryHandler,),
        {
            "review_root": directory,
            "units": units,
            "units_by_id": {unit["id"]: unit for unit in units},
            "db_path": db_path,
            "template_dir": template_dir,
            "static_dir": static_dir,
        },
    )

    httpd = ThreadingHTTPServer((bind_address, 0), handler_cls)
    port = httpd.server_address[1]
    url = f"http://{bind_address}:{port}"

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    return GalleryServer(httpd, thread, url, db_path, units, directory)


def main():
    parser = argparse.ArgumentParser(description="Bugshot gallery server")
    parser.add_argument("directory", help="Path to screenshot directory")
    bind_group = parser.add_mutually_exclusive_group()
    bind_group.add_argument(
        "--bind",
        default="0.0.0.0",
        help="Address to bind to (default: 0.0.0.0, all interfaces)",
    )
    bind_group.add_argument(
        "--local-only",
        action="store_true",
        help="Shortcut for --bind 127.0.0.1 (loopback only)",
    )
    args = parser.parse_args()

    bind_address = "127.0.0.1" if args.local_only else args.bind

    try:
        server = create_server(args.directory, bind_address=bind_address)
    except ValueError as error:
        print(json.dumps({"error": str(error)}), flush=True)
        sys.exit(1)

    atexit.register(
        lambda: os.unlink(server.db_path) if os.path.exists(server.db_path) else None
    )

    print(
        json.dumps(
            {
                "port": server.httpd.server_address[1],
                "url": server.url,
                "images": server.images,
                "units": [unit["id"] for unit in server.units],
            }
        ),
        flush=True,
    )

    try:
        server.thread.join()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

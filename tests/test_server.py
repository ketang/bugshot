import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

import gallery_server


def _post_json(url, data):
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


def _get_json(url):
    try:
        resp = urllib.request.urlopen(url)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _patch_json(url, data):
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
    req = urllib.request.Request(url, method="DELETE")
    try:
        resp = urllib.request.urlopen(req)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def _read_comments(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, unit_id, body, region, created_at FROM comments ORDER BY id"
        ).fetchall()]
    finally:
        conn.close()


def _read_session(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            key: value
            for key, value in conn.execute("SELECT key, value FROM session").fetchall()
        }
    finally:
        conn.close()


def test_server_exposes_images(server):
    assert server.images == ["alpha.png", "beta.png", "delta.ansi", "gamma.jpg"]


def test_server_exposes_grouped_units(grouped_server):
    assert [unit["id"] for unit in grouped_server.units] == [
        "login-button",
        "settings-panel",
    ]
    assert [unit["label"] for unit in grouped_server.units] == [
        "Login Button Review",
        "Settings Panel Review",
    ]
    assert [asset["name"] for asset in grouped_server.units[0]["assets"]] == [
        "candidate.png",
        "final.svg",
        "reference.png",
    ]
    assert grouped_server.units[0]["reference_asset_relative_path"] == (
        "login-button/reference.png"
    )
    assert [item["name"] for item in grouped_server.units[0]["metadata"]] == [
        "report.json",
    ]


def test_index_page_returns_200(server):
    resp = urllib.request.urlopen(f"{server.url}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert "alpha.png" in body
    assert "beta.png" in body


def test_grouped_index_page_returns_200(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert "Login Button Review" in body
    assert "Settings Panel Review" in body


def test_detail_page_exposes_copy_filename_control(server):
    resp = urllib.request.urlopen(f"{server.url}/view/alpha.png")
    assert resp.status == 200
    body = resp.read().decode()
    assert 'id="copy-filename-btn"' in body
    assert 'class="copy-filename-icon"' in body
    assert "<span>Copy</span>" in body
    assert "alpha.png" in body
    assert 'class="detail-shortcut-legend"' in body
    assert ">c</span> copy filename" in body
    # Flat-mode review root (single-image units): no '/ unit id' suffix.
    assert "/ unit id" not in body
    assert ">n/.</span> next" in body
    assert ">p/,</span> previous" in body


def test_grouped_detail_page_renders_assets_and_metadata(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/view/login-button")
    assert resp.status == 200
    body = resp.read().decode()
    assert "Login Button Review" in body
    assert "reference.png" in body
    assert "candidate.png" in body
    assert "final.svg" in body
    assert "report.json" in body
    assert "comparison" in body
    assert "bugshot-unit.json" not in body
    assert body.index('id="comment-form"') < body.index('id="unit-metadata"')
    assert 'id="detail-theme-controls"' in body
    assert '"primary_color": "#111111"' in body


def test_grouped_detail_page_legend_keeps_unit_id_label(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/view/login-button")
    body = resp.read().decode()
    # Grouped review units: filename != unit id, so the disambiguating
    # '/ unit id' suffix on the copy-filename shortcut must remain.
    assert ">c</span> copy filename / unit id" in body


def test_grouped_svg_asset_serves_with_svg_content_type(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/screenshots/login-button/final.svg")
    assert resp.status == 200
    assert resp.headers.get_content_type() == "image/svg+xml"
    assert "<svg" in resp.read().decode()


def test_invalid_manifest_raises_value_error(tmp_path):
    unit_dir = tmp_path / "broken-unit"
    unit_dir.mkdir()
    (unit_dir / "reference.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (unit_dir / "bugshot-unit.json").write_text(
        '{"assets":["missing.png"]}',
        encoding="utf-8",
    )

    try:
        gallery_server.create_server(str(tmp_path))
    except ValueError as error:
        assert "missing.png" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid manifest")


def test_reference_asset_must_be_declared_in_assets(tmp_path):
    unit_dir = tmp_path / "broken-unit"
    unit_dir.mkdir()
    (unit_dir / "reference.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (unit_dir / "candidate.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (unit_dir / "bugshot-unit.json").write_text(
        '{"assets":["candidate.png"],"reference_asset":"reference.png"}',
        encoding="utf-8",
    )

    try:
        gallery_server.create_server(str(tmp_path))
    except ValueError as error:
        assert "reference_asset must name one of the unit assets" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid reference_asset")


def test_grouped_unit_does_not_infer_reference_asset_without_manifest_field(tmp_path):
    unit_dir = tmp_path / "implicit-reference"
    unit_dir.mkdir()
    for name in ["reference.png", "candidate.png"]:
        (unit_dir / name).write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    server = gallery_server.create_server(str(tmp_path))
    try:
        assert server.units[0]["reference_asset_relative_path"] is None
    finally:
        server.shutdown()
        if os.path.exists(server.db_path):
            os.unlink(server.db_path)


def test_gallery_js_wires_copy_filename_shortcut(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert 'SHORTCUT_KEY_COPY_FILENAME = "c"' in script
    assert 'SHORTCUT_KEY_NEXT_ALTERNATE = "."' in script
    assert 'SHORTCUT_KEY_PREVIOUS_ALTERNATE = ","' in script
    assert 'THEME_STORAGE_KEY = "bugshot-theme"' in script
    assert 'id: "mono-light"' in script
    assert 'id: "mono-dark"' in script
    assert "rewriteSvgPrimaryColor" in script
    assert "copy-filename-btn" in script
    assert "copyFilenameToClipboard" in script
    assert "navigator.clipboard.writeText" in script


def test_detail_styles_align_filename_and_copy_button(repo_root):
    style = open(f"{repo_root}/static/style.css").read()
    assert 'body[data-theme="mono-light"]' in style
    assert 'body[data-theme="mono-dark"]' in style
    assert ".metadata-table" in style
    assert ".svg-rendered .svg-asset" in style
    assert re.search(r"\.detail-filename\s*\{[^}]*line-height:\s*1;", style, re.S)
    assert re.search(r"\.btn-copy-filename\s*\{[^}]*line-height:\s*1;", style, re.S)


def test_theme_controls_are_separate_from_nav_buttons(repo_root):
    index_template = open(f"{repo_root}/templates/index.html").read()
    detail_template = open(f"{repo_root}/templates/detail.html").read()
    style = open(f"{repo_root}/static/style.css").read()

    assert 'class="theme-toolbar"' in index_template
    assert 'class="theme-toolbar detail-theme-toolbar"' in detail_template
    index_controls = index_template.split('class="controls"')[1].split('class="theme-toolbar"')[0]
    detail_controls = detail_template.split('detail-nav-toolbar"')[1].split('class="theme-toolbar detail-theme-toolbar"')[0]
    assert 'id="index-theme-controls"' not in index_controls
    assert 'id="detail-theme-controls"' not in detail_controls
    assert not re.search(r"\.theme-button,\s*\.btn\s*\{", style)
    assert re.search(r"\.theme-button\s*\{[^}]*width:\s*28px;", style, re.S)
    assert re.search(r"\.theme-swatch\s*\{", style, re.S)


def test_create_comment(server):
    status, body = _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png",
        "body": "Button is misaligned",
    })
    assert status == 200
    assert body["id"] == 1
    assert body["unit_id"] == "alpha.png"
    assert body["body"] == "Button is misaligned"
    assert "created_at" in body


def test_create_grouped_comment(grouped_server):
    status, body = _post_json(f"{grouped_server.url}/api/comments", {
        "unit_id": "login-button",
        "body": "The candidate diverges from the reference.",
    })
    assert status == 200
    assert body["unit_id"] == "login-button"
    assert body["body"] == "The candidate diverges from the reference."


def test_create_comment_persists(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"unit_id": "beta.png", "body": "Issue 2"})

    comments = _read_comments(server.db_path)
    assert len(comments) == 2
    assert comments[0]["body"] == "Issue 1"
    assert comments[1]["body"] == "Issue 2"


def test_list_comments(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"unit_id": "beta.png", "body": "Issue 2"})

    status, body = _get_json(f"{server.url}/api/comments")

    assert status == 200
    assert [comment["body"] for comment in body] == ["Issue 1", "Issue 2"]


def test_list_comments_filters_by_unit(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"unit_id": "beta.png", "body": "Issue 2"})

    status, body = _get_json(
        f"{server.url}/api/comments?unit_id={urllib.parse.quote('alpha.png')}"
    )

    assert status == 200
    assert len(body) == 1
    assert body[0]["unit_id"] == "alpha.png"
    assert body[0]["body"] == "Issue 1"


def test_update_comment(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Original"})

    status, body = _patch_json(f"{server.url}/api/comments/1", {"body": "Updated"})
    assert status == 200
    assert body["body"] == "Updated"

    comments = _read_comments(server.db_path)
    assert comments[0]["body"] == "Updated"


def test_delete_comment(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Delete me"})

    status = _delete(f"{server.url}/api/comments/1")
    assert status == 204

    assert _read_comments(server.db_path) == []


def test_create_comment_missing_fields(server):
    status, body = _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png"})
    assert status == 400


def test_update_nonexistent_comment(server):
    status, body = _patch_json(f"{server.url}/api/comments/999", {"body": "Nope"})
    assert status == 404


def test_delete_nonexistent_comment(server):
    status = _delete(f"{server.url}/api/comments/999")
    assert status == 404


def test_heartbeat(server):
    status, body = _post_json(f"{server.url}/api/heartbeat", {})
    assert status == 200
    assert body["ok"] is True


def test_done_button_sets_session_state(server):
    _post_json(f"{server.url}/api/done", {})
    state = _read_session(server.db_path)
    assert state["done"] == "true"
    assert state["done_reason"] == "button"


def test_closed_signal_sets_session_state(server):
    _post_json(f"{server.url}/api/closed", {})
    state = _read_session(server.db_path)
    assert state["done"] == "true"
    assert state["done_reason"] == "closed"


def test_comments_table_has_region_column(server):
    conn = sqlite3.connect(server.db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    finally:
        conn.close()
    assert "region" in cols, "comments table must have a `region` column"


def test_create_comment_with_rect_region(server):
    region = {"type": "rect", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    status, body = _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png",
        "body": "Submit button color regression",
        "region": region,
    })
    assert status == 200
    assert body["region"] == region


def test_create_comment_with_ellipse_region(server):
    region = {"type": "ellipse", "cx": 0.4, "cy": 0.55, "rx": 0.12, "ry": 0.08}
    status, body = _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png",
        "body": "Loading spinner offset",
        "region": region,
    })
    assert status == 200
    assert body["region"] == region

    # Round-trip through GET to confirm SQLite encode/decode preserves shape.
    _, listed = _get_json(f"{server.url}/api/comments")
    matching = [c for c in listed if c["body"] == "Loading spinner offset"]
    assert matching and matching[0]["region"] == region


def test_create_comment_with_path_region(server):
    region = {"type": "path", "points": [[0.1, 0.2], [0.15, 0.22], [0.2, 0.25]]}
    status, body = _post_json(f"{server.url}/api/comments", {
        "unit_id": "beta.png",
        "body": "Headline shifted",
        "region": region,
    })
    assert status == 200
    assert body["region"] == region


def test_create_comment_without_region_returns_null(server):
    status, body = _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png",
        "body": "Image-level comment",
    })
    assert status == 200
    assert body["region"] is None


def test_list_comments_includes_region(server):
    region = {"type": "rect", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}
    _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png", "body": "With region", "region": region,
    })
    _post_json(f"{server.url}/api/comments", {
        "unit_id": "alpha.png", "body": "Without region",
    })

    status, body = _get_json(f"{server.url}/api/comments")
    assert status == 200
    assert body[0]["region"] == region
    assert body[1]["region"] is None


def test_patch_comment_adds_region(server):
    _post_json(f"{server.url}/api/comments", {"unit_id": "alpha.png", "body": "Original"})
    new_region = {"type": "rect", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    status, body = _patch_json(
        f"{server.url}/api/comments/1",
        {"body": "Original", "region": new_region},
    )
    assert status == 200
    assert body["region"] == new_region


def test_patch_comment_clears_region(server):
    region = {"type": "rect", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}
    _post_json(
        f"{server.url}/api/comments",
        {"unit_id": "alpha.png", "body": "With region", "region": region},
    )
    status, body = _patch_json(
        f"{server.url}/api/comments/1",
        {"body": "With region", "region": None},
    )
    assert status == 200
    assert body["region"] is None


def test_patch_comment_omits_region_preserves_existing(server):
    region = {"type": "rect", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}
    _post_json(
        f"{server.url}/api/comments",
        {"unit_id": "alpha.png", "body": "With region", "region": region},
    )
    status, body = _patch_json(
        f"{server.url}/api/comments/1",
        {"body": "Edited body, no region key"},
    )
    assert status == 200
    assert body["region"] == region


def test_detail_page_includes_tools_toolbar_markup(server):
    resp = urllib.request.urlopen(f"{server.url}/view/alpha.png")
    body = resp.read().decode()
    assert 'id="detail-tools"' in body
    assert 'data-tool="rect"' in body
    assert 'data-tool="ellipse"' in body
    assert 'data-tool="path"' in body
    assert 'data-tool="off"' in body
    assert 'id="pending-region-indicator"' in body
    assert ">d</span> cycle tool" in body


def test_gallery_js_wires_region_tool_shortcut(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert 'SHORTCUT_KEY_CYCLE_TOOL = "d"' in script
    assert 'TOOL_OFF = "off"' in script
    assert 'TOOL_RECT = "rect"' in script
    assert 'TOOL_ELLIPSE = "ellipse"' in script
    assert 'TOOL_PATH = "path"' in script
    assert 'unitSupportsRegionDrawing' in script
    assert 'pendingRegion' in script
    assert 'region-badge' in script


def test_detail_legend_marks_region_drawing_entry(server):
    # The 'd cycle tool' entry must be rendered as a uniquely-targetable
    # element so the client can toggle it based on whether the current unit
    # supports region drawing.
    resp = urllib.request.urlopen(f"{server.url}/view/alpha.png")
    body = resp.read().decode()
    assert 'id="legend-region-drawing"' in body
    # The id must be on the same item that hosts the 'd cycle tool' label.
    pattern = re.compile(
        r'id="legend-region-drawing"[^>]*>\s*<span[^>]*>d</span>\s*cycle tool',
    )
    assert pattern.search(body), body


def test_grouped_detail_legend_hides_region_drawing_entry(grouped_server):
    # Grouped review units have multiple assets, so unitSupportsRegionDrawing
    # returns false. The legend entry is still rendered server-side; the
    # client toggles it hidden. We assert the marker remains addressable.
    resp = urllib.request.urlopen(f"{grouped_server.url}/view/login-button")
    body = resp.read().decode()
    assert 'id="legend-region-drawing"' in body


def test_gallery_js_toggles_region_drawing_legend_entry(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert 'legend-region-drawing' in script
    # The toggle must be gated on the same predicate used by the keypress
    # handler at the existing 'd' shortcut site.
    assert 'unitSupportsRegionDrawing(currentUnit)' in script


def test_gallery_js_wires_region_hover_highlight(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    # Pure hit-test helpers for each region type plus the dispatch wrapper.
    assert "function hitTestRect(" in script
    assert "function hitTestEllipse(" in script
    assert "function hitTestPath(" in script
    assert "function hitTestRegions(" in script
    # Bidirectional highlight state and the comment-list ↔ canvas wiring.
    assert "highlightedSelectionId" in script
    assert "setHighlightedSelection" in script
    assert "syncHighlightedComment" in script
    assert "data-selection-id" in script or "dataset.selectionId" in script
    # Card-level hover (works in OFF tool mode, when the overlay is transparent
    # to events) drives the canvas → comment direction.
    assert "onCardHover" in script
    assert "region-hover-active" in script


def test_gallery_js_arrow_keys_navigate_comment_list(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    # ArrowUp/ArrowDown keydown branch on detail pages.
    assert '"ArrowDown"' in script
    assert '"ArrowUp"' in script
    # A dedicated helper that reuses the qh9 highlight code path.
    assert "function focusAdjacentComment(" in script
    # The helper must reuse setHighlightedSelection rather than reimplement
    # the hover highlight or canvas paint.
    helper_start = script.index("function focusAdjacentComment(")
    helper_end = script.index("\n    }\n", helper_start)
    helper_body = script[helper_start:helper_end]
    assert "setHighlightedSelection" in helper_body
    # The "no input/textarea focused" gate is shared with the existing
    # shortcut dispatch — the arrow branch must live inside it.
    arrow_index = script.index('"ArrowDown"')
    typing_guard_index = script.index('activeElement.tagName === "TEXTAREA"')
    assert typing_guard_index < arrow_index


def test_detail_styles_subdue_committed_regions(repo_root):
    style = open(f"{repo_root}/static/style.css").read()
    assert ".comment-item.is-hovered" in style
    assert ".asset-card.has-region-overlay.region-hover-active" in style
    assert "cursor: pointer" in style

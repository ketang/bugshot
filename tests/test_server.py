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
    assert "c copy filename" in body
    assert "n/. next" in body
    assert "p/, previous" in body


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

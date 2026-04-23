import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request


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
            "SELECT id, image, body, created_at FROM comments ORDER BY id"
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


def test_index_page_returns_200(server):
    resp = urllib.request.urlopen(f"{server.url}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert "alpha.png" in body
    assert "beta.png" in body


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


def test_gallery_js_wires_copy_filename_shortcut(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert 'SHORTCUT_KEY_COPY_FILENAME = "c"' in script
    assert 'SHORTCUT_KEY_NEXT_ALTERNATE = "."' in script
    assert 'SHORTCUT_KEY_PREVIOUS_ALTERNATE = ","' in script
    assert "copy-filename-btn" in script
    assert "copyFilenameToClipboard" in script
    assert "navigator.clipboard.writeText" in script


def test_detail_styles_align_filename_and_copy_button(repo_root):
    style = open(f"{repo_root}/static/style.css").read()
    assert re.search(r"\.detail-filename\s*\{[^}]*line-height:\s*1;", style, re.S)
    assert re.search(r"\.btn-copy-filename\s*\{[^}]*line-height:\s*1;", style, re.S)


def test_create_comment(server):
    status, body = _post_json(f"{server.url}/api/comments", {
        "image": "alpha.png",
        "body": "Button is misaligned",
    })
    assert status == 200
    assert body["id"] == 1
    assert body["image"] == "alpha.png"
    assert body["body"] == "Button is misaligned"
    assert "created_at" in body


def test_create_comment_persists(server):
    _post_json(f"{server.url}/api/comments", {"image": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"image": "beta.png", "body": "Issue 2"})

    comments = _read_comments(server.db_path)
    assert len(comments) == 2
    assert comments[0]["body"] == "Issue 1"
    assert comments[1]["body"] == "Issue 2"


def test_list_comments(server):
    _post_json(f"{server.url}/api/comments", {"image": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"image": "beta.png", "body": "Issue 2"})

    status, body = _get_json(f"{server.url}/api/comments")

    assert status == 200
    assert [comment["body"] for comment in body] == ["Issue 1", "Issue 2"]


def test_list_comments_filters_by_image(server):
    _post_json(f"{server.url}/api/comments", {"image": "alpha.png", "body": "Issue 1"})
    _post_json(f"{server.url}/api/comments", {"image": "beta.png", "body": "Issue 2"})

    status, body = _get_json(
        f"{server.url}/api/comments?image={urllib.parse.quote('alpha.png')}"
    )

    assert status == 200
    assert len(body) == 1
    assert body[0]["image"] == "alpha.png"
    assert body[0]["body"] == "Issue 1"


def test_update_comment(server):
    _post_json(f"{server.url}/api/comments", {"image": "alpha.png", "body": "Original"})

    status, body = _patch_json(f"{server.url}/api/comments/1", {"body": "Updated"})
    assert status == 200
    assert body["body"] == "Updated"

    comments = _read_comments(server.db_path)
    assert comments[0]["body"] == "Updated"


def test_delete_comment(server):
    _post_json(f"{server.url}/api/comments", {"image": "alpha.png", "body": "Delete me"})

    status = _delete(f"{server.url}/api/comments/1")
    assert status == 204

    assert _read_comments(server.db_path) == []


def test_create_comment_missing_fields(server):
    status, body = _post_json(f"{server.url}/api/comments", {"image": "alpha.png"})
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

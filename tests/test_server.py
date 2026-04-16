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

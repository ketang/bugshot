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

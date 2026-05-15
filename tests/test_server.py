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


def _write_png(path):
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


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
        "reference.png",
        "final.svg",
        "candidate.png",
    ]
    assert grouped_server.units[0]["reference_asset_relative_path"] == (
        "login-button/reference.png"
    )
    assert [item["name"] for item in grouped_server.units[0]["metadata"]] == [
        "report.json",
    ]


def test_grouped_unit_manifest_supports_asset_tooltips(tmp_path):
    unit_dir = tmp_path / "tooltip-unit"
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
    (unit_dir / "bugshot-unit.json").write_text(
        json.dumps(
            {
                "assets": ["reference.png", "candidate.png"],
                "asset_tooltips": {
                    "reference.png": "Baseline before the change",
                    "candidate.png": "Current branch rendering",
                },
            }
        ),
        encoding="utf-8",
    )

    units = gallery_server.discover_review_units(str(tmp_path))
    payload = gallery_server.unit_detail_payload(units[0], review_root=str(tmp_path))

    assert [asset["tooltip"] for asset in units[0]["assets"]] == [
        "Baseline before the change",
        "Current branch rendering",
    ]
    assert [asset["tooltip"] for asset in payload["assets"]] == [
        "Baseline before the change",
        "Current branch rendering",
    ]


def test_asset_tooltip_must_name_declared_asset(tmp_path):
    unit_dir = tmp_path / "broken-unit"
    unit_dir.mkdir()
    (unit_dir / "candidate.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (unit_dir / "bugshot-unit.json").write_text(
        json.dumps(
            {
                "assets": ["candidate.png"],
                "asset_tooltips": {"reference.png": "Missing baseline"},
            }
        ),
        encoding="utf-8",
    )

    try:
        gallery_server.discover_review_units(str(tmp_path))
    except ValueError as error:
        assert "asset_tooltips keys must name one of the unit assets" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown asset tooltip")


def test_grouped_unit_orders_reference_conversion_then_diagnostics(tmp_path):
    unit_dir = tmp_path / "logo-sample"
    unit_dir.mkdir()
    for name in [
        "difference-overlay.png",
        "final.svg",
        "input-minus-svg.png",
        "source-crop.png",
        "svg-minus-input.png",
    ]:
        (unit_dir / name).write_bytes(b"asset")

    units = gallery_server.discover_review_units(str(tmp_path))

    assert [asset["name"] for asset in units[0]["assets"]] == [
        "source-crop.png",
        "final.svg",
        "difference-overlay.png",
        "input-minus-svg.png",
        "svg-minus-input.png",
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


def test_detail_page_places_feedback_composer_before_assets(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/view/login-button")
    body = resp.read().decode()
    assert 'class="feedback-composer"' in body
    assert body.index('class="feedback-composer"') < body.index('id="unit-assets"')
    assert body.index('id="comments-list"') > body.index('id="unit-assets"')


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


def test_image_asset_has_cache_control_header(server):
    resp = urllib.request.urlopen(f"{server.url}/screenshots/alpha.png")
    assert resp.status == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=31536000, immutable"


def test_static_asset_has_cache_control_header(server):
    resp = urllib.request.urlopen(f"{server.url}/static/gallery.js")
    assert resp.status == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=86400"


def test_index_page_contains_prefetch_links_for_images(server):
    resp = urllib.request.urlopen(f"{server.url}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert 'rel="prefetch"' in body
    assert 'as="image"' in body
    assert "/screenshots/alpha.png" in body


def test_index_page_prefetches_all_image_assets(tmp_path):
    for i in range(60):
        (tmp_path / f"img{i:02d}.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    units = gallery_server.discover_review_units(str(tmp_path))
    links = gallery_server._build_image_prefetch_links(units)
    assert links.count('rel="prefetch"') == 60
    assert "/screenshots/img00.png" in links
    assert "/screenshots/img59.png" in links


def test_index_page_prefetches_all_grouped_image_assets(grouped_server):
    resp = urllib.request.urlopen(f"{grouped_server.url}/")
    body = resp.read().decode()
    assert "/screenshots/login-button/reference.png" in body
    assert "/screenshots/login-button/final.svg" in body
    assert "/screenshots/login-button/candidate.png" in body
    assert "/screenshots/settings-panel/reference.png" in body
    assert "/screenshots/settings-panel/final.svg" in body
    assert "/screenshots/settings-panel/candidate.png" in body


def test_detail_page_prefetches_previous_and_next_images(server):
    resp = urllib.request.urlopen(f"{server.url}/view/beta.png")
    assert resp.status == 200
    body = resp.read().decode()
    assert "/screenshots/alpha.png" in body
    assert "/screenshots/gamma.jpg" in body
    assert "/screenshots/beta.png" not in body.split("</head>")[0]


def test_ansi_assets_excluded_from_prefetch_links(server):
    resp = urllib.request.urlopen(f"{server.url}/")
    body = resp.read().decode()
    assert "delta.ansi" not in body.split('rel="prefetch"')[0] if 'rel="prefetch"' in body else True
    links = gallery_server._build_image_prefetch_links(server.units)
    assert "delta.ansi" not in links


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
        server.cleanup_temporary_files()


def test_temporary_database_filename_carries_session_context(tmp_path, monkeypatch):
    project_dir = tmp_path / "Demo Project"
    project_dir.mkdir()
    review_root = tmp_path / "Checkout Screens"
    review_root.mkdir()
    _write_png(review_root / "page.png")

    monkeypatch.chdir(project_dir)
    monkeypatch.setenv("BUGSHOT_AGENT", "Codex Runner")

    server = gallery_server.create_server(str(review_root))
    try:
        filename = os.path.basename(server.db_path)
        assert re.match(
            r"bugshot_\d{8}_\d{6}_codex-runner_demo-project_[a-z0-9_]+\.db$",
            filename,
        )
        assert "checkout-screens" not in filename
        assert (
            server.review_root_sidecar_path
            == os.path.splitext(server.db_path)[0] + ".root"
        )
        assert os.path.exists(server.review_root_sidecar_path)
        with open(server.review_root_sidecar_path, encoding="utf-8") as f:
            assert f.read() == f"{os.path.abspath(review_root)}\n"
    finally:
        server.shutdown()
        server.cleanup_temporary_files()


def test_temporary_file_cleanup_removes_database_and_review_root_sidecar(screenshot_dir):
    server = gallery_server.create_server(screenshot_dir)
    db_path = server.db_path
    sidecar_path = server.review_root_sidecar_path

    assert os.path.exists(db_path)
    assert os.path.exists(sidecar_path)

    server.shutdown()
    server.cleanup_temporary_files()

    assert not os.path.exists(db_path)
    assert not os.path.exists(sidecar_path)


def test_temporary_files_can_use_explicit_session_directory(screenshot_dir, tmp_path):
    session_dir = tmp_path / "bugshot-session"
    session_dir.mkdir()

    server = gallery_server.create_server(screenshot_dir, session_dir=str(session_dir))
    try:
        assert os.path.dirname(server.db_path) == str(session_dir)
        assert os.path.dirname(server.review_root_sidecar_path) == str(session_dir)
        assert os.path.exists(server.db_path)
        assert os.path.exists(server.review_root_sidecar_path)
        with open(server.review_root_sidecar_path, encoding="utf-8") as f:
            assert f.read() == f"{os.path.abspath(screenshot_dir)}\n"
    finally:
        server.shutdown()
        server.cleanup_temporary_files()


def test_gallery_js_wires_copy_filename_shortcut(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert 'SHORTCUT_KEY_COPY_FILENAME = "c"' in script
    assert 'SHORTCUT_KEY_THEME = "t"' in script
    assert 'SHORTCUT_KEY_NEXT_ALTERNATE = "."' in script
    assert 'SHORTCUT_KEY_PREVIOUS_ALTERNATE = ","' in script
    assert 'THEME_STORAGE_KEY = "bugshot-theme"' in script
    assert "cycleTheme()" in script
    assert "theme-select" in script
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


def test_fullsize_gallery_preserves_native_image_dimensions(repo_root):
    style = open(f"{repo_root}/static/style.css").read()

    assert re.search(
        r"\.gallery\.fullsize-mode\s*\{[^}]*grid-template-columns:\s*max-content;",
        style,
        re.S,
    )
    assert re.search(
        r"\.fullsize-mode\s+\.gallery-item\s+img\s*\{[^}]*width:\s*auto;",
        style,
        re.S,
    )
    assert re.search(
        r"\.fullsize-mode\s+\.gallery-item\s+\.svg-asset,\s*"
        r"\.fullsize-mode\s+\.gallery-item\s+\.svg-preview\s+img\s*\{[^}]*width:\s*auto;",
        style,
        re.S,
    )
    assert re.search(
        r"\.fullsize-mode\s+\.gallery-item\s*\{[^}]*overflow:\s*visible;",
        style,
        re.S,
    )


def test_theme_controls_are_labeled_selects_not_buttons(repo_root):
    index_template = open(f"{repo_root}/templates/index.html").read()
    detail_template = open(f"{repo_root}/templates/detail.html").read()
    style = open(f"{repo_root}/static/style.css").read()

    assert 'id="index-theme-controls"' in index_template.split('class="controls"')[1].split("</div>")[0]
    assert 'id="detail-theme-controls"' in detail_template.split('detail-nav-toolbar"')[1].split("</div>")[0]
    assert 'class="theme-toolbar"' not in index_template
    assert 'class="theme-toolbar detail-theme-toolbar"' not in detail_template
    assert not re.search(r"\.theme-button,\s*\.btn\s*\{", style)
    assert re.search(r"\.theme-select-control\s*\{", style, re.S)
    assert re.search(r"\.theme-select-label\s*\{", style, re.S)
    assert re.search(r"\.theme-select\s*\{", style, re.S)


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


def test_gallery_js_applies_asset_tooltips(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert "applyAssetTooltip" in script
    assert "asset.tooltip" in script
    assert 'title.className = "asset-title"' in script
    assert "imageElement.title = asset.tooltip" in script


def test_gallery_js_moves_region_toolbar_into_asset_header(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert "asset-header" in script
    assert 'card.querySelector(".asset-header")' in script
    assert "assetHeader.appendChild(toolbar)" in script


def test_gallery_js_updates_comments_count_link(repo_root):
    script = open(f"{repo_root}/static/gallery.js").read()
    assert "comments-count-link" in script
    assert 'commentsLink.href = "#comments-list"' in script
    assert "function updateCommentsCountLink()" in script
    assert 'count + " " + (count === 1 ? "comment" : "comments")' in script


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


def test_detail_styles_float_feedback_composer(repo_root):
    style = open(f"{repo_root}/static/style.css").read()
    assert ".feedback-composer" in style
    composer_start = style.index(".feedback-composer")
    composer_end = style.index("\n}", composer_start)
    composer_rule = style[composer_start:composer_end]
    assert "position: sticky" in composer_rule
    assert "top: 6px" in composer_rule
    assert "margin: 0 auto 18px" in composer_rule
    assert "z-index" in composer_rule
    assert "padding: 2px" in composer_rule
    assert ".comment-status:empty" in style
    assert ".comments-count-link" in style
    assert "margin-left: 8px" in style
    assert "background: var(--bg-muted)" in style

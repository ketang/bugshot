import io
import json
import sqlite3

import bugshot_workflow


def _seed_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            body TEXT NOT NULL,
            region TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def _insert(db_path: str, unit_id: str, body: str, region) -> None:
    region_text = json.dumps(region) if region is not None else None
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO comments (unit_id, body, region) VALUES (?, ?, ?)",
        (unit_id, body, region_text),
    )
    conn.commit()
    conn.close()


def _make_single_asset_unit(unit_id: str) -> dict:
    return {
        "id": unit_id,
        "label": unit_id,
        "relative_dir": "",
        "assets": [
            {"name": unit_id, "relative_path": unit_id, "type": "image"},
        ],
        "metadata": [],
        "reference_asset_relative_path": None,
    }


def _make_shell(json_output: bool):
    out = io.StringIO()
    err = io.StringIO()
    shell = bugshot_workflow.ShellIO(
        input_stream=io.StringIO(),
        output_stream=out,
        error_stream=err,
        json_output=json_output,
    )
    return shell, out, err


def test_drafts_include_region_on_single_asset_unit(tmp_path):
    db = tmp_path / "session.db"
    _seed_db(str(db))
    region = {"type": "rect", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    _insert(str(db), "alpha.png", "Submit button regression", region)
    _insert(str(db), "beta.png", "Headline alignment", None)

    units = [_make_single_asset_unit("alpha.png"), _make_single_asset_unit("beta.png")]
    shell, _out, _err = _make_shell(json_output=True)
    comments = bugshot_workflow._fetch_comments(str(db))
    summary = bugshot_workflow._process_comments(
        comments, units, str(tmp_path), shell, json_output=True,
    )

    assert summary.draft_count == 2
    assert summary.drafts[0]["region"] == region
    assert summary.drafts[1]["region"] is None


def test_markdown_includes_region_when_present(tmp_path):
    db = tmp_path / "session.db"
    _seed_db(str(db))
    region = {"type": "rect", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    _insert(str(db), "alpha.png", "Issue", region)

    units = [_make_single_asset_unit("alpha.png")]
    shell, out, _err = _make_shell(json_output=False)
    comments = bugshot_workflow._fetch_comments(str(db))
    bugshot_workflow._process_comments(
        comments, units, str(tmp_path), shell, json_output=False,
    )

    output = out.getvalue()
    assert "Region: rect" in output
    assert "x=0.10" in output


def test_markdown_omits_region_line_when_null(tmp_path):
    db = tmp_path / "session.db"
    _seed_db(str(db))
    _insert(str(db), "alpha.png", "Image-level only", None)

    units = [_make_single_asset_unit("alpha.png")]
    shell, out, _err = _make_shell(json_output=False)
    comments = bugshot_workflow._fetch_comments(str(db))
    bugshot_workflow._process_comments(
        comments, units, str(tmp_path), shell, json_output=False,
    )

    output = out.getvalue()
    assert "Region:" not in output


def test_path_region_markdown_summarizes_point_count(tmp_path):
    db = tmp_path / "session.db"
    _seed_db(str(db))
    region = {"type": "path", "points": [[0.1, 0.2], [0.15, 0.22], [0.2, 0.25]]}
    _insert(str(db), "alpha.png", "Freehand issue", region)

    units = [_make_single_asset_unit("alpha.png")]
    shell, out, _err = _make_shell(json_output=False)
    comments = bugshot_workflow._fetch_comments(str(db))
    bugshot_workflow._process_comments(
        comments, units, str(tmp_path), shell, json_output=False,
    )

    output = out.getvalue()
    assert "Region: path (3 points)" in output

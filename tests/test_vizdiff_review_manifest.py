import json
import urllib.request
from pathlib import Path


REVIEW_SCHEMA = "bugshot.vizdiff-review/v1"


def _post_json(url: str, path: str, payload: dict | None = None) -> None:
    data = json.dumps(payload or {}).encode()
    urllib.request.urlopen(
        urllib.request.Request(
            f"{url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    ).read()


def _mark_seen(url: str, unit_id: str) -> None:
    _post_json(url, "/api/review-state", {"unit_id": unit_id, "seen": True})


def _signal_done(url: str) -> None:
    _post_json(url, "/api/done")


def _signal_closed(url: str) -> None:
    _post_json(url, "/api/closed")


def test_vizdiff_writes_passing_review_manifest_when_all_units_seen(
    fake_git_worktree,
    fake_capture_command,
):
    import vizdiff_workflow

    def session(server):
        for unit in server.units:
            _mark_seen(server.url, unit["id"])
        _post_json(
            server.url,
            "/api/comments",
            {"unit_id": server.units[0]["id"], "body": "intentional visual change"},
        )
        _signal_done(server.url)

    vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        head_only=True,
        bind_address="127.0.0.1",
        on_server_ready=session,
    )

    manifest_path = fake_git_worktree / ".bugshot" / "review-manifest.json"
    ok, errors = vizdiff_workflow.check_review_manifest(manifest_path)
    assert ok, errors

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == REVIEW_SCHEMA
    assert manifest["done_reason"] == "button"
    assert manifest["unit_count"] == 2
    assert {unit["seen"] for unit in manifest["units"]} == {True}
    assert [unit["commented"] for unit in manifest["units"]].count(True) == 1


def test_vizdiff_writes_failing_review_manifest_on_early_close(
    fake_git_worktree,
    fake_capture_command,
):
    import vizdiff_workflow

    def session(server):
        _mark_seen(server.url, server.units[0]["id"])
        _signal_closed(server.url)

    vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        head_only=True,
        bind_address="127.0.0.1",
        on_server_ready=session,
    )

    manifest_path = fake_git_worktree / ".bugshot" / "review-manifest.json"
    ok, errors = vizdiff_workflow.check_review_manifest(manifest_path)
    assert not ok
    assert any("not seen" in error for error in errors)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["done_reason"] == "closed"
    assert manifest["unit_count"] == 2
    assert sorted(unit["seen"] for unit in manifest["units"]) == [False, True]


def test_review_manifest_check_fails_when_expected_unit_entry_is_missing(tmp_path: Path):
    import vizdiff_workflow

    manifest_path = tmp_path / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": REVIEW_SCHEMA,
                "unit_count": 2,
                "expected_units": [
                    {"id": "alpha.png", "label": "alpha.png"},
                    {"id": "beta.png", "label": "beta.png"},
                ],
                "units": [
                    {
                        "id": "alpha.png",
                        "label": "alpha.png",
                        "seen": True,
                        "commented": False,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ok, errors = vizdiff_workflow.check_review_manifest(manifest_path)

    assert not ok
    assert any("missing review entries" in error for error in errors)


def test_review_manifest_check_fails_empty_expected_units(tmp_path: Path):
    import vizdiff_workflow

    manifest_path = tmp_path / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": REVIEW_SCHEMA,
                "unit_count": 0,
                "expected_units": [],
                "units": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ok, errors = vizdiff_workflow.check_review_manifest(manifest_path)

    assert not ok
    assert any("expected_units must be non-empty" in error for error in errors)

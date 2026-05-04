import json
from pathlib import Path

import gallery_server
import vizdiff_cli
import vizdiff_workflow


def test_manifest_review_root_carries_surface_summary_and_changeset(tmp_path: Path):
    (tmp_path / "base").mkdir()
    (tmp_path / "head").mkdir()
    (tmp_path / "base/login.png").write_bytes(b"BASE")
    (tmp_path / "head/login.png").write_bytes(b"HEAD")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "bugshot.vizdiff-manifest/v1",
                "branch": "feature/login-polish",
                "base_ref": "main",
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "changeset": {
                    "url": "https://example.test/pull/123",
                    "commits": ["b" * 40],
                },
                "surfaces": [
                    {
                        "name": "Login desktop",
                        "base": "base/login.png",
                        "head": "head/login.png",
                        "expected_change": "Only the primary button color should change.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review_root = vizdiff_workflow.build_review_root_from_manifest(manifest_path)
    units = gallery_server.discover_review_units(str(review_root))

    assert [unit["id"] for unit in units] == ["Login desktop"]
    payload = gallery_server.unit_detail_payload(units[0], review_root=str(review_root))
    assert payload["label"] == "Login desktop"
    assert payload["vizdiff"]["classification"] == "changed"
    assert payload["vizdiff"]["expected_change"] == "Only the primary button color should change."
    assert payload["vizdiff"]["branch"] == "feature/login-polish"
    assert payload["vizdiff"]["changeset"]["url"] == "https://example.test/pull/123"


def test_vizdiff_cli_accepts_manifest_without_feature_worktree(tmp_path: Path):
    args = vizdiff_cli.parse_args(["--manifest", str(tmp_path / "manifest.json")])

    assert args.manifest == tmp_path / "manifest.json"
    assert args.feature_worktree is None

import json
from pathlib import Path

import pytest

import gallery_server


VIZDIFF_SCHEMA = "bugshot.vizdiff/v1"


def make_vizdiff_unit(tmp_path: Path, unit_id: str, classification: str,
                      base_present: bool = True, head_present: bool = True) -> Path:
    unit = tmp_path / unit_id
    unit.mkdir(parents=True)
    assets = []
    if base_present:
        (unit / "reference.png").write_bytes(b"BASE")
        assets.append("reference.png")
    if head_present:
        (unit / "candidate.png").write_bytes(b"HEAD")
        assets.append("candidate.png")
    manifest = {
        "label": unit_id.replace("__", "/"),
        "assets": assets,
        "metadata": ["bugshot-metadata.json"],
    }
    if base_present:
        manifest["reference_asset"] = "reference.png"
    (unit / "bugshot-unit.json").write_text(json.dumps(manifest))
    metadata = {
        "schema": VIZDIFF_SCHEMA,
        "classification": classification,
        "relative_path": unit_id.replace("__", "/"),
        "base_asset": "reference.png" if base_present else None,
        "head_asset": "candidate.png" if head_present else None,
        "base_sha256": "x"*64 if base_present else None,
        "head_sha256": "y"*64 if head_present else None,
        "base_ref": "main", "base_sha": "a"*40, "head_sha": "b"*40,
    }
    (unit / "bugshot-metadata.json").write_text(json.dumps(metadata))
    return unit


def test_index_payload_includes_vizdiff_block(tmp_path):
    make_vizdiff_unit(tmp_path, "pages__login.png", "changed")
    units = gallery_server.discover_review_units(str(tmp_path))
    payload = gallery_server.unit_index_payload(units[0], review_root=str(tmp_path))
    assert payload["vizdiff"]["classification"] == "changed"
    assert payload["vizdiff"]["base_asset"] == "reference.png"
    assert payload["vizdiff"]["head_asset"] == "candidate.png"


def test_detail_payload_includes_vizdiff_block(tmp_path):
    make_vizdiff_unit(tmp_path, "pages__login.png", "changed")
    units = gallery_server.discover_review_units(str(tmp_path))
    payload = gallery_server.unit_detail_payload(units[0], review_root=str(tmp_path))
    assert payload["vizdiff"]["classification"] == "changed"
    assert payload["vizdiff"]["base_asset"] == "reference.png"


def test_unit_without_vizdiff_metadata_has_no_block(tmp_path):
    (tmp_path / "plain.png").write_bytes(b"X")
    units = gallery_server.discover_review_units(str(tmp_path))
    payload = gallery_server.unit_index_payload(units[0], review_root=str(tmp_path))
    assert "vizdiff" not in payload


def test_added_unit_has_null_base_in_vizdiff_block(tmp_path):
    make_vizdiff_unit(tmp_path, "new.png", "added", base_present=False, head_present=True)
    units = gallery_server.discover_review_units(str(tmp_path))
    payload = gallery_server.unit_index_payload(units[0], review_root=str(tmp_path))
    assert payload["vizdiff"]["classification"] == "added"
    assert payload["vizdiff"]["base_asset"] is None

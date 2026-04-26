import json
from pathlib import Path

import pytest

import image_diff
import vizdiff_review_root


def write(p: Path, body: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)


def test_unit_id_for_relative_path():
    assert vizdiff_review_root.unit_id_for("pages/login/desktop.png") == "pages__login__desktop.png"
    assert vizdiff_review_root.unit_id_for("a.png") == "a.png"


def test_assemble_changed_unit(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"; out = tmp_path / "review"
    write(base / "pages/login.png", b"BASE")
    write(head / "pages/login.png", b"HEAD")
    pairs = image_diff.classify_pairs(base, head)
    vizdiff_review_root.assemble(
        out_dir=out, base_dir=base, head_dir=head, pairs=pairs,
        base_ref="main", base_sha="a"*40, head_sha="b"*40,
    )
    unit = out / "pages__login.png"
    assert unit.is_dir()
    manifest = json.loads((unit / "bugshot-unit.json").read_text())
    assert manifest["label"] == "pages/login.png"
    assert manifest["reference_asset"] == "reference.png"
    assert manifest["assets"] == ["reference.png", "candidate.png"]
    assert manifest["metadata"] == ["bugshot-metadata.json"]
    assert (unit / "reference.png").read_bytes() == b"BASE"
    assert (unit / "candidate.png").read_bytes() == b"HEAD"

    metadata = json.loads((unit / "bugshot-metadata.json").read_text())
    assert metadata["schema"] == "bugshot.vizdiff/v1"
    assert metadata["classification"] == "changed"
    assert metadata["relative_path"] == "pages/login.png"
    assert metadata["base_asset"] == "reference.png"
    assert metadata["head_asset"] == "candidate.png"
    assert metadata["base_ref"] == "main"
    assert metadata["base_sha"] == "a"*40
    assert metadata["head_sha"] == "b"*40
    assert "base_sha256" in metadata and "head_sha256" in metadata


def test_assemble_added_unit_has_no_reference(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"; out = tmp_path / "review"
    base.mkdir()
    write(head / "new.png", b"HEAD")
    pairs = image_diff.classify_pairs(base, head)
    vizdiff_review_root.assemble(
        out_dir=out, base_dir=base, head_dir=head, pairs=pairs,
        base_ref="main", base_sha="a"*40, head_sha="b"*40,
    )
    unit = out / "new.png"
    manifest = json.loads((unit / "bugshot-unit.json").read_text())
    assert "reference_asset" not in manifest
    assert manifest["assets"] == ["candidate.png"]
    assert (unit / "candidate.png").exists()
    assert not (unit / "reference.png").exists()
    metadata = json.loads((unit / "bugshot-metadata.json").read_text())
    assert metadata["classification"] == "added"
    assert metadata["base_asset"] is None
    assert metadata["base_sha256"] is None


def test_assemble_removed_unit_has_no_candidate(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"; out = tmp_path / "review"
    head.mkdir()
    write(base / "gone.png", b"BASE")
    pairs = image_diff.classify_pairs(base, head)
    vizdiff_review_root.assemble(
        out_dir=out, base_dir=base, head_dir=head, pairs=pairs,
        base_ref="main", base_sha="a"*40, head_sha="b"*40,
    )
    unit = out / "gone.png"
    manifest = json.loads((unit / "bugshot-unit.json").read_text())
    assert manifest["reference_asset"] == "reference.png"
    assert manifest["assets"] == ["reference.png"]
    assert (unit / "reference.png").exists()
    assert not (unit / "candidate.png").exists()
    metadata = json.loads((unit / "bugshot-metadata.json").read_text())
    assert metadata["classification"] == "removed"
    assert metadata["head_asset"] is None
    assert metadata["head_sha256"] is None


def test_assemble_unchanged_unit_includes_both(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"; out = tmp_path / "review"
    write(base / "stable.png", b"SAME")
    write(head / "stable.png", b"SAME")
    pairs = image_diff.classify_pairs(base, head)
    vizdiff_review_root.assemble(
        out_dir=out, base_dir=base, head_dir=head, pairs=pairs,
        base_ref="main", base_sha="a"*40, head_sha="b"*40,
    )
    unit = out / "stable.png"
    metadata = json.loads((unit / "bugshot-metadata.json").read_text())
    assert metadata["classification"] == "unchanged"


def test_assemble_clean_directory_first(tmp_path):
    """Existing review-root contents are removed before reassembly."""
    base = tmp_path / "base"; head = tmp_path / "head"; out = tmp_path / "review"
    out.mkdir(); (out / "stale-unit").mkdir()
    write(base / "a.png", b"X"); write(head / "a.png", b"X")
    vizdiff_review_root.assemble(
        out_dir=out, base_dir=base, head_dir=head,
        pairs=image_diff.classify_pairs(base, head),
        base_ref="main", base_sha="a"*40, head_sha="b"*40,
    )
    assert not (out / "stale-unit").exists()
    assert (out / "a.png").is_dir()

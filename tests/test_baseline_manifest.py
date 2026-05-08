import json
from pathlib import Path

import pytest

import baseline_manifest


def test_manifest_round_trips(tmp_path):
    manifest = baseline_manifest.Manifest(
        schema_version=1,
        base_ref="main",
        base_sha="a" * 40,
        created_at="2026-04-25T12:00:00Z",
        capture_command_path=".agent-plugins/bento/bugshot/viz/capture-command",
        capture_command_sha256="b" * 64,
        images=[
            baseline_manifest.ImageEntry(path="a.png", sha256="c" * 64),
            baseline_manifest.ImageEntry(path="pages/login.png", sha256="d" * 64),
        ],
    )
    path = tmp_path / "manifest.json"
    baseline_manifest.write_manifest(path, manifest)
    loaded = baseline_manifest.read_manifest(path)
    assert loaded == manifest
    assert loaded.image_count == 2


def test_manifest_image_count_field_persists(tmp_path):
    manifest = baseline_manifest.Manifest(
        schema_version=1, base_ref="main", base_sha="a" * 40,
        created_at="t", capture_command_path="x", capture_command_sha256="y",
        images=[],
    )
    path = tmp_path / "m.json"
    baseline_manifest.write_manifest(path, manifest)
    raw = json.loads(path.read_text())
    assert raw["image_count"] == 0


def test_validate_detects_count_mismatch(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({
        "schema_version": 1, "base_ref": "main", "base_sha": "a"*40,
        "created_at": "t", "capture_command_path": "x", "capture_command_sha256": "y",
        "image_count": 5, "images": [{"path": "a.png", "sha256": "z"*64}],
    }))
    with pytest.raises(baseline_manifest.ManifestError, match="image_count"):
        baseline_manifest.read_manifest(path)


def test_validate_rejects_unknown_schema_version(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({
        "schema_version": 99, "base_ref": "main", "base_sha": "a"*40,
        "created_at": "t", "capture_command_path": "x", "capture_command_sha256": "y",
        "image_count": 0, "images": [],
    }))
    with pytest.raises(baseline_manifest.ManifestError, match="schema_version"):
        baseline_manifest.read_manifest(path)


def test_atomic_promote(tmp_path):
    target = tmp_path / "baseline"
    tmp = tmp_path / "baseline.tmp"
    tmp.mkdir()
    (tmp / "manifest.json").write_text("{}")
    (tmp / "images").mkdir()
    baseline_manifest.atomic_promote(tmp, target)
    assert not tmp.exists()
    assert (target / "manifest.json").exists()


def test_atomic_promote_replaces_existing_with_refresh(tmp_path):
    target = tmp_path / "baseline"
    target.mkdir()
    (target / "stale.txt").write_text("old")

    tmp = tmp_path / "baseline.tmp"
    tmp.mkdir()
    (tmp / "manifest.json").write_text("{}")
    baseline_manifest.atomic_promote(tmp, target, refresh=True)

    assert (target / "manifest.json").exists()
    assert not (target / "stale.txt").exists()


def test_atomic_promote_refuses_when_target_exists_without_refresh(tmp_path):
    target = tmp_path / "baseline"
    target.mkdir()
    tmp = tmp_path / "baseline.tmp"
    tmp.mkdir()
    with pytest.raises(baseline_manifest.ManifestError):
        baseline_manifest.atomic_promote(tmp, target, refresh=False)


def _hex_sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _baseline_with(tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, baseline_manifest.Manifest]:
    images_dir = tmp_path / "baseline" / "images"
    images_dir.mkdir(parents=True)
    entries = []
    for rel, data in files.items():
        target = images_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append(baseline_manifest.ImageEntry(path=rel, sha256=_hex_sha256(data)))
    manifest = baseline_manifest.Manifest(
        schema_version=1, base_ref="main", base_sha="a" * 40,
        created_at="t", capture_command_path="x", capture_command_sha256="y",
        images=entries,
    )
    return tmp_path / "baseline", manifest


def test_verify_images_passes_when_disk_matches_manifest(tmp_path):
    baseline_dir, manifest = _baseline_with(
        tmp_path, {"a.png": b"alpha", "pages/b.png": b"beta"}
    )
    baseline_manifest.verify_images(baseline_dir / "images", manifest)


def test_verify_images_raises_on_sha_mismatch(tmp_path):
    baseline_dir, manifest = _baseline_with(
        tmp_path, {"a.png": b"alpha", "pages/b.png": b"beta"}
    )
    (baseline_dir / "images" / "a.png").write_bytes(b"TAMPERED")
    with pytest.raises(baseline_manifest.ManifestError, match=r"sha.*a\.png"):
        baseline_manifest.verify_images(baseline_dir / "images", manifest)


def test_verify_images_raises_on_missing_image(tmp_path):
    baseline_dir, manifest = _baseline_with(
        tmp_path, {"a.png": b"alpha", "pages/b.png": b"beta"}
    )
    (baseline_dir / "images" / "a.png").unlink()
    with pytest.raises(baseline_manifest.ManifestError, match=r"missing.*a\.png"):
        baseline_manifest.verify_images(baseline_dir / "images", manifest)

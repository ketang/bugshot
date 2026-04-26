"""Assemble a grouped review root for bugshot from baseline + head + classification."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import image_diff

VIZDIFF_SCHEMA = "bugshot.vizdiff/v1"
ASSET_NAME_REFERENCE = "reference"
ASSET_NAME_CANDIDATE = "candidate"
PATH_SEPARATOR_REPLACEMENT = "__"


def unit_id_for(rel_path: str) -> str:
    """Translate a forward-slash relative path into a flat unit-directory name."""
    return rel_path.replace("/", PATH_SEPARATOR_REPLACEMENT)


def assemble(
    *,
    out_dir: Path,
    base_dir: Path,
    head_dir: Path,
    pairs: list[image_diff.Pair],
    base_ref: str,
    base_sha: str,
    head_sha: str,
) -> None:
    """Create a fresh review root at out_dir; one unit per pair."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for pair in pairs:
        _assemble_unit(
            out_dir=out_dir, base_dir=Path(base_dir), head_dir=Path(head_dir),
            pair=pair, base_ref=base_ref, base_sha=base_sha, head_sha=head_sha,
        )


def _assemble_unit(
    *,
    out_dir: Path,
    base_dir: Path,
    head_dir: Path,
    pair: image_diff.Pair,
    base_ref: str,
    base_sha: str,
    head_sha: str,
) -> None:
    unit_id = unit_id_for(pair.rel_path)
    unit_dir = out_dir / unit_id
    unit_dir.mkdir(parents=True)

    ext = os.path.splitext(pair.rel_path)[1]  # includes leading dot
    base_asset_name = f"{ASSET_NAME_REFERENCE}{ext}" if pair.base_sha is not None else None
    head_asset_name = f"{ASSET_NAME_CANDIDATE}{ext}" if pair.head_sha is not None else None

    if base_asset_name:
        shutil.copy2(base_dir / pair.rel_path, unit_dir / base_asset_name)
    if head_asset_name:
        shutil.copy2(head_dir / pair.rel_path, unit_dir / head_asset_name)

    assets: list[str] = []
    if base_asset_name:
        assets.append(base_asset_name)
    if head_asset_name:
        assets.append(head_asset_name)

    manifest = {
        "label": pair.rel_path,
        "assets": assets,
        "metadata": ["bugshot-metadata.json"],
    }
    if base_asset_name:
        manifest["reference_asset"] = base_asset_name

    metadata = {
        "schema": VIZDIFF_SCHEMA,
        "classification": pair.classification,
        "relative_path": pair.rel_path,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "base_asset": base_asset_name,
        "head_asset": head_asset_name,
        "base_sha256": pair.base_sha,
        "head_sha256": pair.head_sha,
    }

    (unit_dir / "bugshot-unit.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    (unit_dir / "bugshot-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8",
    )

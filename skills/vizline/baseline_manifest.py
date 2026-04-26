"""Read, write, validate, and atomically promote bugshot baseline manifests."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class ImageEntry:
    path: str
    sha256: str


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    base_ref: str
    base_sha: str
    created_at: str
    capture_command_path: str
    capture_command_sha256: str
    images: list[ImageEntry] = field(default_factory=list)

    @property
    def image_count(self) -> int:
        return len(self.images)


def write_manifest(path: str | os.PathLike[str], manifest: Manifest) -> None:
    payload = {
        "schema_version": manifest.schema_version,
        "base_ref": manifest.base_ref,
        "base_sha": manifest.base_sha,
        "created_at": manifest.created_at,
        "capture_command_path": manifest.capture_command_path,
        "capture_command_sha256": manifest.capture_command_sha256,
        "image_count": manifest.image_count,
        "images": [{"path": img.path, "sha256": img.sha256} for img in manifest.images],
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_manifest(path: str | os.PathLike[str]) -> Manifest:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    schema_version = raw.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(f"unknown schema_version: {schema_version!r}")

    images = [ImageEntry(path=img["path"], sha256=img["sha256"]) for img in raw.get("images", [])]
    declared_count = raw.get("image_count")
    if declared_count != len(images):
        raise ManifestError(
            f"image_count mismatch: manifest declares {declared_count}, "
            f"images list has {len(images)}"
        )

    return Manifest(
        schema_version=schema_version,
        base_ref=raw["base_ref"],
        base_sha=raw["base_sha"],
        created_at=raw["created_at"],
        capture_command_path=raw["capture_command_path"],
        capture_command_sha256=raw["capture_command_sha256"],
        images=images,
    )


def atomic_promote(tmp_dir: Path, target_dir: Path, refresh: bool = False) -> None:
    """Promote a fully-written tmp_dir to target_dir via os.rename.

    refresh=True removes an existing target_dir, but only after tmp_dir is
    fully prepared, so a failure mid-write leaves the prior baseline intact.
    """
    if target_dir.exists():
        if not refresh:
            raise ManifestError(
                f"target already exists; pass refresh=True to overwrite: {target_dir}"
            )
        shutil.rmtree(target_dir)
    os.rename(tmp_dir, target_dir)

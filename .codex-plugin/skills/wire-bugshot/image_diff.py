"""Pure-stdlib image pairing and SHA classification for vizline / vizdiff."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

RECOGNIZED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
ANSI_EXT = ".ansi"
RECOGNIZED_EXTS = RECOGNIZED_IMAGE_EXTS | {ANSI_EXT}

CLASSIFICATIONS = ("unchanged", "changed", "added", "removed")


@dataclass(frozen=True)
class Pair:
    rel_path: str
    classification: str
    base_sha: str | None
    head_sha: str | None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover(root: Path) -> dict[str, str]:
    """Return {relative-path: sha256} for every recognized file under root."""
    found: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in RECOGNIZED_EXTS:
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            found[rel] = sha256_file(full)
    return found


def classify_pairs(base: Path, head: Path) -> list[Pair]:
    pairs, _ = classify_pairs_with_warnings(base, head)
    return pairs


def classify_pairs_with_warnings(base: Path, head: Path) -> tuple[list[Pair], list[str]]:
    base_map = discover(base)
    head_map = discover(head)
    warnings: list[str] = []

    base_lower = {k.lower(): k for k in base_map}
    head_lower = {k.lower(): k for k in head_map}
    case_collisions = (set(base_lower) & set(head_lower)) - (set(base_map) & set(head_map))
    for lower in sorted(case_collisions):
        warnings.append(
            f"case-differing paths treated as separate: "
            f"{base_lower[lower]!r} vs {head_lower[lower]!r}"
        )

    rels = sorted(set(base_map) | set(head_map))
    pairs: list[Pair] = []
    for rel in rels:
        b = base_map.get(rel)
        h = head_map.get(rel)
        if b is not None and h is not None:
            cls = "unchanged" if b == h else "changed"
        elif h is not None:
            cls = "added"
        else:
            cls = "removed"
        pairs.append(Pair(rel_path=rel, classification=cls, base_sha=b, head_sha=h))
    return pairs, warnings

import hashlib
from pathlib import Path

import pytest

import image_diff


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def test_sha256_bytes_matches_hashlib():
    payload = b"alpha\nbeta\n"
    assert image_diff.sha256_bytes(payload) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_matches_bytes(tmp_path):
    f = tmp_path / "x.png"
    write(f, b"fake-png-bytes")
    assert image_diff.sha256_file(f) == hashlib.sha256(b"fake-png-bytes").hexdigest()


def test_classify_pairs_unchanged(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    payload = b"identical-bytes"
    write(base / "a.png", payload); write(head / "a.png", payload)
    pairs = image_diff.classify_pairs(base, head)
    assert pairs == [
        image_diff.Pair(rel_path="a.png", classification="unchanged",
                        base_sha=hashlib.sha256(payload).hexdigest(),
                        head_sha=hashlib.sha256(payload).hexdigest()),
    ]


def test_classify_pairs_changed(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    write(base / "a.png", b"old"); write(head / "a.png", b"new")
    pairs = image_diff.classify_pairs(base, head)
    assert len(pairs) == 1
    assert pairs[0].classification == "changed"
    assert pairs[0].base_sha != pairs[0].head_sha


def test_classify_pairs_added_and_removed(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    write(base / "removed.png", b"x")
    write(head / "added.png", b"y")
    pairs = sorted(image_diff.classify_pairs(base, head), key=lambda p: p.rel_path)
    assert [p.classification for p in pairs] == ["added", "removed"]
    assert pairs[0].rel_path == "added.png"
    assert pairs[0].base_sha is None
    assert pairs[1].rel_path == "removed.png"
    assert pairs[1].head_sha is None


def test_classify_pairs_recurses(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    (base / "pages/login").mkdir(parents=True)
    (head / "pages/login").mkdir(parents=True)
    payload = b"same"
    write(base / "pages/login/desktop.png", payload)
    write(head / "pages/login/desktop.png", payload)
    pairs = image_diff.classify_pairs(base, head)
    assert pairs[0].rel_path == "pages/login/desktop.png"
    assert pairs[0].classification == "unchanged"


def test_classify_pairs_ansi_uses_byte_sha(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    same = b"\x1b[31mhello\x1b[0m\n"
    write(base / "log.ansi", same); write(head / "log.ansi", same)
    pairs = image_diff.classify_pairs(base, head)
    assert pairs[0].classification == "unchanged"


def test_classify_pairs_ansi_whitespace_difference_is_changed(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    write(base / "log.ansi", b"hello\n")
    write(head / "log.ansi", b"hello\n\n")
    pairs = image_diff.classify_pairs(base, head)
    assert pairs[0].classification == "changed"


def test_classify_pairs_warns_on_case_differing_paths(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    write(base / "Login.png", b"a"); write(head / "login.png", b"b")
    pairs, warnings = image_diff.classify_pairs_with_warnings(base, head)
    assert any("case" in w.lower() for w in warnings)
    rels = sorted(p.rel_path for p in pairs)
    assert rels == ["Login.png", "login.png"]


def test_classify_pairs_skips_unrecognized_extensions(tmp_path):
    base = tmp_path / "base"; head = tmp_path / "head"
    base.mkdir(); head.mkdir()
    write(base / "a.txt", b"x"); write(head / "a.txt", b"y")
    write(base / "b.png", b"z"); write(head / "b.png", b"z")
    pairs = image_diff.classify_pairs(base, head)
    assert len(pairs) == 1
    assert pairs[0].rel_path == "b.png"

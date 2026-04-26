import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


def load_build_plugin(tmp_path, monkeypatch):
    """Import scripts/build-plugin with ROOT and VERSION_FILE pointing at tmp_path."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "build-plugin"
    loader = SourceFileLoader("build_plugin", str(script))
    spec = importlib.util.spec_from_loader("build_plugin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)

    version_file = tmp_path / "plugin-version.json"
    version_file.write_text('{"version": "1.0.0"}\n')

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "VERSION_FILE", version_file)
    return mod


def test_read_version(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    assert mod.read_version() == "1.0.0"


def test_bump_version():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build-plugin"
    loader = SourceFileLoader("build_plugin", str(script))
    spec = importlib.util.spec_from_loader("build_plugin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    assert mod.bump_version("1.0.0") == "1.0.1"
    assert mod.bump_version("2.3.9") == "2.3.10"


def setup_source_files(tmp_path: Path) -> None:
    """Create minimal source files that build-plugin reads or preserves."""
    skill_dir = tmp_path / "skills" / "bugshot"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: bugshot\n---\n")
    for name in ["bugshot_cli.py", "bugshot_workflow.py", "gallery_server.py", "ansi_render.py"]:
        (tmp_path / name).write_text(f"# {name}\n")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "style.css").write_text("")
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "index.html").write_text("")


def test_build_generates_manifests(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    claude = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
    assert claude["name"] == "bugshot"
    assert claude["version"] == "1.0.0"
    assert "description" in claude
    assert claude["author"]["name"] == "Ketan Gangatirkar"

    codex = json.loads((tmp_path / ".codex-plugin" / "plugin.json").read_text())
    assert codex["version"] == "1.0.0"
    assert codex["author"]["email"] == "ketan@gangatirkar.com"
    assert "interface" in codex
    assert codex["interface"]["brandColor"] == "#2090C8"


def test_build_generates_skill_dir(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    skill_md = tmp_path / "skills" / "bugshot" / "SKILL.md"
    skill_md.write_text("---\nname: bugshot\n---\n# canonical edit\n")

    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    skill_dir = tmp_path / "skills" / "bugshot"
    assert skill_md.read_text() == "---\nname: bugshot\n---\n# canonical edit\n", \
        "build-plugin must not clobber the canonical SKILL.md"
    for name in mod.SKILL_FILES:
        assert (skill_dir / name).exists(), f"missing {name} in skills/bugshot/"
    assert (skill_dir / "static").is_dir()
    assert (skill_dir / "templates").is_dir()


def test_build_generates_assets(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    assets = tmp_path / "assets"
    assert (assets / "icon.png").exists()
    assert (assets / "logo.png").exists()
    for v in range(1, 4):
        assert (assets / f"screenshot-{v}.png").exists()


def test_bump_flag_increments_version(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin", "--bump"])
    mod.main()

    version_file = tmp_path / "plugin-version.json"
    assert json.loads(version_file.read_text())["version"] == "1.0.1"
    claude = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
    assert claude["version"] == "1.0.1"


def test_no_bump_flag_is_idempotent(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()
    mod.main()

    version_file = tmp_path / "plugin-version.json"
    assert json.loads(version_file.read_text())["version"] == "1.0.0"

import importlib.util
import json
import subprocess
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
    mod._real_compile_frontend = mod.compile_frontend
    monkeypatch.setattr(mod, "compile_frontend", lambda verbose=False: None)
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


SHARED_SKILL_PYTHON_FILES = [
    "bugshot_cli.py",
    "bugshot_workflow.py",
    "gallery_server.py",
    "ansi_render.py",
    "vizline_cli.py",
    "vizline_workflow.py",
    "vizdiff_cli.py",
    "vizdiff_workflow.py",
    "vizdiff_review_root.py",
    "baseline_manifest.py",
    "capture_runner.py",
    "image_diff.py",
]


def setup_source_files(tmp_path: Path) -> None:
    """Create minimal source files that build-plugin reads or preserves."""
    for skill_name in ("bugshot", "vizline", "vizdiff"):
        skill_dir = tmp_path / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_name}\n---\n")
    for name in SHARED_SKILL_PYTHON_FILES:
        (tmp_path / name).write_text(f"# {name}\n")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "gallery.ts").write_text("(() => {})();\n")
    (tmp_path / "static" / "gallery.js").write_text("stale js\n")
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


def test_build_compiles_gallery_typescript_before_copying_skills(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        (tmp_path / "static" / "gallery.js").write_text("compiled js\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "compile_frontend", mod._real_compile_frontend)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    assert calls == [(["npm", "run", "build:frontend"], tmp_path, True)]
    assert (tmp_path / "static" / "gallery.js").read_text() == "compiled js\n"
    assert (tmp_path / "skills" / "bugshot" / "static" / "gallery.js").read_text() == "compiled js\n"
    assert not (tmp_path / "skills" / "bugshot" / "static" / "gallery.ts").exists()


def test_build_generates_vizline_skill(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    skill_dir = tmp_path / "skills" / "vizline"
    for name in mod.SKILL_PLUGINS["vizline"]["files"]:
        assert (skill_dir / name).exists(), f"missing {name} in skills/vizline/"
    # vizline doesn't ship templates or static.
    assert not (skill_dir / "static").exists()
    assert not (skill_dir / "templates").exists()


def test_build_generates_vizdiff_skill(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    skill_dir = tmp_path / "skills" / "vizdiff"
    for name in mod.SKILL_PLUGINS["vizdiff"]["files"]:
        assert (skill_dir / name).exists(), f"missing {name} in skills/vizdiff/"
    assert (skill_dir / "static").is_dir()
    assert (skill_dir / "templates").is_dir()


def test_build_preserves_each_skill_md(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    canonical = {
        "bugshot": "---\nname: bugshot\n---\n# canonical bugshot\n",
        "vizline": "---\nname: vizline\n---\n# canonical vizline\n",
        "vizdiff": "---\nname: vizdiff\n---\n# canonical vizdiff\n",
    }
    for skill_name, body in canonical.items():
        (tmp_path / "skills" / skill_name / "SKILL.md").write_text(body)

    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    for skill_name, body in canonical.items():
        actual = (tmp_path / "skills" / skill_name / "SKILL.md").read_text()
        assert actual == body, f"build-plugin clobbered skills/{skill_name}/SKILL.md"


def test_codex_manifest_points_at_skills_root(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    codex = json.loads((tmp_path / ".codex-plugin" / "plugin.json").read_text())
    assert codex["skills"] == "./.codex-plugin/skills"


def test_build_generates_agent_specific_skill_payloads(tmp_path, monkeypatch):
    mod = load_build_plugin(tmp_path, monkeypatch)
    setup_source_files(tmp_path)
    skill_dir = tmp_path / "skills" / "bugshot"
    skill_dir.joinpath("SKILL.md").write_text("canonical skill\n")
    overlay_dir = skill_dir / "overlays"
    overlay_dir.mkdir()
    overlay_dir.joinpath("codex.md").write_text("codex overlay\n")
    overlay_dir.joinpath("claude.md").write_text("claude overlay\n")

    monkeypatch.setattr(sys, "argv", ["build-plugin"])
    mod.main()

    canonical = skill_dir.joinpath("SKILL.md").read_text()
    codex = tmp_path.joinpath(".codex-plugin", "skills", "bugshot", "SKILL.md").read_text()
    claude = tmp_path.joinpath(".claude", "skills", "bugshot.md").read_text()

    assert canonical == "canonical skill\n"
    assert codex == "canonical skill\n\ncodex overlay\n"
    assert claude == "canonical skill\n\nclaude overlay\n"
    assert "claude overlay" not in codex
    assert "codex overlay" not in claude
    assert tmp_path.joinpath(".codex-plugin", "skills", "bugshot", "bugshot_cli.py").exists()


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

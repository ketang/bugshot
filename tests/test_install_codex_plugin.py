import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-codex-plugin"


def create_source_tree(root: Path) -> None:
    codex_manifest_dir = root / ".codex-plugin"
    codex_manifest_dir.mkdir(parents=True)
    (codex_manifest_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "bugshot",
                "version": "1.0.0",
                "description": "Test plugin",
                "skills": "./skills",
            }
        )
        + "\n"
    )

    skill_dir = root / "skills" / "bugshot"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: bugshot\n---\n")

    assets_dir = root / "assets"
    assets_dir.mkdir()
    (assets_dir / "icon.png").write_bytes(b"png")

    (root / "plugin-version.json").write_text('{"version": "1.0.0"}\n')
    (root / "INSTALL.md").write_text("# Install\n")


def run_installer(*args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_help_flag_succeeds() -> None:
    result = run_installer("--help")

    assert result.returncode == 0
    assert "Install the Bugshot Codex plugin" in result.stdout
    assert "--marketplace-root" in result.stdout


def test_dry_run_does_not_write_marketplace(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    create_source_tree(source)
    marketplace = tmp_path / "marketplace"

    result = run_installer(
        "--source",
        str(source),
        "--marketplace-root",
        str(marketplace),
        "--skip-build",
        "--skip-register",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "Would install Bugshot Codex plugin" in result.stdout
    assert not marketplace.exists()


def test_installer_writes_local_marketplace(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    create_source_tree(source)
    marketplace = tmp_path / "marketplace"

    result = run_installer(
        "--source",
        str(source),
        "--marketplace-root",
        str(marketplace),
        "--skip-build",
        "--skip-register",
        "--verbose",
    )

    assert result.returncode == 0, result.stderr

    plugin_root = marketplace / "plugins" / "bugshot"
    assert (plugin_root / ".codex-plugin" / "plugin.json").is_file()
    assert (plugin_root / "skills" / "bugshot" / "SKILL.md").is_file()
    assert (plugin_root / "assets" / "icon.png").is_file()
    assert (plugin_root / "plugin-version.json").is_file()
    assert (plugin_root / "INSTALL.md").is_file()

    manifest_path = marketplace / ".agents" / "plugins" / "marketplace.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "bugshot"
    assert manifest["interface"]["displayName"] == "Bugshot"

    plugin_entry = manifest["plugins"][0]
    assert plugin_entry["name"] == "bugshot"
    assert plugin_entry["source"] == {
        "source": "local",
        "path": "./plugins/bugshot",
    }
    assert plugin_entry["policy"] == {
        "installation": "INSTALLED_BY_DEFAULT",
        "authentication": "ON_INSTALL",
    }
    assert plugin_entry["category"] == "Coding"

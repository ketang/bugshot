from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_INVOCATION = (
    'python3 {{bugshot_dir}}/bugshot_cli.py --json --bind "$bind_address" {{directory}}'
)


def test_bugshot_skill_forbids_rtk_gallery_invocation_prefix() -> None:
    skill = (REPO_ROOT / "skills" / "bugshot" / "SKILL.md").read_text()
    codex_overlay = (
        REPO_ROOT / "skills" / "bugshot" / "overlays" / "codex.md"
    ).read_text()

    assert GALLERY_INVOCATION in skill
    assert f"rtk {GALLERY_INVOCATION}" not in skill
    assert "Do not prefix this gallery process invocation with `rtk`" in skill
    assert "Do not prefix the gallery process invocation with `rtk`" in codex_overlay

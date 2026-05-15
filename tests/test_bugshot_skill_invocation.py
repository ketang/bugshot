from pathlib import Path
import stat


REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_INVOCATION = (
    '{{bugshot_dir}}/bugshot_cli.py --json --bind "$bind_address" {{directory}}'
)
WRAPPED_GALLERY_INVOCATIONS = (
    f"rtk {GALLERY_INVOCATION}",
    f"python3 {GALLERY_INVOCATION}",
)


def test_bugshot_skill_forbids_rtk_gallery_invocation_prefix() -> None:
    skill = (REPO_ROOT / "skills" / "bugshot" / "SKILL.md").read_text()
    codex_overlay = (
        REPO_ROOT / "skills" / "bugshot" / "overlays" / "codex.md"
    ).read_text()
    normalized_skill = " ".join(skill.split())

    assert GALLERY_INVOCATION in skill
    for wrapped_invocation in WRAPPED_GALLERY_INVOCATIONS:
        assert wrapped_invocation not in skill
    assert "Do not prefix this gallery process invocation with `python3`, `rtk`" in normalized_skill
    assert "Do not prefix the gallery process invocation with `python3` or `rtk`" in codex_overlay


def test_bugshot_cli_is_executable_for_direct_skill_invocation() -> None:
    mode = (REPO_ROOT / "bugshot_cli.py").stat().st_mode

    assert mode & stat.S_IXUSR

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_wire(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "wire_bugshot_cli.py"), *args],
        capture_output=True,
        text=True,
    )


def test_wire_writes_executable_capture_command(fake_git_worktree: Path) -> None:
    result = run_wire([
        "--worktree", str(fake_git_worktree),
        "--capture-command",
        """python3 -c "from pathlib import Path; out=Path('{output_dir}'); (out / 'pages').mkdir(); (out / 'pages' / 'home.png').write_text('shot')" """,
    ])

    assert result.returncode == 0, result.stderr
    capture = fake_git_worktree / ".agent-plugins/bento/bugshot/viz/capture-command"
    assert capture.is_file()
    assert os.access(capture, os.X_OK)

    output_dir = fake_git_worktree / "manual-output"
    invoked = subprocess.run([str(capture), str(output_dir)], capture_output=True, text=True)
    assert invoked.returncode == 0, invoked.stderr
    assert (output_dir / "pages" / "home.png").read_text() == "shot"


def test_wire_refuses_nondeterministic_output_paths(fake_git_worktree: Path) -> None:
    result = run_wire([
        "--worktree", str(fake_git_worktree),
        "--capture-command",
        """python3 -c "import time; from pathlib import Path; out=Path('{output_dir}'); out.mkdir(exist_ok=True); (out / (str(time.time_ns()) + '.png')).write_text('shot')" """,
    ])

    assert result.returncode != 0
    assert "nondeterministic" in result.stderr.lower()
    assert not (fake_git_worktree / ".agent-plugins/bento/bugshot/viz/capture-command").exists()


def test_wire_seed_baseline_creates_vizline_manifest(fake_git_worktree: Path) -> None:
    result = run_wire([
        "--worktree", str(fake_git_worktree),
        "--capture-command",
        """python3 -c "from pathlib import Path; out=Path('{output_dir}'); (out / 'pages').mkdir(); (out / 'pages' / 'home.png').write_text('shot')" """,
        "--base-ref", "main",
        "--seed-baseline",
    ])

    assert result.returncode == 0, result.stderr
    manifest_path = fake_git_worktree / ".bugshot" / "baseline" / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["image_count"] == 1
    assert manifest["images"][0]["path"] == "pages/home.png"

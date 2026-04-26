import os
import stat
from pathlib import Path

import pytest

import capture_runner


VIZ_DIR_REL = ".agent-plugins/bento/bugshot/viz"


def make_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def fake_worktree(tmp_path: Path) -> Path:
    (tmp_path / VIZ_DIR_REL).mkdir(parents=True)
    return tmp_path


def test_locate_returns_path_when_executable(fake_worktree):
    target = fake_worktree / VIZ_DIR_REL / "capture-command"
    make_executable(target, "#!/bin/sh\nexit 0\n")
    assert capture_runner.locate(fake_worktree, "capture-command") == target


def test_locate_returns_none_when_absent(fake_worktree):
    assert capture_runner.locate(fake_worktree, "capture-command") is None


def test_locate_returns_none_when_present_but_not_executable(fake_worktree):
    target = fake_worktree / VIZ_DIR_REL / "capture-command"
    target.write_text("#!/bin/sh\nexit 0\n")  # not chmod +x
    assert capture_runner.locate(fake_worktree, "capture-command") is None


def test_run_capture_writes_to_output_dir(fake_worktree, tmp_path):
    target = fake_worktree / VIZ_DIR_REL / "capture-command"
    make_executable(target, '#!/bin/sh\nmkdir -p "$1/sub"\necho "fake" > "$1/sub/a.png"\n')
    output = tmp_path / "out"; output.mkdir()
    result = capture_runner.run_capture(target, output, env={})
    assert result.returncode == 0
    assert (output / "sub" / "a.png").read_text() == "fake\n"


def test_run_capture_propagates_failure(fake_worktree, tmp_path):
    target = fake_worktree / VIZ_DIR_REL / "capture-command"
    make_executable(target, '#!/bin/sh\necho boom >&2\nexit 7\n')
    output = tmp_path / "out"; output.mkdir()
    result = capture_runner.run_capture(target, output, env={})
    assert result.returncode == 7
    assert "boom" in result.stderr


def test_run_should_baseline_passes_env_vars(fake_worktree):
    target = fake_worktree / VIZ_DIR_REL / "should-baseline"
    make_executable(
        target,
        '#!/bin/sh\necho branch=$BUGSHOT_BRANCH base=$BUGSHOT_BASE_SHA\nexit 0\n',
    )
    env = {"BUGSHOT_BRANCH": "feature/x", "BUGSHOT_BASE_SHA": "abc"}
    result = capture_runner.run_should_baseline(target, fake_worktree, env=env)
    assert result.returncode == 0
    assert "branch=feature/x" in result.stdout
    assert "base=abc" in result.stdout


def test_run_ephemeral_root_returns_first_line(fake_worktree, tmp_path):
    target = fake_worktree / VIZ_DIR_REL / "ephemeral-root"
    placement = tmp_path / "place"; placement.mkdir()
    make_executable(target, f'#!/bin/sh\necho "{placement}"\n')
    result = capture_runner.run_ephemeral_root(target, fake_worktree)
    assert result.returncode == 0
    assert result.stdout.strip() == str(placement)

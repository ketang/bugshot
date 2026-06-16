import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_vizline(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "vizline_cli.py"), *args],
        capture_output=True, text=True,
    )


def edit_capture_command_to_change_one_image(worktree: Path) -> None:
    script = worktree / ".agent-plugins/bento/bugshot/viz/capture-command"
    script.write_text(
        "#!/bin/sh\n"
        "out=\"$1\"\n"
        "mkdir -p \"$out/pages/login\"\n"
        "printf 'HEAD-LOGIN' > \"$out/pages/login/desktop.png\"\n"   # changed
        "printf 'BASE-WELCOME' > \"$out/pages/welcome.png\"\n"       # unchanged
        "printf 'NEW-ABOUT' > \"$out/pages/about.png\"\n"            # added
    )
    script.chmod(0o755)
    subprocess.run(["git", "-C", str(worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-q", "-m", "head-changes"], check=True)


def submit_comment(url: str, unit_id: str, body: str) -> None:
    payload = json.dumps({"unit_id": unit_id, "body": body}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"{url}/api/comments", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )).read()


def signal_done(url: str) -> None:
    urllib.request.urlopen(urllib.request.Request(
        f"{url}/api/done", data=b"", method="POST",
    )).read()


def test_vizdiff_emits_unit_shaped_drafts_with_vizdiff_block(fake_git_worktree, fake_capture_command):
    assert run_vizline(
        ["--feature-worktree", str(fake_git_worktree), "--base-ref", "main"]
    ).returncode == 0

    subprocess.run(["git", "-C", str(fake_git_worktree), "checkout", "-q", "-b", "feature/x"], check=True)
    edit_capture_command_to_change_one_image(fake_git_worktree)

    import vizdiff_workflow

    def session_hook(server):
        time.sleep(0.5)
        submit_comment(server.url, "pages__login__desktop.png", "submit btn regressed")
        signal_done(server.url)

    drafts = vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        base_ref="main",
        bind_address="127.0.0.1",
        on_server_ready=session_hook,
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["unit_id"] == "pages__login__desktop.png"
    assert draft["unit_label"] == "pages/login/desktop.png"
    assert draft["user_comment"] == "submit btn regressed"
    assert "reference.png" in draft["asset_names"]
    assert "candidate.png" in draft["asset_names"]
    assert draft["reference_asset_name"] == "reference.png"
    assert draft["vizdiff"]["classification"] == "changed"
    assert draft["vizdiff"]["relative_path"] == "pages/login/desktop.png"


def test_vizdiff_errors_clearly_when_baseline_missing(fake_git_worktree, fake_capture_command):
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "vizdiff_cli.py"), str(fake_git_worktree), "--local-only"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "baseline" in result.stderr.lower()
    assert "--from-base-ref" in result.stderr


def test_vizdiff_cli_uses_bind_selector_by_default(tmp_path, monkeypatch):
    import vizdiff_cli

    selected = []

    monkeypatch.setattr(
        vizdiff_cli.vizdiff_workflow,
        "build_review_root_from_manifest",
        lambda manifest: tmp_path,
    )
    monkeypatch.setattr(vizdiff_cli, "select_bind_address", lambda: "127.0.0.1")
    monkeypatch.setattr(
        vizdiff_cli.bugshot_workflow,
        "run_review_session",
        lambda **kwargs: selected.append(kwargs["bind_address"]) or 0,
    )

    assert vizdiff_cli.main(["--manifest", str(tmp_path / "manifest.json"), "--json"]) == 0
    assert selected == ["127.0.0.1"]


def test_vizdiff_cli_default_bind_keeps_helper_stderr_before_gallery_url(
    tmp_path, monkeypatch, capfd
):
    import vizdiff_cli

    helper = tmp_path / "select-bind-address"
    helper.write_text(
        "#!/bin/sh\n"
        "printf 'Bugshot bind selection: using 127.0.0.1 (test).\\n' >&2\n"
        "printf '127.0.0.1\\n'\n"
    )
    helper.chmod(0o755)

    monkeypatch.setattr(
        vizdiff_cli.vizdiff_workflow,
        "build_review_root_from_manifest",
        lambda manifest: tmp_path,
    )
    monkeypatch.setattr(vizdiff_cli, "bind_selector_path", lambda: helper)

    def fake_review_session(**kwargs):
        print("Gallery is running at http://127.0.0.1:12345", file=sys.stderr)
        return 0

    monkeypatch.setattr(
        vizdiff_cli.bugshot_workflow,
        "run_review_session",
        fake_review_session,
    )

    assert vizdiff_cli.main(["--manifest", str(tmp_path / "manifest.json"), "--json"]) == 0
    stderr_lines = capfd.readouterr().err.splitlines()
    assert stderr_lines[0].startswith("Bugshot bind selection:")
    assert "Gallery is running at http://127.0.0.1:12345" in stderr_lines


def test_vizdiff_cli_preserves_explicit_bind_override(tmp_path, monkeypatch):
    import vizdiff_cli

    selected = []

    monkeypatch.setattr(
        vizdiff_cli.vizdiff_workflow,
        "build_review_root_from_manifest",
        lambda manifest: tmp_path,
    )
    monkeypatch.setattr(
        vizdiff_cli,
        "select_bind_address",
        lambda: pytest.fail("explicit --bind should not call the selector"),
    )
    monkeypatch.setattr(
        vizdiff_cli.bugshot_workflow,
        "run_review_session",
        lambda **kwargs: selected.append(kwargs["bind_address"]) or 0,
    )

    assert vizdiff_cli.main([
        "--manifest", str(tmp_path / "manifest.json"),
        "--bind", "0.0.0.0",
        "--json",
    ]) == 0
    assert selected == ["0.0.0.0"]


def test_vizdiff_cli_preserves_local_only_override(tmp_path, monkeypatch):
    import vizdiff_cli

    selected = []

    monkeypatch.setattr(
        vizdiff_cli.vizdiff_workflow,
        "build_review_root_from_manifest",
        lambda manifest: tmp_path,
    )
    monkeypatch.setattr(
        vizdiff_cli,
        "select_bind_address",
        lambda: pytest.fail("--local-only should not call the selector"),
    )
    monkeypatch.setattr(
        vizdiff_cli.bugshot_workflow,
        "run_review_session",
        lambda **kwargs: selected.append(kwargs["bind_address"]) or 0,
    )

    assert vizdiff_cli.main([
        "--manifest", str(tmp_path / "manifest.json"),
        "--local-only",
        "--json",
    ]) == 0
    assert selected == ["127.0.0.1"]


def test_vizdiff_cli_checks_review_manifest_without_feature_worktree(tmp_path):
    import vizdiff_cli

    passing_manifest = tmp_path / "passing-review-manifest.json"
    passing_manifest.write_text(
        json.dumps(
            {
                "schema": "bugshot.vizdiff-review/v1",
                "unit_count": 1,
                "expected_units": [{"id": "login.png", "label": "login.png"}],
                "units": [
                    {
                        "id": "login.png",
                        "label": "login.png",
                        "seen": True,
                        "commented": False,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    failing_manifest = tmp_path / "failing-review-manifest.json"
    failing_manifest.write_text(
        json.dumps(
            {
                "schema": "bugshot.vizdiff-review/v1",
                "unit_count": 1,
                "expected_units": [{"id": "login.png", "label": "login.png"}],
                "units": [
                    {
                        "id": "login.png",
                        "label": "login.png",
                        "seen": False,
                        "commented": False,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert vizdiff_cli.main(["--check-review-manifest", str(passing_manifest)]) == 0
    assert vizdiff_cli.main(["--check-review-manifest", str(failing_manifest)]) == 1


def test_vizdiff_head_only_skips_baseline_lookup(fake_git_worktree, fake_capture_command):
    """--head-only should classify every image as 'added' without needing a baseline."""
    import vizdiff_workflow

    def session_hook(server):
        time.sleep(0.3)
        signal_done(server.url)

    drafts = vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        head_only=True,
        bind_address="127.0.0.1",
        on_server_ready=session_hook,
    )
    assert drafts == []  # no comments → no drafts; the call should still complete cleanly

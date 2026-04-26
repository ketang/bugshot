"""End-to-end vizline → vizdiff round trip with a real fake project."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_full_round_trip(fake_git_worktree, fake_capture_command):
    """vizline at main → switch branch + diverge HEAD → vizdiff → 1 changed unit draft."""
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "vizline_cli.py"),
         "--feature-worktree", str(fake_git_worktree), "--base-ref", "main"],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr

    subprocess.run(["git", "-C", str(fake_git_worktree), "checkout", "-q", "-b", "feature/x"], check=True)
    script = fake_git_worktree / ".agent-plugins/bento/bugshot/viz/capture-command"
    script.write_text(
        "#!/bin/sh\n"
        "out=\"$1\"\n"
        "mkdir -p \"$out/pages/login\"\n"
        "printf 'HEAD-LOGIN' > \"$out/pages/login/desktop.png\"\n"
        "printf 'BASE-WELCOME' > \"$out/pages/welcome.png\"\n"
    )
    script.chmod(0o755)
    subprocess.run(["git", "-C", str(fake_git_worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(fake_git_worktree), "commit", "-q", "-m", "diverge"], check=True)

    import vizdiff_workflow

    def session(server):
        time.sleep(0.5)
        url = server.url
        payload = json.dumps({
            "unit_id": "pages__login__desktop.png",
            "body": "regression here",
        }).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/comments", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )).read()
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/done", data=b"", method="POST",
        )).read()

    drafts = vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        base_ref="main",
        bind_address="127.0.0.1",
        on_server_ready=session,
    )
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["vizdiff"]["classification"] == "changed"
    assert draft["vizdiff"]["relative_path"] == "pages/login/desktop.png"
    assert draft["user_comment"] == "regression here"


def test_full_round_trip_with_added_and_removed_units(fake_git_worktree, fake_capture_command):
    """Verify added + removed classifications propagate end-to-end."""
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "vizline_cli.py"),
         "--feature-worktree", str(fake_git_worktree), "--base-ref", "main"],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stderr

    # Mutate capture-command so HEAD adds and removes images.
    subprocess.run(["git", "-C", str(fake_git_worktree), "checkout", "-q", "-b", "feature/y"], check=True)
    script = fake_git_worktree / ".agent-plugins/bento/bugshot/viz/capture-command"
    script.write_text(
        "#!/bin/sh\n"
        "out=\"$1\"\n"
        "mkdir -p \"$out/pages/login\"\n"
        "printf 'BASE-LOGIN' > \"$out/pages/login/desktop.png\"\n"  # unchanged
        # pages/welcome.png removed
        "printf 'NEW-DASHBOARD' > \"$out/pages/dashboard.png\"\n"   # added
    )
    script.chmod(0o755)
    subprocess.run(["git", "-C", str(fake_git_worktree), "add", "."], check=True)
    subprocess.run(["git", "-C", str(fake_git_worktree), "commit", "-q", "-m", "+/- units"], check=True)

    import vizdiff_workflow

    def session(server):
        time.sleep(0.5)
        url = server.url
        for unit_id, body in [
            ("pages__dashboard.png", "new page; review copy"),
            ("pages__welcome.png", "missing — confirm intentional"),
        ]:
            payload = json.dumps({"unit_id": unit_id, "body": body}).encode()
            urllib.request.urlopen(urllib.request.Request(
                f"{url}/api/comments", data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )).read()
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/done", data=b"", method="POST",
        )).read()

    drafts = vizdiff_workflow.run_in_process(
        feature_worktree=fake_git_worktree,
        base_ref="main",
        bind_address="127.0.0.1",
        on_server_ready=session,
    )
    by_unit = {d["unit_id"]: d for d in drafts}
    assert by_unit["pages__dashboard.png"]["vizdiff"]["classification"] == "added"
    assert by_unit["pages__welcome.png"]["vizdiff"]["classification"] == "removed"

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "bugshot" / "select-bind-address"


def run_selector(extra_env=None):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"}
    }
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [str(SCRIPT)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_selects_loopback_without_remote_login_signals():
    result = run_selector()

    assert result.stdout == "127.0.0.1\n"
    assert "using 127.0.0.1" in result.stderr
    assert "no SSH login environment variables were present" in result.stderr


def test_selects_all_interfaces_for_ssh_connection():
    result = run_selector({"SSH_CONNECTION": "192.0.2.10 55555 198.51.100.20 22"})

    assert result.stdout == "0.0.0.0\n"
    assert "using 0.0.0.0" in result.stderr
    assert "SSH login environment variable was present" in result.stderr

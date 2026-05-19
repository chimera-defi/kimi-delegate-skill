#!/usr/bin/env python3
"""Regression tests for pi-wrapper-binary.py behavior."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _make_wrapper_link(tmp_path: Path, name: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    wrapper = root / "scripts" / "pi-wrapper-binary.py"
    link = tmp_path / name
    link.symlink_to(wrapper)
    return link


def test_subagent_check_maps_to_delegate_check(tmp_path: Path) -> None:
    kd = tmp_path / "kd"
    _write_executable(
        kd,
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
    )

    subagent = _make_wrapper_link(tmp_path, "pi-kimi-subagent")
    env = {
        **os.environ,
        "KIMI_DELEGATE_SCRIPT": str(kd),
        "PI_REAL_BINARY": "/bin/echo",
        "PI_KIMI_SUBAGENT_REAL_BINARY": "/bin/echo",
    }

    proc = subprocess.run([str(subagent), "--check"], capture_output=True, text=True, env=env, check=False)

    assert proc.returncode == 0
    assert proc.stdout.strip() == "--check"


def test_recursion_depth_guard_bypasses_kd_when_depth_exceeded(tmp_path: Path) -> None:
    real_pi = tmp_path / "real-pi"
    _write_executable(real_pi, "#!/usr/bin/env bash\necho REAL:$*\n")

    kd = tmp_path / "kd"
    _write_executable(kd, "#!/usr/bin/env bash\necho KD:$*\n")

    pi = _make_wrapper_link(tmp_path, "pi")
    env = {
        **os.environ,
        "KIMI_DELEGATE_SCRIPT": str(kd),
        "PI_REAL_BINARY": str(real_pi),
        "PI_KIMI_SUBAGENT_REAL_BINARY": "/bin/echo",
        "KIMI_DELEGATE_DEPTH": "2",
    }

    proc = subprocess.run(
        [str(pi), "--provider", "kimi-coding", "--model", "k2p6", "--print", "task"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.strip() == "REAL:--provider kimi-coding --model k2p6 --print task"
    assert "KD:" not in proc.stdout


def test_dash_prefixed_print_task_skips_flags_not_treated_as_task_value(tmp_path: Path) -> None:
    kd = tmp_path / "kd"
    _write_executable(
        kd,
        "#!/usr/bin/env bash\nprintf '%s\n' \"$@\"\n",
    )

    pi = _make_wrapper_link(tmp_path, "pi")
    env = {
        **os.environ,
        "KIMI_DELEGATE_SCRIPT": str(kd),
        "PI_REAL_BINARY": "/bin/echo",
        "PI_KIMI_SUBAGENT_REAL_BINARY": "/bin/echo",
    }

    proc = subprocess.run(
        [
            str(pi),
            "--provider",
            "kimi-coding",
            "--model",
            "k2p6",
            "--print",
            "--check",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # --check is a flag, not a task text; wrapper should fail to extract a task
    assert proc.returncode == 2
    assert "could not extract task" in proc.stderr


def test_dash_prefixed_print_task_value_with_positional(tmp_path: Path) -> None:
    kd = tmp_path / "kd"
    _write_executable(
        kd,
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
    )

    pi = _make_wrapper_link(tmp_path, "pi")
    env = {
        **os.environ,
        "KIMI_DELEGATE_SCRIPT": str(kd),
        "PI_REAL_BINARY": "/bin/echo",
        "PI_KIMI_SUBAGENT_REAL_BINARY": "/bin/echo",
    }

    proc = subprocess.run(
        [
            str(pi),
            "--provider",
            "kimi-coding",
            "--model",
            "k2p6",
            "--print",
            "some-task-here",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.strip() == "--task=some-task-here"


def test_subagent_recursion_guard_uses_real_subagent_binary(tmp_path: Path) -> None:
    real_pi = tmp_path / "real-pi"
    _write_executable(real_pi, "#!/usr/bin/env bash\necho PI:$*\n")

    real_subagent = tmp_path / "real-subagent"
    _write_executable(real_subagent, "#!/usr/bin/env bash\necho SUBAGENT:$*\n")

    subagent = _make_wrapper_link(tmp_path, "pi-kimi-subagent")
    env = {
        **os.environ,
        "KIMI_DELEGATE_ACTIVE": "1",
        "PI_REAL_BINARY": str(real_pi),
        "PI_KIMI_SUBAGENT_REAL_BINARY": str(real_subagent),
    }

    proc = subprocess.run([str(subagent), "ping"], capture_output=True, text=True, env=env, check=False)

    assert proc.returncode == 0
    assert proc.stdout.strip() == "SUBAGENT:ping"


def test_machine_protocol_call_passthrough_to_real_pi(tmp_path: Path) -> None:
    real_pi = tmp_path / "real-pi"
    _write_executable(real_pi, "#!/usr/bin/env bash\necho REAL:$*\n")

    kd = tmp_path / "kd"
    _write_executable(kd, "#!/usr/bin/env bash\necho KD:$*\n")

    pi = _make_wrapper_link(tmp_path, "pi")
    env = {
        **os.environ,
        "KIMI_DELEGATE_SCRIPT": str(kd),
        "PI_REAL_BINARY": str(real_pi),
        "PI_KIMI_SUBAGENT_REAL_BINARY": "/bin/echo",
    }

    proc = subprocess.run(
        [
            str(pi),
            "--tools",
            "read,bash,edit,write",
            "--print",
            "--mode",
            "json",
            "--provider",
            "kimi-coding",
            "--model",
            "k2p6",
            "--session",
            "abc123",
            "Test",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.startswith("REAL:")
    assert "KD:" not in proc.stdout

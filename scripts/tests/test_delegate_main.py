#!/usr/bin/env python3
"""Tests for delegate.py main-level behavior (positional args, stdin pipe)."""
from __future__ import annotations

import importlib.util
import subprocess
import unittest.mock
from pathlib import Path


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("delegate_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_positional_task_flag() -> None:
    root = Path(__file__).resolve().parents[2]
    # --print-envelope --dry-run should exit 0 and print the envelope
    proc = subprocess.run(
        [str(root / "scripts" / "delegate.py"), "summarize failing CI run", "--print-envelope", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "summarize failing CI run" in proc.stdout


def test_stdin_pipe_reads_task() -> None:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [str(root / "scripts" / "delegate.py"), "--print-envelope", "--dry-run"],
        input="summarize from stdin",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "summarize from stdin" in proc.stdout


def test_dash_prefixed_task_value_supported() -> None:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [str(root / "scripts" / "delegate.py"), "--task=--check", "--print-envelope", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "\"goal\": \"--check\"" in proc.stdout


def test_auth_error_exits_126_without_fallback(tmp_path: Path) -> None:
    """Contract: an auth/session error exits 126 and does NOT auto-retry via the
    codex fallback engine (the user must re-auth manually)."""
    root = Path(__file__).resolve().parents[2]
    mod = _load(root / "scripts" / "delegate.py")

    calls: list = []

    def fake_call(cmd, timeout):
        calls.append(cmd)
        if any("fallback.py" in str(c) for c in cmd):
            return (0, "# Result\nok\n## Evidence\n-\n## Next steps\n-", "", 1.0)
        # Primary pi execution returns an auth error.
        return (1, "", "authentication failed", 1.0)

    config = {
        "provider": "kimi-coding",
        "model": "k2p6",
        "thinking": "medium",
        "max_retries": 0,
        "fallback_engine": "codex",
        "fallback_provider": "openai",
        "fallback_model": None,
        "timeout_seconds": 30,
        "max_timeout_seconds": 60,
    }
    routing = {"default": {}, "task_classes": {}}

    with unittest.mock.patch.object(mod, "health_check_quick", return_value=(True, "ok")), \
            unittest.mock.patch.object(mod, "call", side_effect=fake_call), \
            unittest.mock.patch.object(mod.shutil, "which", side_effect=lambda n: None if n == "pi-kimi-subagent" else "/usr/bin/pi"):
        rc = mod.run_delegate(
            "summarize the failing run",
            None,
            "summarize",
            False,
            False,
            config,
            routing,
            tmp_path,
            repo_scale={"files": 10, "mb": 1},
        )

    assert rc == 126, f"auth_error must exit 126, got {rc}"
    assert not any(any("fallback.py" in str(c) for c in cmd) for cmd in calls), (
        "auth_error must NOT trigger the codex fallback engine (no auto-retry)"
    )


def test_call_passes_kimi_delegate_active_env() -> None:
    """Regression: KIMI_DELEGATE_ACTIVE=1 must be in the subprocess env so the
    binary wrapper can detect it's being called from within delegate and skip
    re-interception, preventing the rc=2 re-delegation loop."""
    root = Path(__file__).resolve().parents[2]
    mod = _load(root / "scripts" / "delegate.py")

    captured_env: dict = {}

    def fake_run(cmd, *, capture_output, text, timeout, check, env):
        captured_env.update(env or {})
        result = unittest.mock.MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with unittest.mock.patch("subprocess.run", side_effect=fake_run):
        mod.call(["echo", "hi"], timeout=5)

    assert captured_env.get("KIMI_DELEGATE_ACTIVE") == "1", (
        "KIMI_DELEGATE_ACTIVE=1 must be passed to subprocess env to prevent the "
        "binary wrapper from re-intercepting delegate's own pi calls (rc=2 loop)"
    )

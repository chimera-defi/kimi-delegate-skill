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

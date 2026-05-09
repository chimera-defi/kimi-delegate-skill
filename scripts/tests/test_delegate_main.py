#!/usr/bin/env python3
"""Tests for delegate.py main-level behavior (positional args, stdin pipe)."""
from __future__ import annotations

import subprocess
from pathlib import Path


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

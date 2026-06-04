#!/usr/bin/env python3
"""Tests for edge cases identified in external security/reliability review."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_current_repo_root_when_git_missing() -> None:
    """delegate.current_repo_root must not crash when git binary is missing."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    with subprocess_patch(side_effect=FileNotFoundError("git missing")):
        result = mod.current_repo_root(Path("/tmp/fallback"))
    assert result == Path("/tmp/fallback").resolve()


def test_repo_root_from_script_when_git_missing() -> None:
    """telemetry.repo_root_from_script must not crash when git binary is missing."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "kimi_delegate_telemetry.py")
    with subprocess_patch(side_effect=FileNotFoundError("git missing")):
        result = mod.repo_root_from_script()
    # Falls back to __file__.resolve().parents[3] — must be absolute and not crash
    assert isinstance(result, Path)
    assert result.is_absolute()


def test_load_last_task_tolerates_corrupted_tail() -> None:
    """load_last_task must skip corrupted tail lines and find the last valid entry."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        history = repo / "artifacts" / "kimi-delegate" / "history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text(
            '{"task": "first", "timestamp": "2024-01-01T00:00:00Z"}\n'
            '{"task": "second", "timestamp": "2024-01-01T00:00:01Z"}\n'
            'this line is corrupted\n',
            encoding="utf-8",
        )
        assert mod.load_last_task(repo) == "second"


def test_load_last_task_all_corrupted_returns_empty() -> None:
    """load_last_task returns empty string when all lines are corrupted."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        history = repo / "artifacts" / "kimi-delegate" / "history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text("bad line 1\nbad line 2\n", encoding="utf-8")
        assert mod.load_last_task(repo) == ""


def test_safe_context_file_blocks_traversal() -> None:
    """_safe_context_file rejects paths that escape repo_root."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    repo = Path("/tmp/test-repo")
    assert mod._safe_context_file("../etc/passwd", repo) is None
    assert mod._safe_context_file("foo/../../bar", repo) is None


def test_safe_context_file_allows_in_repo() -> None:
    """_safe_context_file allows paths within repo_root."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / "context.md").write_text("hello")
        result = mod._safe_context_file("context.md", repo)
        assert result is not None
        assert "context.md" in result


def test_redact_sensitive_strips_tokens() -> None:
    """_redact_sensitive removes bearer tokens and API keys."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "delegate.py")
    raw = "error: Bearer abc123def456ghi789jkl012mno345pqr678stu\nAPI_KEY=sk-abc123def456ghi789jkl012mno345"
    redacted = mod._redact_sensitive(raw)
    assert "Bearer <REDACTED>" in redacted
    assert "abc123def456ghi789" not in redacted
    assert "API_KEY=<REDACTED>" in redacted


def test_fallback_timeout_exception_returns_rc124() -> None:
    """fallback._run_with_timeout returns rc=124 on TimeoutExpired."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "fallback.py")
    proc = mod._run_with_timeout(["sleep", "10"], timeout=1, env=os.environ.copy())
    assert proc.returncode == 124
    assert "timeout after 1s" in proc.stderr


def test_env_check_catches_timeout() -> None:
    """env_check.check_pi_auth returns error status on timeout, not crash."""
    mod = _load_module(Path(__file__).resolve().parents[2] / "scripts" / "env_check.py")
    import unittest.mock as m
    with m.patch("shutil.which", return_value="/usr/local/bin/pi"), \
         m.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pi", timeout=15)):
        result = mod.check_pi_auth({"provider": "kimi-coding", "model": "k2p6"})
    assert result["status"] == "error"
    assert "timed out" in result["detail"]


def subprocess_patch(side_effect=None):
    """Context manager to patch subprocess.run."""
    import unittest.mock as m
    return m.patch("subprocess.run", side_effect=side_effect)

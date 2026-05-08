#!/usr/bin/env python3
"""Tests for delegate.py helper functions."""
from __future__ import annotations

from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("delegate_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_detect_auth_error_catches_common_patterns() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "delegate.py")

    assert mod.detect_auth_error("authentication failed") is True
    assert mod.detect_auth_error("session expired, please re-auth") is True
    assert mod.detect_auth_error("401 unauthorized") is True
    assert mod.detect_auth_error("403 forbidden") is True
    assert mod.detect_auth_error("token invalid") is True
    assert mod.detect_auth_error("SIWE signature required") is True
    assert mod.detect_auth_error("some random timeout") is False
    assert mod.detect_auth_error("") is False


def test_classify_error() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "delegate.py")

    assert mod.classify_error(124, "anything", False) == "timeout"
    assert mod.classify_error(1, "authentication failed", True) == "auth_error"
    assert mod.classify_error(1, "some crash", True) == "provider_error"
    assert mod.classify_error(0, "", False) == "schema_invalid"


def test_compute_timeout_scaling() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "delegate.py")

    config = {
        "large_repo_threshold_files": 10000,
        "large_repo_threshold_mb": 500,
        "large_repo_timeout_multiplier": 2.0,
        "xlarge_repo_threshold_files": 50000,
        "xlarge_repo_threshold_mb": 1000,
        "xlarge_repo_timeout_multiplier": 3.0,
    }
    routing = {
        "default": {"timeout_scale": 1.0},
        "task_classes": {
            "search": {"timeout_scale": 1.0},
            "review": {"timeout_scale": 1.5},
        },
    }

    # Normal repo
    assert mod.compute_timeout(60, "search", config, routing, {"files": 100, "mb": 10}) == 60

    # Large repo
    assert mod.compute_timeout(60, "search", config, routing, {"files": 20000, "mb": 10}) == 120

    # XLarge repo
    assert mod.compute_timeout(60, "search", config, routing, {"files": 60000, "mb": 10}) == 180

    # Task class scale + large repo multiplier stack
    assert mod.compute_timeout(60, "review", config, routing, {"files": 20000, "mb": 10}) == 180


def test_estimate_repo_scale_returns_sensible_numbers(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "delegate.py")

    # Need a git repo to test properly
    repo = tmp_path / "test-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "file1.txt").write_text("a\n", encoding="utf-8")
    (repo / "file2.txt").write_text("b\n", encoding="utf-8")

    # Fake git ls-files by creating a minimal git structure
    git_dir = repo / ".git"
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    scale = mod.estimate_repo_scale(repo)
    assert isinstance(scale, dict)
    assert "files" in scale
    assert "mb" in scale


def test_output_is_valid_heading_only() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "delegate.py")

    assert mod.output_is_valid("# Result\nfoo", ["Result"]) is True
    assert mod.output_is_valid("Result foo", ["Result"]) is False
    assert mod.output_is_valid("# Result\n## Evidence\nfoo", ["Result", "Evidence"]) is True
    assert mod.output_is_valid("", ["Result"]) is False

#!/usr/bin/env python3
"""Tests for plan_prompt.py classifier."""
from __future__ import annotations

from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("plan_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_classify_scoring_prefers_multiple_matches() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "plan_prompt.py")

    # "fix bug and update tests" matches both implementation-lite (fix, update) and review (bug)
    assert mod.classify("fix bug and update tests") == "implementation-lite"


def test_classify_tie_breaks_by_priority() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "plan_prompt.py")

    # "review and fix" ties at 1 each -> tie-break gives review priority
    assert mod.classify("review and fix") == "review"


def test_classify_defaults_to_summarize() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "plan_prompt.py")

    assert mod.classify("random unrelated words") == "summarize"


def test_classify_security_review() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "plan_prompt.py")

    assert mod.classify("security audit of auth module") == "review"


def test_classify_search() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "plan_prompt.py")

    assert mod.classify("find all react components") == "search"

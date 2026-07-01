#!/usr/bin/env python3
"""Tests for fallback.py codex model handling (WP-C: codex/spark parity)."""
from __future__ import annotations

import importlib.util
import unittest.mock
from pathlib import Path


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("fallback_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _codex_cmd(mod, model) -> list[str]:
    captured: dict = {}

    def fake_run(cmd, timeout, env):
        captured["cmd"] = cmd
        result = unittest.mock.MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    # Force the no-sandbox path so the asserted cmd is deterministic.
    with unittest.mock.patch.object(mod, "codex_supports_sandbox", return_value=False), \
            unittest.mock.patch.object(mod, "_run_with_timeout", side_effect=fake_run):
        mod.run_codex("PROMPT", model, timeout=30)
    return captured["cmd"]


def test_codex_omits_model_for_sentinels() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = _load(root / "scripts" / "fallback.py")
    # Unset / sentinel values must NOT pin --model so codex uses the user's
    # Codex config default (spark parity), and "None" never leaks as a literal.
    for sentinel in (None, "", "default", "spark", "null", "None", "NONE"):
        cmd = _codex_cmd(mod, sentinel)
        assert "--model" not in cmd, f"expected no --model for {sentinel!r}, got {cmd}"
        assert cmd[:2] == ["codex", "exec"]
        assert cmd[-1] == "PROMPT"


def test_codex_pins_real_model() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = _load(root / "scripts" / "fallback.py")
    for real in ("gpt-5.5", "k2p6", "o3"):
        cmd = _codex_cmd(mod, real)
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == real

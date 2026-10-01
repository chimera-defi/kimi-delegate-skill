#!/usr/bin/env python3
"""Unit tests for fallback.py helpers not covered by test_fallback_model.py."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest.mock
from pathlib import Path


def _load():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "fallback.py"
    spec = importlib.util.spec_from_file_location("fallback", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# ── codex_supports_sandbox ────────────────────────────────────────────────────

class TestCodexSupportsSandbox:
    def test_returns_true_when_flag_in_help(self) -> None:
        mod = _load()
        mod.codex_supports_sandbox.cache_clear()
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.MagicMock(
                returncode=0, stdout="usage: codex exec --sandbox ...", stderr=""
            )
            assert mod.codex_supports_sandbox() is True

    def test_returns_false_when_flag_absent(self) -> None:
        mod = _load()
        mod.codex_supports_sandbox.cache_clear()
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.MagicMock(
                returncode=0, stdout="usage: codex exec [opts]", stderr=""
            )
            assert mod.codex_supports_sandbox() is False

    def test_returns_false_on_file_not_found(self) -> None:
        mod = _load()
        mod.codex_supports_sandbox.cache_clear()
        with unittest.mock.patch("subprocess.run", side_effect=FileNotFoundError):
            assert mod.codex_supports_sandbox() is False

    def test_returns_false_on_timeout(self) -> None:
        mod = _load()
        mod.codex_supports_sandbox.cache_clear()
        with unittest.mock.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 10)
        ):
            assert mod.codex_supports_sandbox() is False


# ── _load_config ──────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_returns_default_when_file_missing(self) -> None:
        mod = _load()
        with unittest.mock.patch.object(
            Path, "exists", return_value=False
        ):
            cfg = mod._load_config()
        assert cfg == {"max_timeout_seconds": 180}

    def test_reads_valid_json(self) -> None:
        mod = _load()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"max_timeout_seconds": 300, "extra": "x"}, f)
            tmp = Path(f.name)
        try:
            with unittest.mock.patch.object(Path, "exists", return_value=True), \
                 unittest.mock.patch.object(Path, "read_text", return_value=tmp.read_text()):
                cfg = mod._load_config()
            assert cfg["max_timeout_seconds"] == 300
        finally:
            tmp.unlink(missing_ok=True)

    def test_returns_default_on_invalid_json(self) -> None:
        mod = _load()
        with unittest.mock.patch.object(Path, "exists", return_value=True), \
             unittest.mock.patch.object(Path, "read_text", return_value="{not json}"):
            cfg = mod._load_config()
        assert cfg == {"max_timeout_seconds": 180}


# ── _default_timeout ──────────────────────────────────────────────────────────

class TestDefaultTimeout:
    def test_falls_back_to_180(self) -> None:
        mod = _load()
        with unittest.mock.patch.object(mod, "_load_config", return_value={}):
            assert mod._default_timeout() == 180

    def test_reads_from_config(self) -> None:
        mod = _load()
        with unittest.mock.patch.object(
            mod, "_load_config", return_value={"max_timeout_seconds": 240}
        ):
            assert mod._default_timeout() == 240


# ── _run_with_timeout ────────────────────────────────────────────────────────

class TestRunWithTimeout:
    def test_returns_completed_process_on_success(self) -> None:
        mod = _load()
        env = {}
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(["echo"], 0, stdout="ok", stderr="")
            result = mod._run_with_timeout(["echo", "hi"], 30, env)
        assert result.returncode == 0
        assert result.stdout == "ok"

    def test_returns_returncode_124_on_timeout(self) -> None:
        mod = _load()
        with unittest.mock.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("echo", 30)
        ):
            result = mod._run_with_timeout(["echo"], 30, {})
        assert result.returncode == 124
        assert "timeout" in result.stderr


# ── run_pi command construction ───────────────────────────────────────────────

class TestRunPi:
    def _capture_cmd(self, mod, provider: str, model: str) -> list[str]:
        captured: dict = {}

        def fake_run(cmd, timeout, env):
            captured["cmd"] = cmd
            r = unittest.mock.MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        with unittest.mock.patch.object(mod, "_run_with_timeout", side_effect=fake_run):
            mod.run_pi("PROMPT", provider, model, timeout=30)
        return captured["cmd"]

    def test_includes_provider_and_model(self) -> None:
        mod = _load()
        cmd = self._capture_cmd(mod, "openai", "gpt-5")
        assert "--provider" in cmd
        assert cmd[cmd.index("--provider") + 1] == "openai"
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "gpt-5"

    def test_prompt_is_last_arg(self) -> None:
        mod = _load()
        cmd = self._capture_cmd(mod, "openai", "gpt-5")
        assert cmd[-1] == "PROMPT"

    def test_sets_kimi_delegate_active_env(self) -> None:
        mod = _load()
        seen_env: dict = {}

        def fake_run(cmd, timeout, env):
            seen_env.update(env)
            r = unittest.mock.MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        with unittest.mock.patch.object(mod, "_run_with_timeout", side_effect=fake_run):
            mod.run_pi("P", "openai", "x", timeout=10)
        assert seen_env.get("KIMI_DELEGATE_ACTIVE") == "1"


# ── main() error paths ────────────────────────────────────────────────────────

class TestMainErrorPaths:
    def test_missing_envelope_exits_2(self) -> None:
        mod = _load()
        with unittest.mock.patch("sys.argv", ["fallback", "--envelope-file", "/no/such/file.json"]):
            rc = mod.main()
        assert rc == 2

    def test_invalid_json_envelope_exits_2(self) -> None:
        mod = _load()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("{bad json}")
            tmp = Path(f.name)
        try:
            with unittest.mock.patch("sys.argv", ["fallback", "--envelope-file", str(tmp)]):
                rc = mod.main()
            assert rc == 2
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_codex_binary_exits_127(self) -> None:
        mod = _load()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"task": "do something"}, f)
            tmp = Path(f.name)
        try:
            with unittest.mock.patch("sys.argv", [
                "fallback", "--envelope-file", str(tmp), "--fallback-engine", "codex"
            ]), unittest.mock.patch("shutil.which", return_value=None):
                rc = mod.main()
            assert rc == 127
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_pi_binary_exits_127(self) -> None:
        mod = _load()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"task": "do something"}, f)
            tmp = Path(f.name)
        try:
            with unittest.mock.patch("sys.argv", [
                "fallback", "--envelope-file", str(tmp), "--fallback-engine", "pi"
            ]), unittest.mock.patch("shutil.which", return_value=None):
                rc = mod.main()
            assert rc == 127
        finally:
            tmp.unlink(missing_ok=True)

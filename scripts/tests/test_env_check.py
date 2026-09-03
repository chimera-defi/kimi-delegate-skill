#!/usr/bin/env python3
"""Unit tests for env_check.py — check_binary, check_pi_auth, check_repo_scale."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest.mock as m
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "env_check.py"


def _load() :
    spec = importlib.util.spec_from_file_location("env_check", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


ec = _load()


# ---------------------------------------------------------------------------
# check_binary
# ---------------------------------------------------------------------------

def test_check_binary_found() -> None:
    with m.patch("shutil.which", return_value="/usr/bin/git"):
        result = ec.check_binary("git")
    assert result["name"] == "git"
    assert result["status"] == "ok"
    assert result["path"] == "/usr/bin/git"


def test_check_binary_missing() -> None:
    with m.patch("shutil.which", return_value=None):
        result = ec.check_binary("nonexistent-tool")
    assert result["name"] == "nonexistent-tool"
    assert result["status"] == "missing"
    assert result["path"] == ""


def test_check_binary_returns_exact_path() -> None:
    with m.patch("shutil.which", return_value="/custom/bin/pi"):
        result = ec.check_binary("pi")
    assert result["path"] == "/custom/bin/pi"


# ---------------------------------------------------------------------------
# check_pi_auth
# ---------------------------------------------------------------------------

def test_check_pi_auth_skipped_when_pi_absent() -> None:
    with m.patch("shutil.which", return_value=None):
        result = ec.check_pi_auth({})
    assert result["name"] == "pi-auth"
    assert result["status"] == "skipped"
    assert "not installed" in result["detail"]


def test_check_pi_auth_ok_on_zero_returncode() -> None:
    fake = m.MagicMock()
    fake.returncode = 0
    fake.stderr = ""
    with m.patch("shutil.which", return_value="/usr/bin/pi"), \
         m.patch("subprocess.run", return_value=fake):
        result = ec.check_pi_auth({"provider": "kimi-coding", "model": "k2p6"})
    assert result["status"] == "ok"
    assert "responsive" in result["detail"]


def test_check_pi_auth_detects_auth_error_in_stderr() -> None:
    fake = m.MagicMock()
    fake.returncode = 1
    fake.stderr = "Error: unauthorized - token expired"
    with m.patch("shutil.which", return_value="/usr/bin/pi"), \
         m.patch("subprocess.run", return_value=fake):
        result = ec.check_pi_auth({"provider": "kimi-coding", "model": "k2p6"})
    assert result["status"] == "auth_error"
    assert "auth" in result["detail"].lower() or "session" in result["detail"].lower()


def test_check_pi_auth_generic_error_on_nonzero_clean_stderr() -> None:
    fake = m.MagicMock()
    fake.returncode = 2
    fake.stderr = "something went wrong"
    with m.patch("shutil.which", return_value="/usr/bin/pi"), \
         m.patch("subprocess.run", return_value=fake):
        result = ec.check_pi_auth({})
    assert result["status"] == "error"
    assert "rc=2" in result["detail"]


def test_check_pi_auth_uses_config_provider_and_model() -> None:
    """subprocess.run must be called with the provider/model from config."""
    fake = m.MagicMock()
    fake.returncode = 0
    fake.stderr = ""
    with m.patch("shutil.which", return_value="/usr/bin/pi"), \
         m.patch("subprocess.run", return_value=fake) as mock_run:
        ec.check_pi_auth({"provider": "my-provider", "model": "my-model"})
    call_args = mock_run.call_args[0][0]
    assert "my-provider" in call_args
    assert "my-model" in call_args


def test_check_pi_auth_defaults_when_config_empty() -> None:
    fake = m.MagicMock()
    fake.returncode = 0
    fake.stderr = ""
    with m.patch("shutil.which", return_value="/usr/bin/pi"), \
         m.patch("subprocess.run", return_value=fake) as mock_run:
        ec.check_pi_auth({})
    call_args = mock_run.call_args[0][0]
    assert "kimi-coding" in call_args
    assert "k2p6" in call_args


# ---------------------------------------------------------------------------
# check_repo_scale
# ---------------------------------------------------------------------------

def _make_git_du_mocks(git_stdout: str, git_rc: int, du_stdout: str, du_rc: int):
    """Return a side_effect list for two subprocess.run calls: git ls-files, du."""
    git_proc = m.MagicMock()
    git_proc.returncode = git_rc
    git_proc.stdout = git_stdout

    du_proc = m.MagicMock()
    du_proc.returncode = du_rc
    du_proc.stdout = du_stdout

    return [git_proc, du_proc]


def test_check_repo_scale_counts_files() -> None:
    files_out = "a.py\nb.py\nc.py\n"
    side_effects = _make_git_du_mocks(files_out, 0, "10\t.\n", 0)
    with tempfile.TemporaryDirectory() as td, \
         m.patch("subprocess.run", side_effect=side_effects):
        result = ec.check_repo_scale(Path(td))
    assert result["files"] == 3
    assert result["mb"] == 10


def test_check_repo_scale_zero_when_git_fails() -> None:
    side_effects = _make_git_du_mocks("", 1, "5\t.\n", 0)
    with tempfile.TemporaryDirectory() as td, \
         m.patch("subprocess.run", side_effect=side_effects):
        result = ec.check_repo_scale(Path(td))
    assert result["files"] == 0
    assert result["mb"] == 5


def test_check_repo_scale_zero_mb_when_du_fails() -> None:
    files_out = "x.py\n"
    side_effects = _make_git_du_mocks(files_out, 0, "", 1)
    with tempfile.TemporaryDirectory() as td, \
         m.patch("subprocess.run", side_effect=side_effects):
        result = ec.check_repo_scale(Path(td))
    assert result["files"] == 1
    assert result["mb"] == 0


def test_check_repo_scale_tolerates_timeout() -> None:
    with tempfile.TemporaryDirectory() as td, \
         m.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
        result = ec.check_repo_scale(Path(td))
    assert result == {"files": 0, "mb": 0}


def test_check_repo_scale_tolerates_git_not_found() -> None:
    with tempfile.TemporaryDirectory() as td, \
         m.patch("subprocess.run", side_effect=FileNotFoundError("git")):
        result = ec.check_repo_scale(Path(td))
    assert result == {"files": 0, "mb": 0}

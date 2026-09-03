#!/usr/bin/env python3
"""Tests for check_pi_auth() branches beyond the timeout case in test_edge_cases.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))

from env_check import check_pi_auth

CONFIG = {"provider": "kimi-coding", "model": "k2p6"}


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class TestCheckPiAuthMissing:
    def test_returns_skipped_when_pi_not_installed(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_pi_auth(CONFIG)
        assert result["status"] == "skipped"
        assert result["name"] == "pi-auth"
        assert "not installed" in result["detail"]

    def test_uses_default_config_when_empty(self):
        with patch("env_check.shutil.which", return_value=None):
            result = check_pi_auth({})
        assert result["status"] == "skipped"


class TestCheckPiAuthOk:
    def test_returns_ok_on_rc0(self):
        proc = _proc(0, stdout="pong")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert result["status"] == "ok"
        assert result["detail"] == "session responsive"
        assert result["name"] == "pi-auth"


class TestCheckPiAuthError:
    def test_auth_error_on_unauthorized_in_stderr(self):
        proc = _proc(1, stderr="unauthorized: token expired")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert result["status"] == "auth_error"

    def test_auth_error_on_session_keyword(self):
        proc = _proc(1, stderr="session expired, please reauthenticate")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert result["status"] == "auth_error"

    def test_auth_error_on_login_keyword(self):
        proc = _proc(1, stderr="please login first")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert result["status"] == "auth_error"

    def test_error_on_nonzero_without_auth_keywords(self):
        proc = _proc(1, stderr="internal server error")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert result["status"] == "error"
        assert "rc=1" in result["detail"]

    def test_error_detail_includes_returncode(self):
        proc = _proc(2, stderr="unexpected failure")
        with patch("env_check.shutil.which", return_value="/usr/bin/pi"):
            with patch("env_check.subprocess.run", return_value=proc):
                result = check_pi_auth(CONFIG)
        assert "rc=2" in result["detail"]

"""Extended tests for env_check.py — check_binary() and check_repo_scale() were zero coverage."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load_env_check():
    spec = importlib.util.spec_from_file_location("env_check", SCRIPTS / "env_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


env_check = _load_env_check()


# ---------------------------------------------------------------------------
# check_binary()
# ---------------------------------------------------------------------------

class TestCheckBinary:
    def test_found_binary_returns_ok_with_path(self):
        with mock.patch("shutil.which", return_value="/usr/local/bin/pi"):
            result = env_check.check_binary("pi")
        assert result["status"] == "ok"
        assert result["path"] == "/usr/local/bin/pi"
        assert result["name"] == "pi"

    def test_missing_binary_returns_missing(self):
        with mock.patch("shutil.which", return_value=None):
            result = env_check.check_binary("nonexistent-tool")
        assert result["status"] == "missing"
        assert result["path"] == ""
        assert result["name"] == "nonexistent-tool"

    def test_result_always_has_three_keys(self):
        with mock.patch("shutil.which", return_value=None):
            result = env_check.check_binary("anything")
        assert set(result.keys()) == {"name", "status", "path"}


# ---------------------------------------------------------------------------
# check_repo_scale()
# ---------------------------------------------------------------------------

class TestCheckRepoScale:
    def _make_completed(self, stdout: str, returncode: int = 0):
        cp = mock.MagicMock()
        cp.stdout = stdout
        cp.returncode = returncode
        return cp

    def test_normal_git_and_du_output(self, tmp_path):
        git_result = self._make_completed("a.py\nb.py\nc.py\n")
        du_result = self._make_completed("42\t.\n")
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert result == {"files": 3, "mb": 42}

    def test_git_failure_returns_zero_files(self, tmp_path):
        git_result = self._make_completed("", returncode=128)
        du_result = self._make_completed("10\t.\n")
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert result["files"] == 0
        assert result["mb"] == 10

    def test_du_failure_returns_zero_mb(self, tmp_path):
        git_result = self._make_completed("x.py\n")
        du_result = self._make_completed("", returncode=1)
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert result["files"] == 1
        assert result["mb"] == 0

    def test_du_non_integer_output_returns_zero_mb(self, tmp_path):
        git_result = self._make_completed("a\n")
        du_result = self._make_completed("N/A\t.\n")
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert result["mb"] == 0

    def test_timeout_returns_zeros(self, tmp_path):
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            result = env_check.check_repo_scale(tmp_path)
        assert result == {"files": 0, "mb": 0}

    def test_file_not_found_returns_zeros(self, tmp_path):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = env_check.check_repo_scale(tmp_path)
        assert result == {"files": 0, "mb": 0}

    def test_empty_repo_returns_zero_files(self, tmp_path):
        git_result = self._make_completed("")
        du_result = self._make_completed("5\t.\n")
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert result["files"] == 0

    def test_result_always_has_files_and_mb_keys(self, tmp_path):
        git_result = self._make_completed("a\n")
        du_result = self._make_completed("1\t.\n")
        with mock.patch("subprocess.run", side_effect=[git_result, du_result]):
            result = env_check.check_repo_scale(tmp_path)
        assert set(result.keys()) == {"files", "mb"}

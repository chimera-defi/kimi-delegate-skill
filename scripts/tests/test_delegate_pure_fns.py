"""Unit tests for pure-function helpers in kimi-delegate-skill/scripts/delegate.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from delegate import (  # noqa: E402
    _redact_sensitive,
    classify_error,
    detect_agent_end_error,
    detect_auth_error,
    estimate_tokens,
)


# ── estimate_tokens ───────────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_empty_string_returns_one(self) -> None:
        assert estimate_tokens("") == 1

    def test_single_word(self) -> None:
        assert estimate_tokens("hello") == 1

    def test_ten_words(self) -> None:
        text = " ".join(["word"] * 10)
        assert estimate_tokens(text) == 13  # int(10 * 1.3) = 13

    def test_result_always_at_least_one(self) -> None:
        assert estimate_tokens("   ") == 1  # split() on whitespace = empty list → max(1, 0)

    def test_longer_text_grows_proportionally(self) -> None:
        short = estimate_tokens("a b c")
        longer = estimate_tokens("a b c d e f g h i j")
        assert longer > short


# ── detect_auth_error ─────────────────────────────────────────────────────────

class TestDetectAuthError:
    def test_empty_stderr_returns_false(self) -> None:
        assert not detect_auth_error("")

    def test_none_equivalent_empty_string(self) -> None:
        assert not detect_auth_error("")

    def test_auth_keyword_detected(self) -> None:
        assert detect_auth_error("auth required")

    def test_401_detected(self) -> None:
        assert detect_auth_error("HTTP 401 Unauthorized")

    def test_403_detected(self) -> None:
        assert detect_auth_error("403 Forbidden")

    def test_session_detected(self) -> None:
        assert detect_auth_error("session expired")

    def test_token_detected(self) -> None:
        assert detect_auth_error("invalid token")

    def test_credential_detected(self) -> None:
        assert detect_auth_error("bad credential")

    def test_login_detected(self) -> None:
        assert detect_auth_error("please login")

    def test_siwe_detected(self) -> None:
        assert detect_auth_error("SIWE signature required")

    def test_unrelated_stderr_returns_false(self) -> None:
        assert not detect_auth_error("connection refused: ECONNREFUSED")

    def test_case_insensitive(self) -> None:
        assert detect_auth_error("AUTH REQUIRED")


# ── detect_agent_end_error ────────────────────────────────────────────────────

class TestDetectAgentEndError:
    def test_empty_text_returns_false(self) -> None:
        assert not detect_agent_end_error("")

    def test_detects_finished_without_agent_end(self) -> None:
        assert detect_agent_end_error("finished without an agent_end event")

    def test_detects_partial_phrase(self) -> None:
        assert detect_agent_end_error("Stream ended without an agent_end event")

    def test_unrelated_text_returns_false(self) -> None:
        assert not detect_agent_end_error("Task completed successfully")

    def test_case_insensitive(self) -> None:
        assert detect_agent_end_error("FINISHED WITHOUT AN AGENT_END EVENT")


# ── classify_error ────────────────────────────────────────────────────────────

class TestClassifyError:
    def test_rc_124_is_timeout(self) -> None:
        assert classify_error(124, "", True) == "timeout"

    def test_auth_stderr_is_auth_error(self) -> None:
        assert classify_error(1, "401 unauthorized", True) == "auth_error"

    def test_agent_end_missing(self) -> None:
        assert classify_error(1, "without an agent_end event", True) == "agent_end_missing"

    def test_non_zero_rc_with_clean_stderr_is_provider_error(self) -> None:
        assert classify_error(1, "connection refused", True) == "provider_error"

    def test_schema_invalid_on_rc_zero(self) -> None:
        assert classify_error(0, "", False) == "schema_invalid"

    def test_success_case_is_unknown(self) -> None:
        assert classify_error(0, "", True) == "unknown"

    def test_timeout_takes_precedence_over_auth(self) -> None:
        assert classify_error(124, "401 unauthorized", True) == "timeout"


# ── _redact_sensitive ─────────────────────────────────────────────────────────

class TestRedactSensitive:
    def test_no_sensitive_data_unchanged(self) -> None:
        text = "normal log output"
        assert _redact_sensitive(text) == text

    def test_bearer_token_redacted(self) -> None:
        text = "Authorization: Bearer abcdefghij1234567890xyz"
        result = _redact_sensitive(text)
        assert "abcdefghij1234567890xyz" not in result
        assert "<REDACTED>" in result

    def test_api_key_redacted(self) -> None:
        text = "api_key=supersecretvalue1234567890"
        result = _redact_sensitive(text)
        assert "supersecretvalue1234567890" not in result
        assert "<REDACTED>" in result

    def test_short_token_not_redacted(self) -> None:
        text = "token=short"
        result = _redact_sensitive(text)
        assert result == text

    def test_multiple_secrets_all_redacted(self) -> None:
        text = "Bearer verylongtokenvalueXYZ123456789abc and api_key=anotherlongkeyvalue1234567"
        result = _redact_sensitive(text)
        assert "verylongtokenvalueXYZ123456789abc" not in result
        assert "anotherlongkeyvalue1234567" not in result

    def test_empty_string_unchanged(self) -> None:
        assert _redact_sensitive("") == ""

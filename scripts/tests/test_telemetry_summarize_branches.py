"""Branch coverage for summarize() in kimi_delegate_telemetry.py.

test_telemetry_summary.py covers the basic shape with one event.
This file covers: empty events, non-delegate events ignored, fallback tracking,
auth_error/timeout classification, large-repo detection, provider warnings,
latency and savings math.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kimi_delegate_telemetry import summarize


def _event(**kwargs) -> dict:
    base = {
        "event": "delegate_invocation",
        "status": "ok",
        "task_class": "summarize",
        "model_used": "k2p6",
        "fallback_used": False,
        "fallback_reason": "",
        "latency_ms": None,
        "estimated_tokens_saved": None,
        "parent_context_tokens": None,
        "meta": {},
    }
    base.update(kwargs)
    return base


class TestSummarizeEmptyAndNonDelegate:
    def test_empty_list_returns_zero_calls(self):
        result = summarize([])
        assert result["delegate_calls"] == 0

    def test_empty_list_returns_zero_fallback_rate(self):
        result = summarize([])
        assert result["fallback_rate_pct"] == 0.0

    def test_empty_list_returns_zero_avg_latency(self):
        result = summarize([])
        assert result["avg_latency_ms"] == 0.0

    def test_non_delegate_event_ignored(self):
        events = [{"event": "install", "status": "ok"}]
        result = summarize(events)
        assert result["delegate_calls"] == 0

    def test_mixed_events_only_delegate_counted(self):
        events = [
            {"event": "startup"},
            _event(),
            {"event": "shutdown"},
        ]
        result = summarize(events)
        assert result["delegate_calls"] == 1


class TestSummarizeStatusAndTaskClass:
    def test_status_counted(self):
        events = [_event(status="ok"), _event(status="ok"), _event(status="error")]
        result = summarize(events)
        assert result["status"]["ok"] == 2
        assert result["status"]["error"] == 1

    def test_task_class_counted(self):
        events = [_event(task_class="summarize"), _event(task_class="implement")]
        result = summarize(events)
        assert result["task_classes"]["summarize"] == 1
        assert result["task_classes"]["implement"] == 1

    def test_model_counted(self):
        events = [_event(model_used="k2p6"), _event(model_used="k2p6"), _event(model_used="kimi-k2")]
        result = summarize(events)
        assert result["models"]["k2p6"] == 2
        assert result["models"]["kimi-k2"] == 1


class TestSummarizeFallback:
    def test_no_fallback_gives_zero_rate(self):
        events = [_event(fallback_used=False)]
        result = summarize(events)
        assert result["fallback_rate_pct"] == 0.0

    def test_fallback_used_increments_rate(self):
        events = [_event(fallback_used=True, fallback_reason="timeout"), _event(fallback_used=False)]
        result = summarize(events)
        assert result["fallback_rate_pct"] == 50.0

    def test_fallback_reason_counted(self):
        events = [
            _event(fallback_used=True, fallback_reason="timeout"),
            _event(fallback_used=True, fallback_reason="timeout"),
            _event(fallback_used=True, fallback_reason="auth_error"),
        ]
        result = summarize(events)
        assert result["fallback_reasons"]["timeout"] == 2
        assert result["fallback_reasons"]["auth_error"] == 1

    def test_auth_error_counter_incremented(self):
        events = [_event(fallback_used=True, fallback_reason="auth_error")]
        result = summarize(events)
        assert result["auth_errors"] == 1

    def test_auth_error_counter_not_incremented_for_timeout(self):
        events = [_event(fallback_used=True, fallback_reason="timeout")]
        result = summarize(events)
        assert result["auth_errors"] == 0


class TestSummarizeTimeouts:
    def test_timeout_counter_incremented(self):
        events = [_event(fallback_used=True, fallback_reason="timeout")]
        result = summarize(events)
        assert result["timeouts"] == 1

    def test_large_repo_by_files_threshold(self):
        ev = _event(fallback_used=True, fallback_reason="timeout",
                    meta={"repo_scale": {"files": 10000, "mb": 0}})
        result = summarize([ev])
        assert result["timeouts_in_large_repos"] == 1

    def test_large_repo_by_mb_threshold(self):
        ev = _event(fallback_used=True, fallback_reason="timeout",
                    meta={"repo_scale": {"files": 0, "mb": 500}})
        result = summarize([ev])
        assert result["timeouts_in_large_repos"] == 1

    def test_small_repo_timeout_not_counted_as_large(self):
        ev = _event(fallback_used=True, fallback_reason="timeout",
                    meta={"repo_scale": {"files": 100, "mb": 10}})
        result = summarize([ev])
        assert result["timeouts_in_large_repos"] == 0

    def test_non_timeout_large_repo_not_counted(self):
        ev = _event(fallback_used=True, fallback_reason="auth_error",
                    meta={"repo_scale": {"files": 50000, "mb": 1000}})
        result = summarize([ev])
        assert result["timeouts_in_large_repos"] == 0


class TestSummarizeRepoScaleDistribution:
    def test_normal_repo_classified(self):
        ev = _event(meta={"repo_scale": {"files": 500, "mb": 50}})
        result = summarize([ev])
        assert result["repo_scale_distribution"].get("normal") == 1

    def test_large_repo_classified(self):
        ev = _event(meta={"repo_scale": {"files": 15000, "mb": 0}})
        result = summarize([ev])
        assert result["repo_scale_distribution"].get("large") == 1

    def test_xlarge_repo_classified(self):
        ev = _event(meta={"repo_scale": {"files": 60000, "mb": 0}})
        result = summarize([ev])
        assert result["repo_scale_distribution"].get("xlarge") == 1

    def test_no_repo_scale_classified_as_unknown(self):
        ev = _event(meta={})
        result = summarize([ev])
        assert result["repo_scale_distribution"].get("unknown") == 1


class TestSummarizeProviderWarnings:
    def test_provider_warnings_aggregated(self):
        ev = _event(meta={"provider_warnings": ["agent_end_missing", "slow_response"]})
        result = summarize([ev])
        assert result["provider_warnings"]["agent_end_missing"] == 1
        assert result["provider_warnings"]["slow_response"] == 1

    def test_provider_warnings_across_events(self):
        ev1 = _event(meta={"provider_warnings": ["agent_end_missing"]})
        ev2 = _event(meta={"provider_warnings": ["agent_end_missing", "timeout_near"]})
        result = summarize([ev1, ev2])
        assert result["provider_warnings"]["agent_end_missing"] == 2
        assert result["provider_warnings"]["timeout_near"] == 1

    def test_no_warnings_gives_empty_dict(self):
        result = summarize([_event(meta={})])
        assert result["provider_warnings"] == {}


class TestSummarizeLatencyAndSavings:
    def test_avg_latency_computed(self):
        ev1 = _event(latency_ms=100)
        ev2 = _event(latency_ms=200)
        result = summarize([ev1, ev2])
        assert result["avg_latency_ms"] == 150.0

    def test_none_latency_excluded_from_average(self):
        ev1 = _event(latency_ms=100)
        ev2 = _event(latency_ms=None)
        result = summarize([ev1, ev2])
        assert result["avg_latency_ms"] == 100.0

    def test_negative_latency_excluded(self):
        ev1 = _event(latency_ms=200)
        ev2 = _event(latency_ms=-10)
        result = summarize([ev1, ev2])
        assert result["avg_latency_ms"] == 200.0

    def test_tokens_saved_summed(self):
        ev1 = _event(estimated_tokens_saved=100)
        ev2 = _event(estimated_tokens_saved=50)
        result = summarize([ev1, ev2])
        assert result["estimated_tokens_saved"] == 150

    def test_savings_pct_computed(self):
        ev = _event(estimated_tokens_saved=100, parent_context_tokens=200)
        result = summarize([ev])
        assert result["estimated_savings_pct"] == 50.0

    def test_savings_pct_zero_when_no_parent_tokens(self):
        ev = _event(estimated_tokens_saved=100, parent_context_tokens=0)
        result = summarize([ev])
        assert result["estimated_savings_pct"] == 0.0

#!/usr/bin/env python3
"""Tests for kimi_delegate_telemetry.py pure summarization logic."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kimi_delegate_telemetry import summarize, load_events, record_event  # noqa: E402


def _make_invocation(
    *,
    status: str = "ok",
    task_class: str = "research",
    model_used: str = "kimi-k2",
    latency_ms: int = 1000,
    fallback_used: bool = False,
    fallback_reason: str = "",
    estimated_tokens_saved: int = 0,
    parent_context_tokens: int = 0,
) -> dict:
    ev: dict = {
        "event": "delegate_invocation",
        "status": status,
        "task_class": task_class,
        "model_used": model_used,
        "latency_ms": latency_ms,
        "estimated_tokens_saved": estimated_tokens_saved,
        "parent_context_tokens": parent_context_tokens,
    }
    if fallback_used:
        ev["fallback_used"] = True
        ev["fallback_reason"] = fallback_reason
    return ev


# ---------------------------------------------------------------------------
# summarize - basic call counting
# ---------------------------------------------------------------------------


def test_summarize_empty_events_returns_zero_calls() -> None:
    result = summarize([])
    assert result["delegate_calls"] == 0
    assert result["fallback_rate_pct"] == 0.0


def test_summarize_counts_only_delegate_invocation_events() -> None:
    events = [
        _make_invocation(),
        {"event": "other_event", "status": "ok"},
        _make_invocation(),
    ]
    result = summarize(events)
    assert result["delegate_calls"] == 2


def test_summarize_groups_by_status() -> None:
    events = [
        _make_invocation(status="ok"),
        _make_invocation(status="ok"),
        _make_invocation(status="error"),
    ]
    result = summarize(events)
    assert result["status"]["ok"] == 2
    assert result["status"]["error"] == 1


def test_summarize_groups_by_task_class() -> None:
    events = [
        _make_invocation(task_class="research"),
        _make_invocation(task_class="implement"),
        _make_invocation(task_class="research"),
    ]
    result = summarize(events)
    assert result["task_classes"]["research"] == 2
    assert result["task_classes"]["implement"] == 1


def test_summarize_groups_by_model() -> None:
    events = [
        _make_invocation(model_used="kimi-k2"),
        _make_invocation(model_used="claude-3"),
        _make_invocation(model_used="kimi-k2"),
    ]
    result = summarize(events)
    assert result["models"]["kimi-k2"] == 2
    assert result["models"]["claude-3"] == 1


# ---------------------------------------------------------------------------
# summarize - fallback rate
# ---------------------------------------------------------------------------


def test_summarize_calculates_fallback_rate() -> None:
    events = [
        _make_invocation(),
        _make_invocation(),
        _make_invocation(fallback_used=True, fallback_reason="timeout"),
    ]
    result = summarize(events)
    assert result["delegate_calls"] == 3
    assert abs(result["fallback_rate_pct"] - 33.33) < 0.1
    assert result["timeouts"] == 1


def test_summarize_fallback_rate_zero_when_none() -> None:
    events = [_make_invocation(), _make_invocation()]
    result = summarize(events)
    assert result["fallback_rate_pct"] == 0.0


# ---------------------------------------------------------------------------
# summarize - latency
# ---------------------------------------------------------------------------


def test_summarize_avg_latency_calculation() -> None:
    events = [
        _make_invocation(latency_ms=1000),
        _make_invocation(latency_ms=3000),
    ]
    result = summarize(events)
    assert result["avg_latency_ms"] == 2000.0


def test_summarize_avg_latency_zero_when_no_latency_data() -> None:
    events = [{"event": "delegate_invocation", "status": "ok"}]
    result = summarize(events)
    assert result["avg_latency_ms"] == 0.0


# ---------------------------------------------------------------------------
# summarize - token savings
# ---------------------------------------------------------------------------


def test_summarize_calculates_token_savings_pct() -> None:
    events = [
        _make_invocation(estimated_tokens_saved=500, parent_context_tokens=1000),
        _make_invocation(estimated_tokens_saved=200, parent_context_tokens=1000),
    ]
    result = summarize(events)
    assert result["estimated_tokens_saved"] == 700
    assert result["estimated_savings_pct"] == 35.0


def test_summarize_zero_savings_pct_when_no_parent_tokens() -> None:
    events = [_make_invocation(estimated_tokens_saved=500)]
    result = summarize(events)
    assert result["estimated_savings_pct"] == 0.0


# ---------------------------------------------------------------------------
# load_events - basic I/O
# ---------------------------------------------------------------------------


def test_load_events_returns_empty_list_when_no_file(tmp_path: Path) -> None:
    result = load_events(tmp_path)
    assert result == []


def test_load_events_and_record_roundtrip(tmp_path: Path) -> None:
    record_event(tmp_path, {"event": "delegate_invocation", "status": "ok"})
    record_event(tmp_path, {"event": "delegate_invocation", "status": "error"})
    events = load_events(tmp_path)
    assert len(events) == 2
    statuses = {e["status"] for e in events}
    assert statuses == {"ok", "error"}

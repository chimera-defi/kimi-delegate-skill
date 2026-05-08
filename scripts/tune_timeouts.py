#!/usr/bin/env python3
"""Analyze telemetry events to suggest optimal timeout threshold tuning."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def repo_root_from_script() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path(__file__).resolve().parents[3]


def events_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "kimi-delegate" / "events.jsonl"


def load_events(repo_root: Path, days: int | None = None) -> list[dict[str, Any]]:
    path = events_path(repo_root)
    if not path.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                raw_ts = event.get("timestamp")
                if isinstance(raw_ts, str):
                    try:
                        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except ValueError:
                        ts = None
                    if ts is not None and ts < cutoff:
                        continue
            events.append(event)
    return events


def analyze(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze timeout patterns and suggest threshold tuning."""
    by_scale: dict[str, list[dict[str, Any]]] = defaultdict(list)
    timeouts_by_scale: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for ev in events:
        if ev.get("event") != "delegate_invocation":
            continue
        meta = ev.get("meta", {}) or {}
        repo_scale = meta.get("repo_scale") if isinstance(meta, dict) else {}
        if isinstance(repo_scale, dict):
            files = int(repo_scale.get("files", 0))
            mb = int(repo_scale.get("mb", 0))
            if files >= 50000 or mb >= 1000:
                label = "xlarge"
            elif files >= 10000 or mb >= 500:
                label = "large"
            else:
                label = "normal"
        else:
            label = "unknown"

        by_scale[label].append(ev)
        if ev.get("fallback_reason") == "timeout" or str(ev.get("status", "")) == "error":
            latency = ev.get("latency_ms")
            if isinstance(latency, (int, float)) and float(latency) >= 0:
                timeouts_by_scale[label].append(ev)

    recommendations: list[dict[str, Any]] = []

    for scale in ("normal", "large", "xlarge", "unknown"):
        total = len(by_scale[scale])
        timeouts = len(timeouts_by_scale[scale])
        if total == 0:
            continue

        timeout_pct = round((timeouts * 100.0 / total), 2)
        avg_latency = 0.0
        max_latency = 0.0
        if timeouts > 0:
            latencies = [float(e.get("latency_ms", 0)) for e in timeouts_by_scale[scale]]
            avg_latency = round(sum(latencies) / len(latencies), 2)
            max_latency = round(max(latencies), 2)

        # Heuristic: if timeout rate > 15%, suggest increasing multiplier
        suggested_multiplier = None
        if timeout_pct > 15:
            if scale == "normal":
                suggested_multiplier = 1.5
            elif scale == "large":
                suggested_multiplier = 2.5
            elif scale == "xlarge":
                suggested_multiplier = 4.0
        elif timeout_pct > 5:
            # Moderate timeout rate — slight bump
            if scale == "normal":
                suggested_multiplier = 1.2
            elif scale == "large":
                suggested_multiplier = 2.2
            elif scale == "xlarge":
                suggested_multiplier = 3.5

        recommendations.append({
            "scale": scale,
            "total_calls": total,
            "timeouts": timeouts,
            "timeout_rate_pct": timeout_pct,
            "avg_timeout_latency_ms": avg_latency,
            "max_timeout_latency_ms": max_latency,
            "suggested_multiplier": suggested_multiplier,
            "action": (
                "increase"
                if suggested_multiplier and suggested_multiplier > 1.0
                else "keep"
            ),
        })

    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "recommendations": recommendations,
        "current_config": {
            "large_multiplier": 2.0,
            "xlarge_multiplier": 3.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()

    root = args.repo_root or repo_root_from_script()
    events = load_events(root, days=args.days)
    result = analyze(events)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

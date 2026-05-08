#!/usr/bin/env python3
"""Generate an HTML telemetry dashboard from kimi-delegate events."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
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


def load_dashboard_template() -> str:
    skill_root = Path(__file__).resolve().parents[1]
    tpl = skill_root / "telemetry" / "dashboard.html"
    if not tpl.exists():
        raise FileNotFoundError(f"dashboard template not found: {tpl}")
    return tpl.read_text(encoding="utf-8")


def render_badge(value: float, thresholds: list[tuple[float, str]]) -> str:
    """Return CSS class based on thresholds."""
    for threshold, cls in thresholds:
        if value >= threshold:
            return cls
    return "ok"


def render_table_rows(data: dict[str, Any], total: int | None = None) -> str:
    rows = []
    for key, val in sorted(data.items(), key=lambda x: x[1], reverse=True):
        pct = f"{round((val * 100.0 / total), 1)}%" if total else ""
        rows.append(f"<tr><td>{key}</td><td>{val}</td><td>{pct}</td></tr>")
    if not rows:
        rows.append("<tr><td colspan='3'>No data</td></tr>")
    return "\n".join(rows)


def render_simple_rows(data: dict[str, Any]) -> str:
    rows = []
    for key, val in sorted(data.items(), key=lambda x: x[1], reverse=True):
        rows.append(f"<tr><td>{key}</td><td>{val}</td></tr>")
    if not rows:
        rows.append("<tr><td colspan='2'>No data</td></tr>")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--output", "-o", default="")
    args = parser.parse_args()

    root = repo_root_from_script()
    skill_root = Path(__file__).resolve().parents[1]

    # Import telemetry module to reuse load_events + summarize
    sys_path_hack = str(skill_root / "scripts")
    import sys
    sys.path.insert(0, sys_path_hack)
    from kimi_delegate_telemetry import load_events, summarize  # type: ignore

    events = load_events(root, days=args.days)
    summary = summarize(events)

    template = load_dashboard_template()

    # Determine CSS classes
    calls_class = "ok" if summary.get("delegate_calls", 0) > 0 else "warn"
    fallback_class = render_badge(
        summary.get("fallback_rate_pct", 0.0),
        [(15, "err"), (5, "warn")],
    )
    # We need bypass rate from usage audit, not telemetry alone
    bypass_rate = 0.0  # will be populated if usage data available
    bypass_class = "ok"
    auth_class = render_badge(
        summary.get("auth_errors", 0),
        [(3, "err"), (1, "warn")],
    )

    # Try to load usage audit for bypass rate
    usage_files = list((root / "artifacts" / "kimi-delegate").glob("workspace-usage-*-*.json"))
    if usage_files:
        latest = max(usage_files, key=lambda p: p.stat().st_mtime)
        try:
            usage = json.loads(latest.read_text(encoding="utf-8"))
            bypass_rate = usage.get("overall", {}).get("bypass_rate_pct", 0.0)
        except Exception:
            pass
    bypass_class = render_badge(bypass_rate, [(50, "err"), (20, "warn")])

    # Render rows
    status_rows = render_table_rows(
        summary.get("status", {}), summary.get("delegate_calls", 0)
    )
    fallback_rows = render_table_rows(
        summary.get("fallback_reasons", {}), summary.get("delegate_calls", 0)
    )
    error_rows = render_simple_rows(summary.get("error_categories", {}))
    scale_rows = render_simple_rows(summary.get("repo_scale_distribution", {}))

    # Substitute
    html = (
        template
        .replace("{{generated_at}}", summary.get("generated_at", "unknown"))
        .replace("{{days}}", str(args.days))
        .replace("{{repo_count}}", str(root.name))
        .replace("{{delegate_calls}}", str(summary.get("delegate_calls", 0)))
        .replace("{{calls_class}}", calls_class)
        .replace("{{fallback_rate_pct}}", str(summary.get("fallback_rate_pct", 0.0)))
        .replace("{{fallback_class}}", fallback_class)
        .replace("{{bypass_rate_pct}}", str(bypass_rate))
        .replace("{{bypass_class}}", bypass_class)
        .replace("{{avg_latency_ms}}", str(summary.get("avg_latency_ms", 0.0)))
        .replace("{{estimated_tokens_saved}}", str(summary.get("estimated_tokens_saved", 0)))
        .replace("{{estimated_savings_pct}}", str(summary.get("estimated_savings_pct", 0.0)))
        .replace("{{auth_errors}}", str(summary.get("auth_errors", 0)))
        .replace("{{auth_class}}", auth_class)
        .replace("{{status_rows}}", status_rows)
        .replace("{{fallback_rows}}", fallback_rows)
        .replace("{{error_rows}}", error_rows)
        .replace("{{scale_rows}}", scale_rows)
    )

    out_path = Path(args.output) if args.output else root / "artifacts" / "kimi-delegate" / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

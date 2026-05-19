#!/usr/bin/env python3
"""Print a session-start nudge if recent Kimi bypass rate is high."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_usage_audit(workspace_root: Path, days: int = 7) -> dict[str, Any] | None:
    """Find the most recent usage audit report."""
    audit_dir = workspace_root / "kimi-delegate-skill" / "artifacts" / "kimi-delegate"
    if not audit_dir.exists():
        return None

    pattern = f"workspace-usage-{days}d-*.json"
    files = sorted(audit_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        # Fallback: any workspace-usage file
        files = sorted(audit_dir.glob("workspace-usage-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_bypass_report(workspace_root: Path, days: int = 7) -> dict[str, Any] | None:
    audit_dir = workspace_root / "kimi-delegate-skill" / "artifacts" / "kimi-delegate"
    if not audit_dir.exists():
        return None

    pattern = f"workspace-bypass-{days}d-*.json"
    files = sorted(audit_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        files = sorted(audit_dir.glob("workspace-bypass-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def nudge(workspace_root: Path, days: int, threshold: float) -> str:
    usage = load_usage_audit(workspace_root, days)
    bypass = load_bypass_report(workspace_root, days)

    if usage is None and bypass is None:
        return ""

    lines: list[str] = []
    rate = 0.0

    if usage:
        overall = usage.get("overall", {})
        rate = overall.get("bypass_rate_pct", 0.0)
        total_raw = overall.get("raw_kimi_cmd_count", 0)
        total_delegate = overall.get("delegate_cmd_count", 0)
        if total_raw + total_delegate > 0:
            lines.append(
                f"📊 Last {days}d: {total_delegate} wrapper calls, {total_raw} raw Kimi calls, "
                f"bypass rate {rate}% (target <{threshold}%)"
            )

    if bypass and bypass.get("incidents"):
        top_repo = max(
            bypass.get("bypasses_by_repo", {}).items(),
            key=lambda x: x[1],
            default=("", 0),
        )
        if top_repo[1] > 0:
            lines.append(f"🏴‍☠️  Top bypasser: {top_repo[0]} ({top_repo[1]} raw calls)")

    if rate > threshold:
        lines.append("")
        lines.append("⚠️  High bypass rate detected. Route Kimi calls through the skill wrapper:")
        lines.append("   kd --task \"...\"                    # one-liner")
        lines.append("   kd-i                                 # interactive builder")
        lines.append("   ./skills/kimi-delegate/scripts/delegate.py --task \"...\"")
        lines.append("")
        lines.append("   Direct pi --provider kimi-coding calls bypass envelopes, timeouts,")
        lines.append("   fallback, auth detection, and telemetry. Use the wrapper.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--threshold", type=float, default=20.0)
    parser.add_argument("--quiet", action="store_true", help="Only print if threshold exceeded")
    args = parser.parse_args()

    text = nudge(Path(args.workspace_root).resolve(), args.days, args.threshold)
    if text:
        print(text)
        return 0 if (float(text.split("bypass rate ")[1].split("%")[0]) if "bypass rate" in text else 0) <= args.threshold else 1
    if not args.quiet:
        print("✅ No recent bypass data. Good job using the skill wrapper!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

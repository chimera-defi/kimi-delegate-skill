#!/usr/bin/env python3
"""CI gate: fail if Kimi bypass rate exceeds threshold."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_usage_audit(workspace_root: Path, days: int) -> dict[str, Any] | None:
    audit_dir = workspace_root / "kimi-delegate-skill" / "artifacts" / "kimi-delegate"
    if not audit_dir.exists():
        return None
    pattern = f"workspace-usage-{days}d-*.json"
    files = sorted(audit_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        files = sorted(audit_dir.glob("workspace-usage-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def gate(workspace_root: Path, days: int, threshold: float) -> int:
    usage = load_usage_audit(workspace_root, days)
    if usage is None:
        print("kimi-delegate gate: no usage audit data found. Run workspace-sync first.")
        return 0  # be lenient if no data

    overall = usage.get("overall", {})
    bypass_rate = overall.get("bypass_rate_pct", 0.0)
    raw = overall.get("raw_kimi_cmd_count", 0)
    wrapped = overall.get("delegate_cmd_count", 0)

    print(f"kimi-delegate gate: bypass_rate={bypass_rate}% (threshold={threshold}%)")
    print(f"  raw={raw} wrapped={wrapped}")

    # Per-repo check
    failed_repos: list[str] = []
    for row in usage.get("repos", []):
        repo_rate = row.get("bypass_rate_pct", 0.0)
        if repo_rate > threshold:
            failed_repos.append(f"  {row['repo']}: {repo_rate}%")

    if failed_repos:
        print(f"\n❌ FAIL: {len(failed_repos)} repo(s) exceed bypass threshold:")
        for r in failed_repos:
            print(r)
        print(f"\nFix: route Kimi calls through the skill wrapper:")
        print(f"  kd --task \"...\"")
        return 1

    if bypass_rate > threshold:
        print(f"\n❌ FAIL: workspace-wide bypass rate {bypass_rate}% > {threshold}%")
        print(f"\nFix: route Kimi calls through the skill wrapper:")
        print(f"  kd --task \"...\"")
        return 1

    print("\n✅ PASS: bypass rate within threshold.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--threshold", type=float, default=20.0)
    args = parser.parse_args()
    return gate(Path(args.workspace_root).resolve(), args.days, args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Detect raw Kimi subagent calls that bypass the kimi-delegate skill wrapper."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from repo_scan import iter_workspace_repos, repo_label
except ModuleNotFoundError:  # pragma: no cover
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from repo_scan import iter_workspace_repos, repo_label


# Same patterns as audit_workspace_usage.py
DELEGATE_CMD_RE = re.compile(
    r"(?:^|\s)(?:\./)?(?:skills/kimi-delegate/scripts/delegate\.py|kimi-delegate)(?:\s|$)",
    re.IGNORECASE,
)
KIMI_SUBAGENT_RE = re.compile(r"\bpi-kimi-subagent\b|\bpi\s+--provider\s+kimi-coding\b", re.IGNORECASE)


def repo_slug(repo_path: Path) -> str:
    raw = repo_path.resolve().as_posix().lstrip("/")
    return "-" + raw.replace("/", "-").replace(".", "-")


def iter_session_files(repo: Path, cutoff_ts: float) -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []

    files: list[Path] = []
    slug = repo_slug(repo)
    for project_dir in base.glob(f"{slug}*"):
        for session_file in project_dir.glob("*.jsonl"):
            try:
                if session_file.stat().st_mtime < cutoff_ts:
                    continue
            except OSError:
                continue
            files.append(session_file)

            subagent_dir = session_file.with_suffix("") / "subagents"
            if subagent_dir.exists():
                for sf in subagent_dir.glob("*.jsonl"):
                    try:
                        if sf.stat().st_mtime < cutoff_ts:
                            continue
                    except OSError:
                        continue
                    files.append(sf)
    return files


def iter_codex_session_files(cutoff_ts: float) -> list[Path]:
    base = Path.home() / ".codex" / "sessions"
    if not base.exists():
        return []
    files: list[Path] = []
    for path in base.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff_ts:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def parse_bypasses_claude(path: Path) -> list[dict[str, Any]]:
    """Extract raw Kimi calls from Claude session files that did NOT use the wrapper."""
    bypasses: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return bypasses

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        message = event.get("message", {})
        content = message.get("content")
        if not isinstance(content, list):
            continue

        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_use" or item.get("name") != "Bash":
                continue
            command = item.get("input", {}).get("command", "")
            if not isinstance(command, str):
                continue
            # Raw Kimi call but NOT through the wrapper
            if KIMI_SUBAGENT_RE.search(command) and not DELEGATE_CMD_RE.search(command):
                ts = event.get("timestamp", "")
                bypasses.append({
                    "source": "claude",
                    "session_file": str(path),
                    "command": command,
                    "timestamp": ts,
                })
    return bypasses


def extract_cmd_from_exec_args(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    cmd = payload.get("cmd")
    return cmd if isinstance(cmd, str) else ""


def extract_cmds_from_parallel_args(raw: Any) -> list[str]:
    if not isinstance(raw, str):
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    tool_uses = payload.get("tool_uses")
    if not isinstance(tool_uses, list):
        return []
    commands: list[str] = []
    for tool in tool_uses:
        if not isinstance(tool, dict):
            continue
        if tool.get("recipient_name") != "functions.exec_command":
            continue
        params = tool.get("parameters")
        if not isinstance(params, dict):
            continue
        cmd = params.get("cmd")
        if isinstance(cmd, str):
            commands.append(cmd)
    return commands


def parse_bypasses_codex(path: Path) -> list[dict[str, Any]]:
    """Extract raw Kimi calls from Codex session files that did NOT use the wrapper."""
    bypasses: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return bypasses

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            payload = event.get("payload")
            if event_type != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("type") != "function_call":
                continue

            name = payload.get("name")
            arguments = payload.get("arguments")
            commands: list[str] = []
            if name == "exec_command":
                cmd = extract_cmd_from_exec_args(arguments)
                if cmd:
                    commands.append(cmd)
            elif name == "parallel":
                commands.extend(extract_cmds_from_parallel_args(arguments))

            for cmd in commands:
                if KIMI_SUBAGENT_RE.search(cmd) and not DELEGATE_CMD_RE.search(cmd):
                    bypasses.append({
                        "source": "codex",
                        "session_file": str(path),
                        "command": cmd,
                        "timestamp": "",
                    })
    return bypasses


def find_repo_for_cwd(cwd: Path, repo_paths: list[Path]) -> Path | None:
    try:
        cwd_resolved = cwd.resolve()
    except OSError:
        return None
    for repo in repo_paths:
        try:
            cwd_resolved.relative_to(repo.resolve())
            return repo
        except ValueError:
            continue
    return None


def detect_bypasses(workspace_root: Path, days: int) -> dict[str, Any]:
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff_dt.timestamp()

    repo_paths = iter_workspace_repos(workspace_root, include_worktrees=True)
    repo_paths_by_specificity = sorted(repo_paths, key=lambda p: len(str(p.resolve())), reverse=True)

    # Map repo -> list of bypass incidents
    bypasses_by_repo: dict[str, list[dict[str, Any]]] = {}
    all_bypasses: list[dict[str, Any]] = []

    # Claude sessions
    for repo in repo_paths:
        for session_file in iter_session_files(repo, cutoff_ts):
            hits = parse_bypasses_claude(session_file)
            label = repo_label(repo, workspace_root)
            for hit in hits:
                hit["repo"] = label
                all_bypasses.append(hit)
                bypasses_by_repo.setdefault(label, []).append(hit)

    # Codex sessions
    for session_file in iter_codex_session_files(cutoff_ts):
        hits = parse_bypasses_codex(session_file)
        # Try to attribute to a repo via session_meta cwd
        repo = None
        try:
            with session_file.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        event = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "session_meta":
                        payload = event.get("payload", {})
                        raw_cwd = payload.get("cwd")
                        if isinstance(raw_cwd, str):
                            repo = find_repo_for_cwd(Path(raw_cwd), repo_paths_by_specificity)
                        break
        except OSError:
            pass

        label = repo_label(repo, workspace_root) if repo else "unknown"
        for hit in hits:
            hit["repo"] = label
            all_bypasses.append(hit)
            bypasses_by_repo.setdefault(label, []).append(hit)

    total_raw_kimi = len(all_bypasses)
    total_delegate = 0

    # Count delegate commands for ratio
    for repo in repo_paths:
        for session_file in iter_session_files(repo, cutoff_ts):
            try:
                lines = session_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = event.get("message", {}).get("content", [])
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "tool_use" and item.get("name") == "Bash":
                        cmd = item.get("input", {}).get("command", "")
                        if isinstance(cmd, str) and DELEGATE_CMD_RE.search(cmd):
                            total_delegate += 1

    for session_file in iter_codex_session_files(cutoff_ts):
        hits = parse_bypasses_codex(session_file)
        for hit in hits:
            if DELEGATE_CMD_RE.search(hit["command"]):
                total_delegate += 1

    bypass_rate_pct = round(
        (total_raw_kimi * 100.0 / (total_raw_kimi + total_delegate)), 2
    ) if (total_raw_kimi + total_delegate) else 0.0

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "days": days,
        "total_raw_kimi_calls": total_raw_kimi,
        "total_delegate_calls": total_delegate,
        "bypass_rate_pct": bypass_rate_pct,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {k: len(v) for k, v in bypasses_by_repo.items()},
        "incidents": all_bypasses,
    }


def extract_task_from_raw(command: str) -> str | None:
    """Extract the task/prompt text from a raw pi command for auto-convert."""
    # Pattern: pi --provider kimi-coding --print "task text"
    m = re.search(r'--print\s+["\']([^"\']+)["\']', command)
    if m:
        return m.group(1)
    # Pattern: pi-kimi-subagent "task text"
    m = re.search(r'pi-kimi-subagent\s+["\']([^"\']+)["\']', command)
    if m:
        return m.group(1)
    # Pattern: pi --provider kimi-coding --model k2p6 "task text"
    m = re.search(r'pi\s+(?:--\w+\s+\S+\s+)*["\']([^"\']+)["\']', command)
    if m:
        return m.group(1)
    return None


def nudge_report(report: dict[str, Any]) -> str:
    """Generate a human-readable nudge message from bypass report."""
    total = report["total_raw_kimi_calls"]
    delegate = report["total_delegate_calls"]
    rate = report["bypass_rate_pct"]
    target = report["target_bypass_rate_pct"]

    if total == 0:
        return "✅ No raw Kimi bypasses detected. Good job using the skill wrapper!"

    lines = [
        f"⚠️  Kimi Delegate Bypass Detected",
        f"",
        f"Raw Kimi calls (bypassing wrapper): {total}",
        f"Skill wrapper calls:                {delegate}",
        f"Bypass rate:                        {rate}% (target: <{target}%)",
        f"",
        f"Recent bypasses by repo:",
    ]
    for repo, count in sorted(report["bypasses_by_repo"].items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            lines.append(f"  {repo}: {count} raw call(s)")

    # Auto-convert: show exact kd command for the most recent bypass
    incidents = report.get("incidents", [])
    if incidents:
        latest = incidents[-1]
        task = extract_task_from_raw(latest.get("command", ""))
        if task:
            lines.extend([
                f"",
                f"🔄 Re-run your last task through the wrapper:",
                f"   kd --task \"{task}\"",
            ])

    lines.extend([
        f"",
        f"👉 Route through the skill wrapper instead:",
        f"   ./skills/kimi-delegate/scripts/delegate.py --task \"...\"",
        f"   or: kimi-delegate --task \"...\"",
        f"",
        f"Direct pi --provider kimi-coding calls bypass:",
        f"   - Structured envelopes",
        f"   - Auto-scaling timeouts",
        f"   - Auth error detection",
        f"   - Fallback routing",
        f"   - Telemetry for continuous improvement",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--nudge", action="store_true", help="Print human-readable nudge")
    parser.add_argument("--output", default="")
    parser.add_argument("--watch", action="store_true", help="Watch mode: poll session files continuously")
    parser.add_argument("--watch-interval", type=int, default=30, help="Seconds between polls in watch mode")
    args = parser.parse_args()

    if args.watch:
        import time
        print(f"🔍 Watch mode: polling every {args.watch_interval}s (Ctrl+C to stop)")
        last_bypasses = 0
        try:
            while True:
                report = detect_bypasses(Path(args.workspace_root).resolve(), args.days)
                current = report["total_raw_kimi_calls"]
                if current != last_bypasses:
                    last_bypasses = current
                    print(f"[{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%H:%M:%S')}] bypasses={current} rate={report['bypass_rate_pct']}%")
                    if current > 0:
                        print(nudge_report(report))
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\nWatch stopped.")
            return 0

    report = detect_bypasses(Path(args.workspace_root).resolve(), args.days)

    if args.nudge:
        print(nudge_report(report))
        return 0

    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Measure real kimi-delegate and Kimi subagent usage across workspace repos."""
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


DELEGATE_CMD_RE = re.compile(
    r"(?:^|\s)(?:\.\/)?(?:skills/kimi-delegate/scripts/delegate\.py|kimi-delegate)(?:\s|$)",
    re.IGNORECASE,
)
_INVOKE_PREFIX = r"(?:^(?:[A-Z_]+=\S+\s+)*|(?:&&|\|\||;|\|)\s+|\bsudo\s+)"
KIMI_SUBAGENT_RE = re.compile(
    _INVOKE_PREFIX + r"pi-kimi-subagent\b"
    r"|" + _INVOKE_PREFIX + r"pi\s+--provider\s+kimi-coding\b",
    re.IGNORECASE,
)
MACHINE_PROTOCOL_RE = re.compile(
    r"(?:^|\s)--mode(?:=|\s+)json(?:\s|$)|(?:^|\s)--session(?:=|\s+)\S+",
    re.IGNORECASE,
)


def is_machine_protocol_call(command: str) -> bool:
    """Structured pi runner calls should not count as raw bypass traffic."""
    return bool(MACHINE_PROTOCOL_RE.search(command))


def is_false_positive_command(command: str) -> bool:
    """Ignore literal/search/probe commands that are not real delegation bypasses."""
    stripped = command.lstrip()
    search_prefixes = (
        "rg ",
        "rg -",
        "grep ",
        "grep -",
        "ag ",
        "awk ",
        "sed ",
        "git commit",
        "git add",
        "git log",
        "git show",
        "git diff",
        "python3 -c",
        "python -c",
        "command -v pi",
        "command -v pi-kimi-subagent",
    )
    if stripped.startswith(search_prefixes):
        return True
    if stripped.startswith(("pi-kimi-subagent --help", "pi --provider kimi-coding --help")):
        return True
    return False


def repo_slug(repo_path: Path) -> str:
    raw = repo_path.resolve().as_posix().lstrip("/")
    # Claude project directory naming normalizes both path separators and dots.
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


def parse_command_hits(path: Path) -> dict[str, Any]:
    delegate_count = 0
    kimi_count = 0
    raw_kimi_count = 0

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return {"delegate_count": 0, "kimi_count": 0, "raw_kimi_count": 0}

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
            if is_false_positive_command(command):
                continue
            if is_machine_protocol_call(command):
                continue
            is_delegate = bool(DELEGATE_CMD_RE.search(command))
            is_kimi = bool(KIMI_SUBAGENT_RE.search(command))
            if is_delegate:
                delegate_count += 1
            if is_kimi:
                kimi_count += 1
            if is_kimi and not is_delegate:
                raw_kimi_count += 1

    return {"delegate_count": delegate_count, "kimi_count": kimi_count, "raw_kimi_count": raw_kimi_count}


def load_repo_telemetry(repo: Path, cutoff: datetime) -> dict[str, Any]:
    path = repo / "artifacts" / "kimi-delegate" / "events.jsonl"
    if not path.exists():
        return {
            "events": 0,
            "status": {},
            "fallback_rate_pct": 0.0,
            "provider_warnings": {},
            "agent_end_missing": 0,
        }

    status = Counter()
    provider_warnings = Counter()
    total = 0
    fallback = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "delegate_invocation":
            continue
        raw_ts = event.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts is not None and ts < cutoff:
                continue
        total += 1
        status[str(event.get("status", "unknown"))] += 1
        if event.get("fallback_used"):
            fallback += 1
        meta = event.get("meta")
        if isinstance(meta, dict):
            warnings = meta.get("provider_warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    provider_warnings[str(warning)] += 1

    return {
        "events": total,
        "status": dict(status),
        "fallback_rate_pct": round((fallback * 100.0 / total), 2) if total else 0.0,
        "provider_warnings": dict(provider_warnings),
        "agent_end_missing": int(provider_warnings.get("agent_end_missing", 0)),
    }


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


def parse_codex_session_hits(path: Path) -> dict[str, Any]:
    cwd = ""
    delegate_count = 0
    kimi_count = 0
    raw_kimi_count = 0

    try:
        handle = path.open("r", encoding="utf-8", errors="ignore")
    except OSError:
        return {"cwd": cwd, "delegate_count": 0, "kimi_count": 0, "raw_kimi_count": 0}

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
            if event_type == "session_meta" and isinstance(payload, dict):
                raw_cwd = payload.get("cwd")
                if isinstance(raw_cwd, str):
                    cwd = raw_cwd
                continue

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
                if is_false_positive_command(cmd):
                    continue
                if is_machine_protocol_call(cmd):
                    continue
                is_delegate = bool(DELEGATE_CMD_RE.search(cmd))
                is_kimi = bool(KIMI_SUBAGENT_RE.search(cmd))
                if is_delegate:
                    delegate_count += 1
                if is_kimi:
                    kimi_count += 1
                if is_kimi and not is_delegate:
                    raw_kimi_count += 1

    return {"cwd": cwd, "delegate_count": delegate_count, "kimi_count": kimi_count, "raw_kimi_count": raw_kimi_count}


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


def audit_usage(workspace_root: Path, days: int) -> dict[str, Any]:
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff_dt.timestamp()

    repo_paths = iter_workspace_repos(workspace_root, include_worktrees=True)
    repo_paths_by_specificity = sorted(repo_paths, key=lambda p: len(str(p.resolve())), reverse=True)

    repo_stats: dict[Path, dict[str, int]] = {
        repo.resolve(): {
            "claude_session_count": 0,
            "claude_sessions_with_delegate": 0,
            "claude_sessions_with_kimi": 0,
            "claude_delegate_cmd_count": 0,
            "claude_kimi_cmd_count": 0,
            "claude_raw_kimi_cmd_count": 0,
            "codex_session_count": 0,
            "codex_sessions_with_delegate": 0,
            "codex_sessions_with_kimi": 0,
            "codex_delegate_cmd_count": 0,
            "codex_kimi_cmd_count": 0,
            "codex_raw_kimi_cmd_count": 0,
        }
        for repo in repo_paths
    }

    rows: list[dict[str, Any]] = []
    total_sessions = 0
    total_delegate_sessions = 0
    total_delegate_cmds = 0
    total_kimi_sessions = 0
    total_kimi_cmds = 0
    total_telemetry_events = 0
    repos_with_telemetry = 0
    repos_with_telemetry_success = 0
    total_telemetry_provider_warnings = Counter()
    total_agent_end_missing = 0
    repos_with_agent_end_warnings = 0
    total_raw_kimi_cmds = 0
    repos_with_delegate_activity = 0

    for repo in repo_paths:
        files = iter_session_files(repo, cutoff_ts)
        stats = repo_stats[repo.resolve()]
        stats["claude_session_count"] = len(files)
        for sf in files:
            hits = parse_command_hits(sf)
            d_count = int(hits["delegate_count"])
            k_count = int(hits["kimi_count"])
            r_count = int(hits.get("raw_kimi_count", 0))
            stats["claude_delegate_cmd_count"] += d_count
            stats["claude_kimi_cmd_count"] += k_count
            stats["claude_raw_kimi_cmd_count"] += r_count
            if d_count > 0:
                stats["claude_sessions_with_delegate"] += 1
            if k_count > 0:
                stats["claude_sessions_with_kimi"] += 1

    for session_file in iter_codex_session_files(cutoff_ts):
        hits = parse_codex_session_hits(session_file)
        cwd = hits.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            continue
        repo = find_repo_for_cwd(Path(cwd), repo_paths_by_specificity)
        if repo is None:
            continue

        stats = repo_stats[repo.resolve()]
        stats["codex_session_count"] += 1
        d_count = int(hits["delegate_count"])
        k_count = int(hits["kimi_count"])
        r_count = int(hits.get("raw_kimi_count", 0))
        stats["codex_delegate_cmd_count"] += d_count
        stats["codex_kimi_cmd_count"] += k_count
        stats["codex_raw_kimi_cmd_count"] += r_count
        if d_count > 0:
            stats["codex_sessions_with_delegate"] += 1
        if k_count > 0:
            stats["codex_sessions_with_kimi"] += 1

    for repo in repo_paths:
        stats = repo_stats[repo.resolve()]
        session_count = stats["claude_session_count"] + stats["codex_session_count"]
        sessions_with_delegate = stats["claude_sessions_with_delegate"] + stats["codex_sessions_with_delegate"]
        sessions_with_kimi = stats["claude_sessions_with_kimi"] + stats["codex_sessions_with_kimi"]
        delegate_cmd_count = stats["claude_delegate_cmd_count"] + stats["codex_delegate_cmd_count"]
        kimi_cmd_count = stats["claude_kimi_cmd_count"] + stats["codex_kimi_cmd_count"]
        raw_kimi_cmd_count = stats["claude_raw_kimi_cmd_count"] + stats["codex_raw_kimi_cmd_count"]

        telemetry = load_repo_telemetry(repo, cutoff_dt)
        telemetry_events = int(telemetry["events"])
        telemetry_ok = int(telemetry["status"].get("ok", 0))
        telemetry_warnings = telemetry.get("provider_warnings", {})
        telemetry_agent_end_missing = int(telemetry.get("agent_end_missing", 0))
        if isinstance(telemetry_warnings, dict):
            for warning, count in telemetry_warnings.items():
                total_telemetry_provider_warnings[str(warning)] += int(count)

        total_sessions += session_count
        total_delegate_sessions += sessions_with_delegate
        total_delegate_cmds += delegate_cmd_count
        total_kimi_sessions += sessions_with_kimi
        total_kimi_cmds += kimi_cmd_count
        total_raw_kimi_cmds += raw_kimi_cmd_count
        total_telemetry_events += telemetry_events
        total_agent_end_missing += telemetry_agent_end_missing
        if telemetry_events > 0:
            repos_with_telemetry += 1
        if telemetry_ok > 0:
            repos_with_telemetry_success += 1
        if telemetry_agent_end_missing > 0:
            repos_with_agent_end_warnings += 1
        if delegate_cmd_count > 0 or telemetry_events > 0:
            repos_with_delegate_activity += 1

        rows.append(
            {
                "repo": repo_label(repo, workspace_root),
                "session_count": session_count,
                "sessions_with_delegate": sessions_with_delegate,
                "delegate_cmd_count": delegate_cmd_count,
                "sessions_with_kimi_subagent": sessions_with_kimi,
                "kimi_subagent_cmd_count": kimi_cmd_count,
                "raw_kimi_cmd_count": raw_kimi_cmd_count,
                "bypass_rate_pct": round((raw_kimi_cmd_count * 100.0 / (raw_kimi_cmd_count + delegate_cmd_count)), 2)
                if (raw_kimi_cmd_count + delegate_cmd_count) > 0
                else 0.0,
                "delegate_session_adoption_pct": round((sessions_with_delegate * 100.0 / session_count), 2)
                if session_count
                else 0.0,
                "kimi_session_adoption_pct": round((sessions_with_kimi * 100.0 / session_count), 2)
                if session_count
                else 0.0,
                "codex_session_count": stats["codex_session_count"],
                "codex_sessions_with_delegate": stats["codex_sessions_with_delegate"],
                "codex_sessions_with_kimi_subagent": stats["codex_sessions_with_kimi"],
                "claude_session_count": stats["claude_session_count"],
                "claude_sessions_with_delegate": stats["claude_sessions_with_delegate"],
                "claude_sessions_with_kimi_subagent": stats["claude_sessions_with_kimi"],
                "delegate_activity_observed": bool(delegate_cmd_count > 0 or telemetry_events > 0),
                "telemetry_events": telemetry["events"],
                "telemetry_status": telemetry["status"],
                "telemetry_fallback_rate_pct": telemetry["fallback_rate_pct"],
                "telemetry_provider_warnings": telemetry.get("provider_warnings", {}),
                "telemetry_agent_end_missing": telemetry_agent_end_missing,
            }
        )

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "days": days,
        "overall": {
            "sessions": total_sessions,
            "sessions_with_delegate": total_delegate_sessions,
            "delegate_cmd_count": total_delegate_cmds,
            "sessions_with_kimi_subagent": total_kimi_sessions,
            "kimi_subagent_cmd_count": total_kimi_cmds,
            "raw_kimi_cmd_count": total_raw_kimi_cmds,
            "bypass_rate_pct": round((total_raw_kimi_cmds * 100.0 / (total_raw_kimi_cmds + total_delegate_cmds)), 2)
            if (total_raw_kimi_cmds + total_delegate_cmds) > 0
            else 0.0,
            "target_bypass_rate_pct": 20.0,
            "delegate_session_adoption_pct": round((total_delegate_sessions * 100.0 / total_sessions), 2)
            if total_sessions
            else 0.0,
            "kimi_session_adoption_pct": round((total_kimi_sessions * 100.0 / total_sessions), 2)
            if total_sessions
            else 0.0,
            "telemetry_events": total_telemetry_events,
            "repos_with_telemetry": repos_with_telemetry,
            "repos_with_telemetry_success": repos_with_telemetry_success,
            "telemetry_provider_warnings": dict(total_telemetry_provider_warnings),
            "telemetry_agent_end_missing": total_agent_end_missing,
            "repos_with_agent_end_warnings": repos_with_agent_end_warnings,
            "repos_with_delegate_activity": repos_with_delegate_activity,
            "delegate_invocations_from_session_logs": total_delegate_cmds,
            "delegate_invocations_from_telemetry": total_telemetry_events,
        },
        "repos": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    payload = audit_usage(Path(args.workspace_root).resolve(), args.days)
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

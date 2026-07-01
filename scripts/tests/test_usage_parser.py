#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("usage_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _usage_script() -> Path:
    extras = Path(os.environ.get(
        "DELEGATE_EXTRAS_DIR",
        str(Path.home() / ".claude" / "skills" / "delegate-skill" / "delegate-extras" / "kimi"),
    ))
    cand = extras / "audit_workspace_usage.py"
    if cand.exists():
        return cand
    return Path(__file__).resolve().parents[2] / "scripts" / "audit_workspace_usage.py"


def test_parse_codex_session_hits_exec_and_parallel(tmp_path: Path) -> None:
    mod = load_module(_usage_script())
    session = tmp_path / "rollout.jsonl"

    lines = [
        {
            "type": "session_meta",
            "payload": {"cwd": "/root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "./skills/kimi-delegate/scripts/delegate.py --task 'summarize logs'"}
                ),
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "parallel",
                "arguments": json.dumps(
                    {
                        "tool_uses": [
                            {
                                "recipient_name": "functions.exec_command",
                                "parameters": {"cmd": "pi --provider kimi-coding --model k2p6 --print ping"},
                            }
                        ]
                    }
                ),
            },
        },
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_codex_session_hits(session)
    assert hits["cwd"].endswith("/token-reduce-skill/.worktrees/main")
    assert hits["delegate_count"] == 1
    assert hits["kimi_count"] == 1


def test_repo_slug_matches_claude_project_dir_format() -> None:
    mod = load_module(_usage_script())
    repo = Path("/root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main")
    assert mod.repo_slug(repo) == "-root--openclaw-workspace-dev-token-reduce-skill--worktrees-main"


def test_parse_codex_session_hits_ignores_machine_protocol_call(tmp_path: Path) -> None:
    mod = load_module(_usage_script())
    session = tmp_path / "rollout-machine.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "pi --tools read,bash --print --mode json --provider kimi-coding --model k2p6 --session abc123 Test"}
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_codex_session_hits(session)
    assert hits["delegate_count"] == 0
    assert hits["kimi_count"] == 0
    assert hits["raw_kimi_count"] == 0


def test_parse_codex_session_hits_ignores_quoted_search_patterns(tmp_path: Path) -> None:
    mod = load_module(_usage_script())
    session = tmp_path / "rollout-search.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "rg -n \"pi --provider kimi-coding|pi-kimi-subagent\" scripts -S"}
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_codex_session_hits(session)
    assert hits["delegate_count"] == 0
    assert hits["kimi_count"] == 0
    assert hits["raw_kimi_count"] == 0


def test_load_repo_telemetry_counts_provider_warnings(tmp_path: Path) -> None:
    mod = load_module(_usage_script())
    repo = tmp_path / "repo"
    events = repo / "artifacts" / "kimi-delegate" / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    payloads = [
        {
            "event": "delegate_invocation",
            "timestamp": now.isoformat(),
            "status": "ok",
            "fallback_used": False,
            "meta": {"provider_warnings": ["agent_end_missing", "agent_end_missing", "other_warning"]},
        },
        {
            "event": "delegate_invocation",
            "timestamp": now.isoformat(),
            "status": "ok",
            "fallback_used": True,
            "meta": {"provider_warnings": ["agent_end_missing"]},
        },
        {
            "event": "delegate_invocation",
            "timestamp": (now - timedelta(days=60)).isoformat(),
            "status": "ok",
            "fallback_used": False,
            "meta": {"provider_warnings": ["agent_end_missing"]},
        },
    ]
    events.write_text("\n".join(json.dumps(p) for p in payloads) + "\n", encoding="utf-8")

    out = mod.load_repo_telemetry(repo, now - timedelta(days=7))
    assert out["events"] == 2
    assert out["fallback_rate_pct"] == 50.0
    assert out["provider_warnings"]["agent_end_missing"] == 3
    assert out["provider_warnings"]["other_warning"] == 1
    assert out["agent_end_missing"] == 3

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("usage_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_parse_codex_session_hits_exec_and_parallel(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "audit_workspace_usage.py")
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
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "audit_workspace_usage.py")
    repo = Path("/root/.openclaw/workspace/dev/token-reduce-skill/.worktrees/main")
    assert mod.repo_slug(repo) == "-root--openclaw-workspace-dev-token-reduce-skill--worktrees-main"

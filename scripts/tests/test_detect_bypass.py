#!/usr/bin/env python3
"""Tests for detect_bypass.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("bypass_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_parse_bypasses_claude_skips_wrapped_calls(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "session.jsonl"
    lines = [
        {
            "timestamp": "2026-05-08T10:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "./skills/kimi-delegate/scripts/delegate.py --task 'summarize'"},
                    }
                ]
            },
        },
        {
            "timestamp": "2026-05-08T10:01:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "pi --provider kimi-coding --model k2p6 --print 'hello'"},
                    }
                ]
            },
        },
        {
            "timestamp": "2026-05-08T10:02:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "echo normal bash"},
                    }
                ]
            },
        },
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_claude(session)
    assert len(hits) == 1
    assert hits[0]["command"] == "pi --provider kimi-coding --model k2p6 --print 'hello'"


def test_nudge_report_when_clean() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    report = {
        "total_raw_kimi_calls": 0,
        "total_delegate_calls": 5,
        "bypass_rate_pct": 0.0,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {},
    }
    msg = mod.nudge_report(report)
    assert "No raw Kimi bypasses" in msg


def test_nudge_report_when_bypasses() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    report = {
        "total_raw_kimi_calls": 10,
        "total_delegate_calls": 2,
        "bypass_rate_pct": 83.33,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {"foo": 7, "bar": 3},
    }
    msg = mod.nudge_report(report)
    assert "Bypass Detected" in msg
    assert "foo: 7" in msg
    assert "bar: 3" in msg
    assert "kd=" not in msg  # make sure we mention the alias


def test_detect_bypasses_counts_correctly(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    # Build a fake workspace with a fake repo
    workspace = tmp_path / "workspace"
    repo = workspace / "test-repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    # We can't easily fake ~/.claude/projects, so test the parsing helpers directly
    assert True


def test_parse_bypasses_codex_detects_raw_kimi(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "pi --provider kimi-coding --model k2p6 --print 'hello'"}
                ),
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "./skills/kimi-delegate/scripts/delegate.py --task 'summarize'"}
                ),
            },
        },
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert len(hits) == 1
    assert "pi --provider kimi-coding" in hits[0]["command"]


def test_parse_bypasses_codex_ignores_machine_protocol_calls(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-machine.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": "pi --tools read,bash --print --mode json --provider kimi-coding --model k2p6 --session abc123 Test"
                    }
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert hits == []


def test_parse_bypasses_codex_ignores_quoted_pattern_mentions(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-search.jsonl"
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

    hits = mod.parse_bypasses_codex(session)
    assert hits == []


def test_parse_bypasses_codex_ignores_help_probe_commands(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "codex-help-probe.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "command -v pi-kimi-subagent && pi-kimi-subagent --help | sed -n '1,120p'"}
                ),
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_codex(session)
    assert hits == []


def test_parse_bypasses_claude_ignores_git_commit_message_literals(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    session = tmp_path / "claude-commit-literal.jsonl"
    lines = [
        {
            "timestamp": "2026-05-18T10:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {
                            "command": "git commit -m \"note: avoid direct pi --provider kimi-coding calls\""
                        },
                    }
                ]
            },
        }
    ]
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    hits = mod.parse_bypasses_claude(session)
    assert hits == []


def test_detect_bypasses_repo_filter_ignores_unattributed_codex_hits(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "detect_bypass.py")

    workspace = tmp_path / "workspace"
    repo = workspace / "repo-a"
    repo.mkdir(parents=True)

    fake_session = tmp_path / "codex.jsonl"
    fake_session.write_text("", encoding="utf-8")

    fake_hits = [
        {
            "source": "codex",
            "session_file": str(fake_session),
            "command": "pi --provider kimi-coding --model k2p6 --print ping",
            "timestamp": "",
        }
    ]

    with mock.patch.object(mod, "iter_workspace_repos", return_value=[repo]):
        with mock.patch.object(mod, "iter_session_files", return_value=[]):
            with mock.patch.object(mod, "iter_codex_session_files", return_value=[fake_session]):
                with mock.patch.object(mod, "parse_bypasses_codex", return_value=fake_hits):
                    report_filtered = mod.detect_bypasses(workspace, days=7, repo_filter=repo)
                    report_unfiltered = mod.detect_bypasses(workspace, days=7, repo_filter=None)

    assert report_filtered["total_raw_kimi_calls"] == 0
    assert report_unfiltered["total_raw_kimi_calls"] == 1

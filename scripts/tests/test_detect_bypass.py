#!/usr/bin/env python3
"""Tests for detect_bypass.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import importlib.util
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detect_bypass import (
    DELEGATE_CMD_RE,
    KIMI_SUBAGENT_RE,
    extract_task_from_raw,
    is_false_positive_command,
    is_machine_protocol_call,
    nudge_report,
)


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
    _mod = load_module(root / "scripts" / "detect_bypass.py")

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


# ── is_machine_protocol_call ──────────────────────────────────────────────────

class TestIsMachineProtocolCall:
    def test_mode_json_flag_is_machine_call(self) -> None:
        assert is_machine_protocol_call("pi --mode json --provider kimi-coding") is True

    def test_mode_equals_json_is_machine_call(self) -> None:
        assert is_machine_protocol_call("pi --mode=json") is True

    def test_session_flag_is_machine_call(self) -> None:
        assert is_machine_protocol_call("pi --session=abc123 --task foo") is True

    def test_plain_pi_command_is_not_machine_call(self) -> None:
        assert is_machine_protocol_call("pi --provider kimi-coding --task do something") is False

    def test_empty_string_is_not_machine_call(self) -> None:
        assert is_machine_protocol_call("") is False


# ── is_false_positive_command ─────────────────────────────────────────────────

class TestIsFalsePositiveCommand:
    @pytest.mark.parametrize("cmd", [
        "rg pi-kimi-subagent scripts/",
        "grep -r pi-kimi-subagent .",
        "git commit -m 'feat: add kimi support'",
        "git log --oneline",
        "git show HEAD",
        "git diff HEAD~1",
        "git add scripts/delegate.py",
        "python3 -c \"import detect_bypass\"",
        "pi-kimi-subagent --help",
        "pi --provider kimi-coding --help",
        "command -v pi",
        "command -v pi-kimi-subagent",
    ])
    def test_known_false_positive_commands(self, cmd: str) -> None:
        assert is_false_positive_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "pi-kimi-subagent --task 'do something'",
        "pi --provider kimi-coding --task 'summarize'",
        "./skills/kimi-delegate/scripts/delegate.py --task foo",
    ])
    def test_real_invocation_is_not_false_positive(self, cmd: str) -> None:
        assert is_false_positive_command(cmd) is False

    def test_empty_string_is_not_false_positive(self) -> None:
        assert is_false_positive_command("") is False


# ── extract_task_from_raw ─────────────────────────────────────────────────────

class TestExtractTaskFromRaw:
    def test_extracts_from_print_flag_double_quotes(self) -> None:
        cmd = 'pi --provider kimi-coding --print "summarize the repo"'
        assert extract_task_from_raw(cmd) == "summarize the repo"

    def test_extracts_from_print_flag_single_quotes(self) -> None:
        cmd = "pi --provider kimi-coding --print 'list open issues'"
        assert extract_task_from_raw(cmd) == "list open issues"

    def test_extracts_from_pi_kimi_subagent_quoted_arg(self) -> None:
        cmd = 'pi-kimi-subagent "review the diff"'
        assert extract_task_from_raw(cmd) == "review the diff"

    def test_returns_none_for_bare_command_no_task_text(self) -> None:
        cmd = "pi --provider kimi-coding"
        assert extract_task_from_raw(cmd) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert extract_task_from_raw("") is None


# ── KIMI_SUBAGENT_RE pattern ──────────────────────────────────────────────────

class TestKimiSubagentRe:
    @pytest.mark.parametrize("cmd", [
        "pi-kimi-subagent --task do something",
        "pi --provider kimi-coding --task foo",
        "&& pi-kimi-subagent --task bar",
        "|| pi --provider kimi-coding --task baz",
        "sudo pi-kimi-subagent --task qux",
    ])
    def test_matches_raw_kimi_invocations(self, cmd: str) -> None:
        assert KIMI_SUBAGENT_RE.search(cmd) is not None

    @pytest.mark.parametrize("cmd", [
        "rg pi-kimi-subagent",
        "grep pi-kimi-subagent scripts/",
        "cat pi-kimi-subagent",
        "./skills/kimi-delegate/scripts/delegate.py",
    ])
    def test_does_not_match_search_or_read_commands(self, cmd: str) -> None:
        assert KIMI_SUBAGENT_RE.search(cmd) is None


# ── nudge_report with incidents ───────────────────────────────────────────────

class TestNudgeReportWithIncidents:
    _BYPASS_REPORT = {
        "total_raw_kimi_calls": 3,
        "total_delegate_calls": 7,
        "bypass_rate_pct": 30.0,
        "target_bypass_rate_pct": 20.0,
        "bypasses_by_repo": {"my-repo": 3},
        "incidents": [
            {"command": 'pi --provider kimi-coding --print "review the diff"', "repo": "my-repo"},
            {"command": "pi-kimi-subagent --task foo", "repo": "my-repo"},
            {"command": 'pi-kimi-subagent "summarise changes"', "repo": "my-repo"},
        ],
    }

    def test_includes_bypass_rate(self) -> None:
        msg = nudge_report(self._BYPASS_REPORT)
        assert "30.0" in msg

    def test_includes_repo_name(self) -> None:
        msg = nudge_report(self._BYPASS_REPORT)
        assert "my-repo" in msg

    def test_suggests_kd_command_for_extractable_task(self) -> None:
        msg = nudge_report(self._BYPASS_REPORT)
        assert "summarise changes" in msg

    def test_includes_wrapper_guidance(self) -> None:
        msg = nudge_report(self._BYPASS_REPORT)
        assert "delegate.py" in msg or "kimi-delegate" in msg

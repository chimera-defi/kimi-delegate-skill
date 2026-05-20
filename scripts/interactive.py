#!/usr/bin/env python3
"""Interactive envelope builder for kimi-delegate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def ask(prompt: str, default: str = "") -> str:
    if default:
        full = f"{prompt} [{default}]: "
    else:
        full = f"{prompt}: "
    try:
        reply = input(full).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        raise SystemExit(130)
    return reply if reply else default


def ask_yn(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    reply = ask(prompt + suffix, "y" if default else "n").lower()
    return reply in ("y", "yes")


def classify(task: str) -> str:
    import re
    patterns = [
        ("search", re.compile(r"\b(find|search|locate|grep|where)\b", re.I)),
        ("summarize", re.compile(r"\b(summarize|summary|explain|tl;dr)\b", re.I)),
        ("review", re.compile(r"\b(review|audit|risk|regression|bug)\b", re.I)),
        ("draft", re.compile(r"\b(draft|write|prepare|compose)\b", re.I)),
        ("implementation-lite", re.compile(r"\b(fix|patch|edit|update|implement)\b", re.I)),
    ]
    for label, pat in patterns:
        if pat.search(task):
            return label
    return "summarize"


def suggest_acceptance(task_class: str) -> list[str]:
    base = [
        "Answer stays within declared scope.",
        "Output is concise and directly actionable.",
        "Include concrete evidence with file/path and line references when analysis claims findings.",
        "If blocked, include exact missing input needed.",
    ]
    extras: dict[str, list[str]] = {
        "search": ["Only report paths that actually exist.", "Prefer grep/ripgrep evidence over memory."],
        "review": ["Rate each issue severity: critical/high/medium/low.", "Suggest specific fix for each finding."],
        "draft": ["Match existing codebase style and conventions.", "Include rationale for non-obvious choices."],
        "implementation-lite": ["Only modify files in declared write_scope.", "Provide diff preview in Evidence section."],
    }
    return base + extras.get(task_class, [])


def suggest_timeout(task_class: str) -> int:
    defaults = {
        "search": 60,
        "summarize": 75,
        "draft": 120,
        "review": 120,
        "implementation-lite": 150,
        "default": 90,
    }
    return defaults.get(task_class, defaults["default"])


def suggest_output_tokens(task_class: str) -> int:
    defaults = {
        "search": 500,
        "summarize": 800,
        "draft": 1100,
        "review": 1200,
        "implementation-lite": 1200,
        "default": 900,
    }
    return defaults.get(task_class, defaults["default"])


def interactive_build() -> dict:
    print("=== Kimi Delegate Interactive Envelope Builder ===")
    print()

    goal = ask("What task should Kimi execute")
    if not goal:
        print("error: goal is required", file=sys.stderr)
        raise SystemExit(2)

    task_class = classify(goal)
    print(f"Detected task class: {task_class}")
    if ask_yn("Is this correct", default=True):
        pass
    else:
        classes = ["search", "summarize", "review", "draft", "implementation-lite"]
        print(f"Available: {', '.join(classes)}")
        task_class = ask("Enter correct task class", task_class)

    context_file = ask("Context file path (optional)")
    context_text = ""
    if context_file:
        cp = Path(context_file)
        if cp.exists():
            context_text = cp.read_text(encoding="utf-8", errors="ignore")[:1500]
        else:
            print(f"warning: context file not found: {cp}", file=sys.stderr)

    suggested_timeout = suggest_timeout(task_class)
    timeout_str = ask(f"Timeout seconds", str(suggested_timeout))
    try:
        timeout = int(timeout_str)
    except ValueError:
        timeout = suggested_timeout

    suggested_tokens = suggest_output_tokens(task_class)
    tokens_str = ask(f"Max output tokens", str(suggested_tokens))
    try:
        max_tokens = int(tokens_str)
    except ValueError:
        max_tokens = suggested_tokens

    no_network = ask_yn("Block network access", default=False)

    acceptance = suggest_acceptance(task_class)
    print()
    print("Suggested acceptance criteria:")
    for i, a in enumerate(acceptance, 1):
        print(f"  {i}. {a}")
    if ask_yn("Add custom acceptance criteria"):
        custom = ask("Enter custom criterion")
        if custom:
            acceptance.append(custom)

    output_format = ask("Output format", "markdown")
    if output_format not in ("markdown", "json", "bullet-list"):
        output_format = "markdown"

    write_scope = ask("Write scope globs (comma-separated)", ".")
    scopes = [s.strip() for s in write_scope.split(",") if s.strip()]

    envelope = {
        "goal": goal,
        "task_class": task_class,
        "context_summary": context_text,
        "constraints": {
            "max_output_tokens": max_tokens,
            "timeout_seconds": timeout,
            "no_network": no_network,
        },
        "acceptance": acceptance,
        "output_schema": {
            "format": output_format,
            "required_sections": ["Result", "Evidence", "Next steps"],
        },
        "write_scope": scopes,
        "escalation_rules": [
            "If schema invalid twice, escalate to fallback.",
            "If timeout, run fallback immediately.",
        ],
        "metrics": {
            "parent_context_tokens": max(1, int(len((goal + "\n" + context_text).split()) * 1.3)),
        },
    }

    return envelope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive envelope builder")
    parser.add_argument("--output", "-o", default="", help="Write envelope to file")
    args = parser.parse_args()

    if not args.interactive:
        print("Use --interactive to build an envelope interactively.")
        return 0

    envelope = interactive_build()
    text = json.dumps(envelope, indent=2)
    print()
    print(text)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved to {out}")

    # Offer to delegate immediately
    if ask_yn("Delegate this envelope now"):
        import subprocess
        import tempfile
        skill_root = Path(__file__).resolve().parents[1]
        delegate_script = skill_root / "scripts" / "delegate.py"
        fd, tmp_path = tempfile.mkstemp(prefix="kimi-delegate-envelope-", suffix=".json", text=True)
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            proc = subprocess.run(
                [str(delegate_script), "--task", envelope["goal"]],
                capture_output=False,
                text=True,
            )
            return proc.returncode
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

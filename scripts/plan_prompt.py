#!/usr/bin/env python3
"""Generate a structured delegation envelope."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TASK_CLASS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("search", re.compile(r"\b(find|search|locate|grep|where|look|scan|discover)\b", re.I)),
    ("summarize", re.compile(r"\b(summarize|summary|explain|tl;dr|condense|recap|overview)\b", re.I)),
    ("review", re.compile(r"\b(review|audit|risk|regression|bug|security|vulnerability|pentest|assess|evaluate|check|inspect)\b", re.I)),
    ("draft", re.compile(r"\b(draft|write|prepare|compose|create|generate|produce|author)\b", re.I)),
    ("implementation-lite", re.compile(r"\b(fix|patch|edit|update|implement|refactor|migrate|upgrade|add|remove|change|modify|convert|migrate|rewrite)\b", re.I)),
]


def classify(text: str) -> str:
    scores: dict[str, int] = {}
    for label, pattern in TASK_CLASS_PATTERNS:
        matches = len(pattern.findall(text))
        if matches > 0:
            scores[label] = matches

    if not scores:
        return "summarize"

    # If top score is tied or ambiguous, default to the more conservative class
    max_score = max(scores.values())
    top_labels = [k for k, v in scores.items() if v == max_score]
    if len(top_labels) == 1:
        return top_labels[0]

    # Tie-break: prefer review > implementation-lite > draft > search > summarize
    priority = ["review", "implementation-lite", "draft", "search", "summarize"]
    for p in priority:
        if p in top_labels:
            return p
    return "summarize"


def tokenize_estimate(text: str) -> int:
    words = re.findall(r"\S+", text)
    return max(1, int(len(words) * 1.3))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--context-file")
    parser.add_argument("--accept", action="append", default=[])
    parser.add_argument("--write-scope", action="append", default=[])
    parser.add_argument("--output-format", default="markdown", choices=["markdown", "json", "bullet-list"])
    args = parser.parse_args()

    context_text = ""
    if args.context_file:
        context_path = Path(args.context_file)
        if context_path.exists():
            context_text = context_path.read_text(encoding="utf-8", errors="ignore")
        else:
            print(f"warning: context file not found: {context_path}", file=sys.stderr)

    task_class = classify(args.task)
    parent_context_tokens = tokenize_estimate(args.task + "\n" + context_text)

    acceptance = args.accept or [
        "Answer stays within declared scope.",
        "Output is concise and directly actionable.",
        "Include concrete evidence with file/path and line references when analysis claims findings.",
        "If blocked, include exact missing input needed.",
    ]

    envelope = {
        "goal": args.task,
        "task_class": task_class,
        "context_summary": context_text[:1500],
        "constraints": {
            "max_output_tokens": 1100,
            "timeout_seconds": 120,
            "no_network": False,
        },
        "acceptance": acceptance,
        "output_schema": {
            "format": args.output_format,
            "required_sections": ["Result", "Evidence", "Next steps"],
        },
        "write_scope": args.write_scope or ["."],
        "escalation_rules": [
            "If schema invalid twice, escalate to fallback.",
            "If timeout, run fallback immediately.",
        ],
        "metrics": {
            "parent_context_tokens": parent_context_tokens,
        },
    }

    print(json.dumps(envelope, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

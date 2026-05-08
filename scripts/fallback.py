#!/usr/bin/env python3
"""Fallback executor for kimi-delegate."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import shutil
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def codex_supports_sandbox() -> bool:
    proc = subprocess.run(
        ["codex", "exec", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "--sandbox" in (proc.stdout or "")


def run_codex(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    cmd = ["codex", "exec", "--model", model]
    if codex_supports_sandbox():
        cmd += ["--sandbox", "workspace-write"]
    cmd += [prompt]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def run_pi(prompt: str, provider: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    cmd = [
        "pi",
        "--provider",
        provider,
        "--model",
        model,
        "--print",
        prompt,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope-file", required=True)
    parser.add_argument("--fallback-engine", default="codex", choices=["codex", "pi"])
    parser.add_argument("--model", default="gpt-5.3-codex")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    envelope_path = Path(args.envelope_file)
    if not envelope_path.exists():
        sys.stderr.write(f"fallback error: envelope file not found: {envelope_path}\n")
        return 2
    try:
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"fallback error: invalid envelope JSON: {exc}\n")
        return 2

    prompt = (
        "Fallback path engaged after Kimi failure.\n"
        "Execute task envelope exactly and return concise output.\n\n"
        + json.dumps(envelope, indent=2)
    )

    if args.fallback_engine == "codex":
        if shutil.which("codex") is None:
            sys.stderr.write("fallback error: `codex` binary not found\n")
            return 127
        proc = run_codex(prompt, args.model, args.timeout)
    else:
        if shutil.which("pi") is None:
            sys.stderr.write("fallback error: `pi` binary not found\n")
            return 127
        proc = run_pi(prompt, args.provider, args.model, args.timeout)

    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return proc.returncode

    sys.stdout.write(proc.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

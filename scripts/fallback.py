#!/usr/bin/env python3
"""Fallback executor for kimi-delegate."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def codex_supports_sandbox() -> bool:
    try:
        proc = subprocess.run(
            ["codex", "exec", "--help"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return "--sandbox" in (proc.stdout or "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _load_config() -> dict:
    """Load kimi-delegate config for default timeout values."""
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir.parent / "config" / "kimi-delegate.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"max_timeout_seconds": 180}


def _default_timeout() -> int:
    return int(_load_config().get("max_timeout_seconds", 180))


def _run_with_timeout(cmd: list[str], timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr=f"timeout after {timeout}s")


def run_codex(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess[str]:
    cmd = ["codex", "exec", "--model", model]
    if codex_supports_sandbox():
        cmd += ["--sandbox", "workspace-write"]
    cmd += [prompt]
    env = os.environ.copy()
    env["KIMI_DELEGATE_ACTIVE"] = "1"
    return _run_with_timeout(cmd, timeout, env)


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
    env = os.environ.copy()
    env["KIMI_DELEGATE_ACTIVE"] = "1"
    return _run_with_timeout(cmd, timeout, env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope-file", required=True)
    parser.add_argument("--fallback-engine", default="codex", choices=["codex", "pi"])
    parser.add_argument("--model", default="gpt-5.3-codex")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--timeout", type=int, default=_default_timeout())
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

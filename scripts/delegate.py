#!/usr/bin/env python3
"""Plan + delegate execution through Kimi with fallback and telemetry."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import shutil
import re
import os
import sys
from pathlib import Path


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def current_repo_root(default_root: Path | None = None) -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    if default_root is not None:
        return default_root.resolve()
    return Path.cwd()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing required config file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_repo_config(repo_root: Path, config: dict) -> dict:
    """Load per-repo overrides from .kimi-delegate.json in repo root."""
    repo_config_path = repo_root / ".kimi-delegate.json"
    if repo_config_path.exists():
        try:
            overrides = json.loads(repo_config_path.read_text(encoding="utf-8"))
            merged = dict(config)
            merged.update(overrides)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return config


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def call(cmd: list[str], timeout: int) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return proc.returncode, proc.stdout, proc.stderr, latency_ms
    except subprocess.TimeoutExpired:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return 124, "", f"timeout after {timeout}s", latency_ms


def detect_auth_error(stderr: str) -> bool:
    """Detect authentication / session expiry patterns that require manual resume."""
    if not stderr:
        return False
    patterns = [
        r"auth",
        r"authentication",
        r"unauthorized",
        r"401",
        r"403",
        r"session",
        r"expired",
        r"token",
        r"credential",
        r"login",
        r"siwe",
        r"sign.in",
        r"resume",
        r"re-auth",
    ]
    lower = stderr.lower()
    return any(re.search(p, lower) for p in patterns)


def classify_error(rc: int, stderr: str, schema_valid: bool) -> str:
    """Categorize failure reason for telemetry and user guidance."""
    if rc == 124:
        return "timeout"
    if detect_auth_error(stderr):
        return "auth_error"
    if rc != 0:
        return "provider_error"
    if not schema_valid:
        return "schema_invalid"
    return "unknown"


def estimate_repo_scale(repo_root: Path) -> dict[str, float | int]:
    """Estimate repo size for timeout scaling. Fast, approximate."""
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return {"files": 0, "mb": 0}
        files = len(proc.stdout.strip().splitlines())
        # Approximate size via git ls-files with du fallback
        du_proc = subprocess.run(
            ["du", "-sm", "."],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        mb = 0
        if du_proc.returncode == 0:
            parts = du_proc.stdout.strip().split()
            if parts:
                try:
                    mb = int(parts[0])
                except ValueError:
                    pass
        return {"files": files, "mb": mb}
    except Exception:
        return {"files": 0, "mb": 0}


def save_task_to_history(repo_root: Path, task: str) -> None:
    """Append task to local history file for --last support."""
    history_path = repo_root / "artifacts" / "kimi-delegate" / "history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"task": task, "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_last_task(repo_root: Path) -> str:
    """Load the most recent task from history."""
    history_path = repo_root / "artifacts" / "kimi-delegate" / "history.jsonl"
    if not history_path.exists():
        return ""
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not lines:
            return ""
        last = json.loads(lines[-1])
        return str(last.get("task", ""))
    except (json.JSONDecodeError, OSError):
        return ""


def compute_timeout(
    base_timeout: int,
    task_class: str,
    config: dict,
    routing: dict,
    repo_scale: dict[str, float | int],
) -> int:
    """Scale timeout by repo size and task class."""
    route = routing.get("task_classes", {}).get(task_class, routing.get("default", {}))
    scale = float(route.get("timeout_scale", 1.0))

    files = int(repo_scale.get("files", 0))
    mb = int(repo_scale.get("mb", 0))

    large_files = int(config.get("large_repo_threshold_files", 10000))
    large_mb = int(config.get("large_repo_threshold_mb", 500))
    large_mult = float(config.get("large_repo_timeout_multiplier", 2.0))

    xlarge_files = int(config.get("xlarge_repo_threshold_files", 50000))
    xlarge_mb = int(config.get("xlarge_repo_threshold_mb", 1000))
    xlarge_mult = float(config.get("xlarge_repo_timeout_multiplier", 3.0))

    repo_mult = 1.0
    if files >= xlarge_files or mb >= xlarge_mb:
        repo_mult = xlarge_mult
    elif files >= large_files or mb >= large_mb:
        repo_mult = large_mult

    return int(base_timeout * scale * repo_mult)


def output_is_valid(text: str, required_sections: list[str]) -> bool:
    if not text.strip():
        return False
    for section in required_sections:
        section = section.strip()
        if not section:
            continue
        heading = re.compile(rf"(?im)^#{{1,6}}\s*{re.escape(section)}\s*$")
        if not heading.search(text):
            return False
    return True


def build_envelope(task: str, context_file: str | None) -> dict:
    cmd = [
        str(script_root() / "plan_prompt.py"),
        "--task",
        task,
    ]
    if context_file:
        cmd += ["--context-file", context_file]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"plan_prompt.py produced invalid JSON: {exc}") from exc


def run_check(config: dict, routing: dict) -> int:
    """Pre-flight environment check."""
    checks: list[dict[str, str]] = []

    pi_kimi = shutil.which("pi-kimi-subagent")
    pi_bin = shutil.which("pi")
    codex_bin = shutil.which("codex")
    kimi_delegate_bin = shutil.which("kimi-delegate")

    checks.append({
        "name": "pi-kimi-subagent",
        "status": "ok" if pi_kimi else "missing",
        "path": pi_kimi or "",
    })
    checks.append({
        "name": "pi",
        "status": "ok" if pi_bin else "missing",
        "path": pi_bin or "",
    })
    checks.append({
        "name": "codex",
        "status": "ok" if codex_bin else "missing",
        "path": codex_bin or "",
    })
    checks.append({
        "name": "kimi-delegate (shorthand)",
        "status": "ok" if kimi_delegate_bin else "missing",
        "path": kimi_delegate_bin or "",
    })

    all_ok = bool(pi_kimi or pi_bin) and bool(codex_bin)

    result = {
        "all_ok": all_ok,
        "primary": "pi-kimi-subagent" if pi_kimi else "pi",
        "fallback": "codex",
        "checks": checks,
        "config": {
            "provider": config.get("provider"),
            "model": config.get("model"),
            "fallback_model": config.get("fallback_model"),
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if all_ok else 1


def print_stats(repo_root: Path) -> int:
    """Print a concise telemetry summary for the current repo."""
    try:
        proc = subprocess.run(
            [str(script_root() / "kimi_delegate_telemetry.py"), "summary", "--days", "14"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print("warning: telemetry summary failed", file=sys.stderr)
            return 1
        data = json.loads(proc.stdout)
        calls = data.get("delegate_calls", 0)
        fallback = data.get("fallback_rate_pct", 0.0)
        saved = data.get("estimated_tokens_saved", 0)
        latency = data.get("avg_latency_ms", 0.0)
        auth = data.get("auth_errors", 0)
        timeouts = data.get("timeouts", 0)

        print(f"📊 Kimi Delegate Stats (last 14d)")
        print(f"   Calls:        {calls}")
        print(f"   Fallback:     {fallback}%")
        print(f"   Tokens saved: {saved}")
        print(f"   Avg latency:  {latency}ms")
        print(f"   Auth errors:  {auth}")
        print(f"   Timeouts:     {timeouts}")
        return 0
    except Exception as exc:
        print(f"warning: stats error: {exc}", file=sys.stderr)
        return 1


def run_delegate(
    task: str,
    context_file: str | None,
    task_class: str | None,
    dry_run: bool,
    print_envelope: bool,
    config: dict,
    routing: dict,
    repo_root: Path,
) -> int:
    """Execute a single delegation task."""
    try:
        envelope = build_envelope(task, context_file)
    except Exception as exc:
        print(f"error: {exc}", flush=True)
        return 2
    if task_class:
        envelope["task_class"] = task_class

    skill = skill_root()
    task_class = envelope.get("task_class", "default")
    route = routing.get("task_classes", {}).get(task_class, routing.get("default", {}))
    base_timeout = int(route.get("timeout_seconds", config.get("timeout_seconds", 120)))
    model = str(route.get("model", config.get("model", "k2p6")))

    repo_scale = estimate_repo_scale(repo_root)
    timeout_seconds = compute_timeout(base_timeout, task_class, config, routing, repo_scale)

    if print_envelope or dry_run:
        envelope["_computed"] = {
            "timeout_seconds": timeout_seconds,
            "base_timeout": base_timeout,
            "repo_scale": repo_scale,
        }
        print(json.dumps(envelope, indent=2))
        if dry_run:
            return 0

    envelope_text = json.dumps(envelope, indent=2)
    prompt = (
        "Execute delegated envelope strictly. "
        "Return concise output with sections: Result, Evidence, Next steps.\n\n"
        + envelope_text
    )

    if shutil.which("pi-kimi-subagent") is not None:
        cmd = ["pi-kimi-subagent", prompt]
        primary_model_used = "pi-kimi-subagent:default"
    else:
        if shutil.which("pi") is None:
            print("error: neither `pi-kimi-subagent` nor `pi` was found", flush=True)
            return 127
        cmd = [
            "pi",
            "--provider",
            str(config.get("provider", "kimi-coding")),
            "--model",
            model,
            "--thinking",
            str(config.get("thinking", "medium")),
            "--print",
            prompt,
        ]
        primary_model_used = f"{config.get('provider', 'kimi-coding')}:{model}"

    fallback_used = False
    fallback_reason = ""
    status = "ok"
    required_sections = list(envelope.get("output_schema", {}).get("required_sections", []))
    max_retries = int(route.get("retry", config.get("max_retries", 1)))

    retry_count = 0
    schema_valid = False
    latency_ms = 0.0
    attempt_latencies: list[float] = []
    last_stderr = ""

    while retry_count <= max_retries:
        rc, out, err, attempt_latency_ms = call(cmd, timeout=timeout_seconds)
        attempt_latencies.append(round(attempt_latency_ms, 2))
        latency_ms += attempt_latency_ms
        last_stderr = err
        schema_valid = output_is_valid(out, required_sections)
        if rc == 0 and schema_valid:
            break
        retry_count += 1

    if rc != 0 or not schema_valid:
        fallback_used = True
        error_category = classify_error(rc, last_stderr, schema_valid)
        fallback_reason = error_category

        if error_category == "auth_error":
            print(
                f"kimi-delegate: auth/session error detected. "
                f"The Kimi subagent could not authenticate or its session expired.\n"
                f"\n"
                f"Steps to resume manually:\n"
                f"  1. Run the auth flow for your provider (e.g., `pi --provider kimi-coding --login`)\n"
                f"  2. Or run: `pi-kimi-subagent --check` to verify session state\n"
                f"  3. Then re-run this task: kimi-delegate --task '{task}'\n"
                f"\n"
                f"Raw stderr:\n{last_stderr}\n",
                flush=True,
            )
            status = "auth_error"
        else:
            envelope_path = repo_root / "artifacts" / "kimi-delegate" / "last-envelope.json"
            envelope_path.parent.mkdir(parents=True, exist_ok=True)
            envelope_path.write_text(envelope_text + "\n", encoding="utf-8")

            fallback_cmd = [
                str(script_root() / "fallback.py"),
                "--envelope-file",
                str(envelope_path),
                "--fallback-engine",
                str(config.get("fallback_engine", "codex")),
                "--model",
                str(config.get("fallback_model", "gpt-5.3-codex")),
                "--provider",
                str(config.get("fallback_provider", "openai")),
            ]
            f_rc, f_out, f_err, f_latency_ms = call(fallback_cmd, timeout=max(timeout_seconds, 180))
            latency_ms += f_latency_ms
            attempt_latencies.append(round(f_latency_ms, 2))
            rc = f_rc
            out = f_out
            last_stderr = f_err
            try:
                envelope_path.unlink(missing_ok=True)
            except OSError:
                pass

            if rc != 0:
                status = "error"

    parent_tokens = int(envelope.get("metrics", {}).get("parent_context_tokens", 0))
    delegate_input_tokens = estimate_tokens(prompt)
    delegate_output_tokens = estimate_tokens(out) if status != "auth_error" else 0
    saved = max(0, parent_tokens - delegate_output_tokens)

    telemetry_meta = {
        "repo_root": str(repo_root),
        "skill_root": str(skill),
        "retry_count": retry_count,
        "attempt_latencies": attempt_latencies,
        "repo_scale": repo_scale,
        "timeout_seconds": timeout_seconds,
        "base_timeout": base_timeout,
        "error_category": fallback_reason if fallback_used else "",
    }

    telemetry_cmd = [
        str(script_root() / "kimi_delegate_telemetry.py"),
        "record",
        "--status",
        status,
        "--task-class",
        str(task_class),
        "--model-used",
        primary_model_used if not fallback_used else f"fallback:{config.get('fallback_engine')}:{config.get('fallback_model')}",
        "--parent-context-tokens",
        str(parent_tokens),
        "--delegate-input-tokens",
        str(delegate_input_tokens),
        "--delegate-output-tokens",
        str(delegate_output_tokens),
        "--estimated-tokens-saved",
        str(saved),
        "--latency-ms",
        str(round(latency_ms, 2)),
        "--meta",
        json.dumps(telemetry_meta),
    ]

    if fallback_used:
        telemetry_cmd += ["--fallback-used", "--fallback-reason", fallback_reason]

    telemetry_proc = subprocess.run(telemetry_cmd, capture_output=True, text=True, check=False)
    if telemetry_proc.returncode != 0:
        print(
            f"warning: telemetry record failed ({telemetry_proc.returncode}): {telemetry_proc.stderr.strip()}",
            flush=True,
        )

    if status == "auth_error":
        return 126

    if rc != 0:
        if last_stderr:
            print(last_stderr)
        return rc

    print(out.rstrip())
    return 0


def run_batch(
    batch_file: str,
    context_file: str | None,
    task_class: str | None,
    config: dict,
    routing: dict,
    repo_root: Path,
) -> int:
    """Execute multiple tasks from a JSONL batch file."""
    path = Path(batch_file)
    if not path.exists():
        print(f"error: batch file not found: {path}", flush=True)
        return 2

    lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if not lines:
        print("error: batch file is empty", flush=True)
        return 2

    results: list[dict[str, Any]] = []
    overall_rc = 0

    for i, line in enumerate(lines, 1):
        try:
            task_spec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"error: batch line {i} invalid JSON: {exc}", flush=True)
            overall_rc = 2
            continue

        task = str(task_spec.get("task", ""))
        if not task:
            print(f"warning: batch line {i} missing 'task' key, skipping", flush=True)
            continue

        line_context = task_spec.get("context_file", context_file)
        line_class = task_spec.get("task_class", task_class)

        print(f"\n{'='*60}\n[batch {i}/{len(lines)}] {task}\n{'='*60}", flush=True)
        rc = run_delegate(task, line_context, line_class, False, False, config, routing, repo_root)
        results.append({"line": i, "task": task, "rc": rc})
        if rc != 0:
            overall_rc = rc

    print(f"\n{'='*60}\nBatch complete: {len(results)}/{len(lines)} tasks, exit {overall_rc}\n{'='*60}")
    return overall_rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_positional", nargs="?", default="", help="Task to delegate (positional)")
    parser.add_argument("--task", default="", help="Task to delegate (flag form)")
    parser.add_argument("--context-file")
    parser.add_argument("--task-class")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-envelope", action="store_true")
    parser.add_argument("--check", action="store_true", help="Pre-flight env check only")
    parser.add_argument("--stats", action="store_true", help="Print recent telemetry summary")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive envelope builder")
    parser.add_argument("--batch", default="", help="Path to JSONL file of tasks to delegate in batch")
    parser.add_argument("--last", action="store_true", help="Re-run the previous task from history")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: suppress extra output")
    args = parser.parse_args()

    # Positional takes precedence over --task
    task = args.task_positional or args.task

    skill = skill_root()
    repo_root = current_repo_root(skill)
    try:
        config = load_json(skill / "config" / "kimi-delegate.json")
        config = load_repo_config(repo_root, config)
        routing = load_json(skill / "config" / "routing.json")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", flush=True)
        return 2

    if args.check:
        return run_check(config, routing)

    if args.stats:
        return print_stats(repo_root)

    if args.last:
        task = load_last_task(repo_root)
        if not task:
            print("error: no previous task in history. Run a task first.", flush=True)
            return 2
        print(f"🔄 Re-running last task: {task}", flush=True)

    if args.interactive or (not task and not args.batch):
        interactive_script = script_root() / "interactive.py"
        if interactive_script.exists():
            return subprocess.run([str(interactive_script), "--interactive"]).returncode
        else:
            print("error: interactive.py not found", flush=True)
            return 2

    if args.batch:
        return run_batch(args.batch, args.context_file, args.task_class, config, routing, repo_root)

    # Save to history before running
    save_task_to_history(repo_root, task)

    rc = run_delegate(task, args.context_file, args.task_class, args.dry_run, args.print_envelope, config, routing, repo_root)

    if rc == 0 and not args.quick and not args.dry_run:
        print(f"\n✅ Task completed via Kimi wrapper. Run 'kd --stats' for telemetry.", flush=True)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

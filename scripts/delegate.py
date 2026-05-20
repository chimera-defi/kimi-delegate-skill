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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def current_repo_root(default_root: Path | None = None) -> Path:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
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
    env = os.environ.copy()
    env["KIMI_DELEGATE_ACTIVE"] = "1"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
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


def detect_agent_end_error(text: str) -> bool:
    """Detect pi stream protocol failures where agent_end is missing."""
    if not text:
        return False
    lower = text.lower()
    return "finished without an agent_end event" in lower or "without an agent_end event" in lower


def classify_error(rc: int, stderr: str, schema_valid: bool) -> str:
    """Categorize failure reason for telemetry and user guidance."""
    if rc == 124:
        return "timeout"
    if detect_auth_error(stderr):
        return "auth_error"
    if detect_agent_end_error(stderr):
        return "agent_end_missing"
    if rc != 0:
        return "provider_error"
    if not schema_valid:
        return "schema_invalid"
    return "unknown"


def load_templates() -> dict[str, dict]:
    """Load task templates from prompts/templates.json."""
    tpl_path = skill_root() / "prompts" / "templates.json"
    if not tpl_path.exists():
        return {}
    try:
        return json.loads(tpl_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def list_templates() -> None:
    """Print available task templates."""
    templates = load_templates()
    if not templates:
        print("No templates found.")
        return
    print("Available templates:")
    for name, info in sorted(templates.items()):
        print(f"  {name:20s}  {info.get('task_class', 'unknown'):15s}  {info.get('description', '')}")


def apply_template(name: str) -> tuple[str, str] | None:
    """Return (task_text, task_class) for a template name, or None if not found."""
    templates = load_templates()
    tpl = templates.get(name)
    if not tpl:
        return None
    return str(tpl.get("template", "")), str(tpl.get("task_class", "summarize"))


def show_history(repo_root: Path, limit: int = 10) -> None:
    """Print recent task history."""
    history_path = repo_root / "artifacts" / "kimi-delegate" / "history.jsonl"
    if not history_path.exists():
        print("No task history found.")
        return
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not lines:
            print("No task history found.")
            return
        recent = lines[-limit:]
        print(f"Recent tasks (last {len(recent)}):")
        for line in reversed(recent):
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                task = entry.get("task", "")
                print(f"  {ts}  {task[:60]}{'...' if len(task) > 60 else ''}")
            except json.JSONDecodeError:
                continue
    except OSError:
        print("No task history found.")


def load_last_failed_task(repo_root: Path) -> str:
    """Load the most recent task that had a non-zero exit."""
    events_path = repo_root / "artifacts" / "kimi-delegate" / "events.jsonl"
    if not events_path.exists():
        return ""
    try:
        lines = events_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        for line in reversed(lines):
            try:
                event = json.loads(line)
                if event.get("event") == "delegate_invocation" and event.get("status") != "ok":
                    goal = event.get("meta", {}).get("goal", "")
                    if goal:
                        return str(goal)
            except json.JSONDecodeError:
                continue
        return ""
    except OSError:
        return ""


# Default file-extension -> task suggestion mapping.
# Loadable via .kimi-delegate.json key "suggest_rules" for per-repo overrides.
DEFAULT_SUGGEST_RULES: list[dict[str, Any]] = [
    {
        "name": "python_tests",
        "extensions": [".py"],
        "path_keywords": ["test", "spec"],
        "min_count": 1,
        "task": "Review changes to test files and suggest fixes for any broken tests.",
        "task_class": "review",
    },
    {
        "name": "frontend_js",
        "extensions": [".js", ".ts", ".jsx", ".tsx"],
        "min_count": 3,
        "task": "Review frontend changes for React component consistency and potential bugs.",
        "task_class": "review",
    },
    {
        "name": "python_code",
        "extensions": [".py"],
        "min_count": 3,
        "task": "Review Python changes for type safety, import issues, and logic bugs.",
        "task_class": "review",
    },
    {
        "name": "docs",
        "extensions": [".md"],
        "min_count": 1,
        "task": "Summarize documentation changes and check for broken links or formatting issues.",
        "task_class": "summarize",
    },
    {
        "name": "rust_code",
        "extensions": [".rs"],
        "min_count": 3,
        "task": "Review Rust changes for borrow-checker safety, idiomatic patterns, and potential bugs.",
        "task_class": "review",
    },
    {
        "name": "go_code",
        "extensions": [".go"],
        "min_count": 3,
        "task": "Review Go changes for error handling, goroutine safety, and idiomatic patterns.",
        "task_class": "review",
    },
    {
        "name": "java_code",
        "extensions": [".java", ".kt"],
        "min_count": 3,
        "task": "Review JVM changes for type safety, concurrency issues, and logic bugs.",
        "task_class": "review",
    },
]


def _load_suggest_rules(config: dict) -> list[dict[str, Any]]:
    return list(config.get("suggest_rules", DEFAULT_SUGGEST_RULES))


def suggest_task_from_git(repo_root: Path, config: dict | None = None) -> tuple[str, str] | None:
    """Auto-suggest a task based on git status."""
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return None
        lines = proc.stdout.strip().splitlines()
        if not lines:
            return None

        rules = _load_suggest_rules(config or {})
        for rule in rules:
            exts = rule.get("extensions", [])
            keywords = rule.get("path_keywords", [])
            min_count = rule.get("min_count", 1)
            count = sum(
                1
                for line in lines
                if any(line.strip().endswith(ext) for ext in exts)
                and (not keywords or any(kw in line.lower() for kw in keywords))
            )
            if count >= min_count:
                return str(rule.get("task", "")), str(rule.get("task_class", "summarize"))

        return f"Summarize the {len(lines)} changed files in this repo.", "summarize"
    except Exception:
        return None


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


_history_lock = threading.Lock()


def _redact_sensitive(text: str) -> str:
    """Strip likely tokens/secrets from stderr before persisting to telemetry."""
    import re as _re
    # Redact bearer tokens, API keys, SIWE signatures, session tokens
    patterns = [
        (r"(?i)(bearer\s+)[a-z0-9_\-]{20,}", r"\1<REDACTED>"),
        (r"(?i)(token[=:]\s*)[a-z0-9_\-]{20,}", r"\1<REDACTED>"),
        (r"(?i)(api[_\-]?key[=:]\s*)[a-z0-9_\-]{20,}", r"\1<REDACTED>"),
        (r"(?i)(session[=:]\s*)[a-z0-9_\-]{20,}", r"\1<REDACTED>"),
        (r"(?i)(signature[=:]\s*)0x[a-f0-9]{20,}", r"\1<REDACTED>"),
    ]
    for pat, repl in patterns:
        text = _re.sub(pat, repl, text)
    return text


def save_task_to_history(repo_root: Path, task: str) -> None:
    """Append task to local history file for --last support."""
    history_path = repo_root / "artifacts" / "kimi-delegate" / "history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"task": task, "timestamp": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    with _history_lock:
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def load_last_task(repo_root: Path) -> str:
    """Load the most recent task from history. Tolerates corrupted tail lines."""
    history_path = repo_root / "artifacts" / "kimi-delegate" / "history.jsonl"
    if not history_path.exists():
        return ""
    try:
        lines = history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        if not lines:
            return ""
        # Walk backwards from tail to find first valid JSON line
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
                return str(last.get("task", ""))
            except json.JSONDecodeError:
                continue
        return ""
    except (json.JSONDecodeError, OSError):
        return ""


def compute_timeout(
    base_timeout: int,
    task_class: str,
    config: dict,
    routing: dict,
    repo_scale: dict[str, float | int],
    override: int | None = None,
) -> int:
    """Scale timeout by repo size and task class. Capped at 120s unless overridden."""
    if override is not None and override > 0:
        return override

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

    computed = int(base_timeout * scale * repo_mult)
    # Cap at configured max_timeout_seconds (default 120s, override up to 600s)
    max_default = int(config.get("max_timeout_seconds", 120))
    return min(computed, max_default)


def output_is_valid(text: str, required_sections: list[str], output_format: str = "markdown") -> bool:
    if not text.strip():
        return False
    if output_format == "json":
        try:
            json.loads(text)
            return True
        except json.JSONDecodeError:
            return False
    for section in required_sections:
        section = section.strip()
        if not section:
            continue
        heading = re.compile(rf"(?im)^#{{1,6}}\s*{re.escape(section)}\s*$")
        if not heading.search(text):
            return False
    return True


def _safe_context_file(context_file: str | None, repo_root: Path) -> str | None:
    """Validate context-file path to prevent directory traversal outside repo."""
    if not context_file:
        return None
    try:
        path = (repo_root / context_file).resolve()
        # Ensure resolved path is inside repo_root
        path.relative_to(repo_root.resolve())
        return str(path)
    except (ValueError, RuntimeError):
        sys.stderr.write(f"[kimi-delegate] context-file escapes repo boundary: {context_file}\n")
        return None


def build_envelope(task: str, context_file: str | None) -> dict:
    cmd = [
        str(script_root() / "plan_prompt.py"),
        f"--task={task}",
    ]
    if context_file:
        cmd += ["--context-file", context_file]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"plan_prompt.py produced invalid JSON: {exc}") from exc


def health_check_quick(timeout: int = 15) -> tuple[bool, str]:
    """Fast health check: ping Kimi subagent with short timeout.
    Returns (ok, reason)."""
    if shutil.which("pi-kimi-subagent") is not None:
        cmd = ["pi-kimi-subagent", "ping"]
    elif shutil.which("pi") is not None:
        cmd = ["pi", "--provider", "kimi-coding", "--model", "k2p6", "--print", "ping"]
    else:
        return False, "pi binary not found"

    env = os.environ.copy()
    env["KIMI_DELEGATE_ACTIVE"] = "1"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
        if proc.returncode == 0:
            return True, ""
        stderr = proc.stderr.lower()
        if any(p in stderr for p in ("auth", "session", "expired", "token", "credential", "unauthorized")):
            return False, "auth/session error — run `pi --provider kimi-coding --login` and retry"
        return False, f"provider error (rc={proc.returncode}): {proc.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"health check timed out after {timeout}s — subagent is unresponsive"
    except Exception as exc:
        return False, f"health check exception: {exc}"


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

    # Fast health check
    health_ok, health_reason = health_check_quick(timeout=15)
    checks.append({
        "name": "kimi-health",
        "status": "ok" if health_ok else "error",
        "detail": health_reason,
    })

    all_ok = bool(pi_kimi or pi_bin) and bool(codex_bin) and health_ok

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
    show_cost: bool = False,
    timeout_override: int | None = None,
    repo_scale: dict[str, float | int] | None = None,
) -> int:
    """Execute a single delegation task."""
    # Auto health check: skip if recent success (5 min cache)
    if not dry_run:
        health_cache = repo_root / "artifacts" / "kimi-delegate" / ".health-cache"
        health_cache.parent.mkdir(parents=True, exist_ok=True)
        run_check_now = True
        if health_cache.exists():
            try:
                cache_age = time.time() - health_cache.stat().st_mtime
                if cache_age < 300:  # 5 minutes
                    run_check_now = False
            except OSError:
                pass
        if run_check_now:
            ok, reason = health_check_quick(timeout=15)
            if ok:
                health_cache.touch()
            else:
                print(
                    f"❌ Kimi subagent unreachable: {reason}\n"
                    f"\n"
                    f"To fix:\n"
                    f"  1. Check auth: pi --provider kimi-coding --login\n"
                    f"  2. Verify:      kd --health\n"
                    f"  3. Then retry:  kd --task '{task}'\n"
                    f"\n"
                    f"This fast-fail prevented a {compute_timeout(120, 'default', config, routing, {'files':0,'mb':0})}s timeout and saved credits.",
                    flush=True,
                )
                return 126

    try:
        safe_context = _safe_context_file(context_file, repo_root)
        envelope = build_envelope(task, safe_context)
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

    _repo_scale = repo_scale if repo_scale is not None else estimate_repo_scale(repo_root)
    timeout_seconds = compute_timeout(base_timeout, task_class, config, routing, _repo_scale, override=timeout_override)

    if print_envelope or dry_run:
        envelope["_computed"] = {
            "timeout_seconds": timeout_seconds,
            "base_timeout": base_timeout,
            "repo_scale": _repo_scale,
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
            print(
                "error: neither `pi-kimi-subagent` nor `pi` was found.\n"
                "\n"
                "To install:\n"
                "  1. Install the pi CLI for your provider\n"
                "  2. Or run: ./scripts/setup.sh (installs links and aliases)\n"
                "\n"
                "If pi is already installed but not on PATH, add it and retry.\n",
                flush=True,
            )
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
    output_format = envelope.get("output_schema", {}).get("format", "markdown")
    max_retries = int(route.get("retry", config.get("max_retries", 1)))

    retry_count = 0
    schema_valid = False
    latency_ms = 0.0
    attempt_latencies: list[float] = []
    attempt_rcs: list[int] = []
    last_stderr = ""
    agent_end_warning_seen = False

    while retry_count <= max_retries:
        rc, out, err, attempt_latency_ms = call(cmd, timeout=timeout_seconds)
        attempt_rcs.append(rc)
        attempt_latencies.append(round(attempt_latency_ms, 2))
        latency_ms += attempt_latency_ms
        last_stderr = err
        if detect_agent_end_error(err) or detect_agent_end_error(out):
            agent_end_warning_seen = True
        schema_valid = output_is_valid(out, required_sections, output_format)
        if rc == 0 and schema_valid:
            break
        # Exponential backoff on timeout: double timeout for next attempt
        # Cap at configured max to prevent runaway waits
        if rc == 124 and retry_count < max_retries:
            max_allowed = int(config.get("max_timeout_seconds", 600))
            new_timeout = min(int(timeout_seconds * 2), max_allowed)
            print(
                f"kimi-delegate: timeout ({timeout_seconds}s). Retrying with {new_timeout}s...",
                flush=True,
            )
            timeout_seconds = new_timeout
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
                f"  2. Or run: `kd --check` (or `kimi-delegate --check`) to verify session state\n"
                f"  3. Then re-run this task: kimi-delegate --task '{task}'\n"
                f"\n"
                f"Raw stderr:\n{last_stderr}\n",
                flush=True,
            )
            status = "auth_error"
        else:
            # Use PID-based unique filename to avoid TOCTOU race in parallel batch mode
            import os
            envelope_path = repo_root / "artifacts" / "kimi-delegate" / f"last-envelope-{os.getpid()}.json"
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
                "--timeout",
                str(max(timeout_seconds, 180)),
            ]
            f_rc, f_out, f_err, f_latency_ms = call(fallback_cmd, timeout=max(timeout_seconds, 180) + 30)
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
        "attempt_rcs": attempt_rcs,
        "attempt_latencies": attempt_latencies,
        "repo_scale": _repo_scale,
        "timeout_seconds": timeout_seconds,
        "base_timeout": base_timeout,
        "last_stderr_excerpt": _redact_sensitive((last_stderr or "")[:500]),
        "error_category": fallback_reason if fallback_used else "",
        "provider_warnings": ["agent_end_missing"] if agent_end_warning_seen else [],
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

    if agent_end_warning_seen:
        print(
            "warning: provider stream ended without an `agent_end` event at least once; "
            "recorded telemetry under meta.provider_warnings.",
            flush=True,
        )

    print(out.rstrip())
    if show_cost:
        # Rough cost estimate: parent tokens would cost ~10x more than delegate output
        parent_cost = parent_tokens * 0.00001  # $10 per 1M tokens
        delegate_cost = delegate_output_tokens * 0.000002  # $2 per 1M tokens
        savings_usd = max(0, parent_cost - delegate_cost)
        print(
            f"\n💰 Cost estimate: ${delegate_cost:.4f} (delegate) vs ${parent_cost:.4f} (parent direct)"
            f" | Saved: ${savings_usd:.4f} ({round(savings_usd * 100.0 / parent_cost, 1)}% cheaper)",
            flush=True,
        )
    return 0


def run_batch(
    batch_file: str,
    context_file: str | None,
    task_class: str | None,
    config: dict,
    routing: dict,
    repo_root: Path,
    parallel: int = 1,
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

    # Parse all tasks first to fail fast on invalid JSON
    tasks: list[tuple[int, str, str | None, str | None]] = []
    for i, line in enumerate(lines, 1):
        try:
            task_spec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"error: batch line {i} invalid JSON: {exc}", flush=True)
            return 2

        task = str(task_spec.get("task", ""))
        if not task:
            print(f"warning: batch line {i} missing 'task' key, skipping", flush=True)
            continue

        line_context = _safe_context_file(task_spec.get("context_file", context_file), repo_root)
        line_class = task_spec.get("task_class", task_class)
        tasks.append((i, task, line_context, line_class))

    results: list[dict[str, Any]] = []
    overall_rc = 0

    # Compute repo scale once for all batch tasks
    batch_repo_scale = estimate_repo_scale(repo_root)

    def _run_one(item: tuple[int, str, str | None, str | None]) -> dict[str, Any]:
        i, task, line_context, line_class = item
        print(f"\n{'='*60}\n[batch {i}/{len(lines)}] {task}\n{'='*60}", flush=True)
        rc = run_delegate(
            task, line_context, line_class, False, False,
            config, routing, repo_root, show_cost=False, timeout_override=None,
            repo_scale=batch_repo_scale,
        )
        return {"line": i, "task": task, "rc": rc}

    max_workers = max(1, min(parallel, 3))  # cap at 3 to avoid rate limits
    if max_workers == 1:
        for item in tasks:
            result = _run_one(item)
            results.append(result)
            if result["rc"] != 0:
                overall_rc = result["rc"]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, item): item for item in tasks}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result["rc"] != 0:
                    overall_rc = result["rc"]

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
    parser.add_argument("--parallel", type=int, default=1, help="Max concurrent tasks in batch mode (default 1, cap 3)")
    parser.add_argument("--last", action="store_true", help="Re-run the previous task from history")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: suppress extra output")
    parser.add_argument("--cost", action="store_true", help="Show estimated cost/savings after run")
    parser.add_argument("--template", default="", help="Use a named task template")
    parser.add_argument("--templates", action="store_true", help="List available templates")
    parser.add_argument("--suggest", action="store_true", help="Auto-suggest a task from git status")
    parser.add_argument("--history", action="store_true", help="Show recent task history")
    parser.add_argument("--retry", action="store_true", help="Retry the last failed task")
    parser.add_argument("--timeout-override", type=int, default=0, help="Override computed timeout (seconds)")
    parser.add_argument("--repo-scale", action="store_true", help="Show repo scale and computed timeout, then exit")
    parser.add_argument("--health", action="store_true", help="Quick health check and exit")
    args = parser.parse_args()

    # Positional takes precedence over --task
    task = args.task_positional or args.task

    # Stdin pipe support: echo "task" | kd
    if not task and not sys.stdin.isatty():
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            task = stdin_text

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

    if args.repo_scale:
        scale = estimate_repo_scale(repo_root)
        base_timeout = int(config.get("timeout_seconds", 120))
        tc = args.task_class or "default"
        timeout = compute_timeout(base_timeout, tc, config, routing, scale)
        print(json.dumps({
            "repo_root": str(repo_root),
            "tracked_files": scale["files"],
            "size_mb": scale["mb"],
            "base_timeout": base_timeout,
            "computed_timeout": timeout,
            "repo_class": "xlarge" if scale["mb"] >= 1000 or scale["files"] >= 50000 else ("large" if scale["mb"] >= 500 or scale["files"] >= 10000 else "normal"),
            "per_repo_config_loaded": (repo_root / ".kimi-delegate.json").exists(),
        }, indent=2))
        return 0

    if args.health:
        ok, reason = health_check_quick(timeout=15)
        if ok:
            print("✅ Kimi subagent healthy")
            return 0
        else:
            print(f"❌ Kimi subagent unhealthy: {reason}")
            return 1

    if args.templates:
        list_templates()
        return 0

    if args.history:
        show_history(repo_root)
        return 0

    if args.template:
        tpl_result = apply_template(args.template)
        if tpl_result is None:
            print(f"error: template '{args.template}' not found. Run --templates to list.", flush=True)
            return 2
        task, auto_class = tpl_result
        if not args.task_class:
            args.task_class = auto_class
        print(f"📋 Using template '{args.template}': {task}", flush=True)

    if args.suggest and not task:
        suggestion = suggest_task_from_git(repo_root, config)
        if suggestion:
            task, auto_class = suggestion
            if not args.task_class:
                args.task_class = auto_class
            print(f"💡 Suggested task: {task}", flush=True)
        else:
            print("warning: could not auto-suggest task from git status.", flush=True)

    if args.last:
        task = load_last_task(repo_root)
        if not task:
            print("error: no previous task in history. Run a task first.", flush=True)
            return 2
        print(f"🔄 Re-running last task: {task}", flush=True)

    if args.retry and not task:
        task = load_last_failed_task(repo_root)
        if not task:
            print("error: no failed task found in telemetry. Run a task that fails first.", flush=True)
            return 2
        print(f"🔁 Retrying last failed task: {task}", flush=True)

    if args.interactive or (not task and not args.batch and not args.suggest and not args.last and not args.retry):
        interactive_script = script_root() / "interactive.py"
        if interactive_script.exists():
            return subprocess.run([str(interactive_script), "--interactive"]).returncode
        else:
            print("error: interactive.py not found", flush=True)
            return 2

    if args.batch:
        return run_batch(
            args.batch, args.context_file, args.task_class, config, routing, repo_root,
            parallel=args.parallel,
        )

    # Save to history before running
    save_task_to_history(repo_root, task)

    rc = run_delegate(task, args.context_file, args.task_class, args.dry_run, args.print_envelope, config, routing, repo_root, show_cost=args.cost, timeout_override=args.timeout_override if args.timeout_override > 0 else None)

    if rc == 0 and not args.quick and not args.dry_run:
        print(f"\n✅ Task completed via Kimi wrapper. Run 'kd --stats' for telemetry.", flush=True)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

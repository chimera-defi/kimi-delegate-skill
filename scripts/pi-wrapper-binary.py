#!/usr/bin/env python3
"""Binary wrapper for pi — intercepts raw Kimi calls at the binary level.

Install: ln -sf $(pwd)/scripts/pi-wrapper-binary.py ~/.local/bin/pi
Requires: real pi binary available at /root/.local/bin/pi.real or via `which pi`

This wrapper is more robust than the bash shim because it works in:
- Non-interactive shells (scripts, CI)
- Subprocess calls from any language
- Environments where .bashrc is not sourced
"""
import os
import sys


def is_executable(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def is_inside_delegate() -> bool:
    """Detect if we're being called from within kimi-delegate (avoid recursion)."""
    if os.environ.get("KIMI_DELEGATE_ACTIVE"):
        return True
    try:
        # Check parent process tree for delegate.py or kimi-delegate.
        ppid = os.getppid()
        with open(f"/proc/{ppid}/cmdline", "rb") as f:
            parent_cmd = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        if "delegate.py" in parent_cmd or "kimi-delegate" in parent_cmd:
            return True
        # Check grandparent too (pi-kimi-subagent -> pi).
        with open(f"/proc/{ppid}/stat", "rb") as f:
            parts = f.read().split()
            grandparent = int(parts[3]) if len(parts) > 3 else 0
        if grandparent > 1:
            with open(f"/proc/{grandparent}/cmdline", "rb") as f:
                gp_cmd = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            if "delegate.py" in gp_cmd or "kimi-delegate" in gp_cmd:
                return True
    except Exception:
        pass
    return False


def find_real_pi() -> str:
    real_pi = os.environ.get("PI_REAL_BINARY", "")
    if is_executable(real_pi):
        return real_pi

    for candidate in ["/root/.local/bin/pi.real", "/usr/local/bin/pi", "/usr/bin/pi"]:
        if is_executable(candidate):
            return candidate

    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    our_dir = os.path.dirname(os.path.abspath(__file__))
    for directory in path_dirs:
        if directory == our_dir or directory == os.path.dirname(our_dir):
            continue
        candidate = os.path.join(directory, "pi")
        if is_executable(candidate):
            return candidate
    return ""


def find_real_pi_kimi_subagent() -> str:
    real_subagent = os.environ.get("PI_KIMI_SUBAGENT_REAL_BINARY", "")
    if is_executable(real_subagent):
        return real_subagent

    for candidate in [
        "/root/.local/bin/pi-kimi-subagent.real",
        "/usr/local/bin/pi-kimi-subagent",
        "/usr/bin/pi-kimi-subagent",
    ]:
        if is_executable(candidate):
            return candidate
    return ""


def resolve_kd() -> str:
    kd = os.environ.get("KIMI_DELEGATE_SCRIPT", "")
    if is_executable(kd):
        return kd

    for candidate in ["/root/.local/bin/kimi-delegate", "/usr/local/bin/kimi-delegate"]:
        if is_executable(candidate):
            return candidate

    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "delegate.py")


REAL_PI = find_real_pi()
REAL_PI_KIMI_SUBAGENT = find_real_pi_kimi_subagent()
INVOKED_AS_SUBAGENT = os.path.basename(sys.argv[0]) == "pi-kimi-subagent"

args = sys.argv[1:]
is_kimi = False
task_text = None

# Pattern: pi --provider kimi-coding ...
for i, arg in enumerate(args):
    if arg == "--provider" and i + 1 < len(args) and args[i + 1] == "kimi-coding":
        is_kimi = True
    if arg == "--print" and i + 1 < len(args):
        task_text = args[i + 1]

# Pattern: pi-kimi-subagent ...
if INVOKED_AS_SUBAGENT:
    is_kimi = True
    task_text = " ".join(args)

    # Map common health probes to delegate-native checks.
    if args and args[0] in {"--check", "--health"}:
        kd = resolve_kd()
        os.execvp(kd, [kd, "--check"])

    # Forward pure option invocations to the real subagent binary.
    # This avoids treating flags like `--check` as delegated task text.
    if args and all(arg.startswith("-") for arg in args):
        if REAL_PI_KIMI_SUBAGENT:
            os.execvp(REAL_PI_KIMI_SUBAGENT, [REAL_PI_KIMI_SUBAGENT] + args)
        sys.stderr.write("[kimi-delegate] Error: real pi-kimi-subagent binary not found.\n")
        sys.stderr.write("  Use `kd --check` for health checks or set PI_KIMI_SUBAGENT_REAL_BINARY.\n")
        sys.exit(2)

# Recursion guard: if we're inside the wrapper process tree, forward to real binary.
if is_inside_delegate():
    forward_bin = REAL_PI_KIMI_SUBAGENT if INVOKED_AS_SUBAGENT and REAL_PI_KIMI_SUBAGENT else REAL_PI
    if forward_bin:
        os.execvp(forward_bin, [forward_bin] + args)
    sys.stderr.write("[kimi-delegate] Error: real pi binary not found (recursion guard).\n")
    sys.exit(1)

if is_kimi:
    if not task_text:
        for arg in reversed(args):
            if not arg.startswith("-"):
                task_text = arg
                break

    # If still no task, read from stdin (handles: cat <<'EOF' | pi-kimi-subagent).
    if not task_text and not sys.stdin.isatty():
        task_text = sys.stdin.read()

    if task_text:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call -> routing through kd\n")
        task_text = task_text.strip('"\'').strip()
        kd = resolve_kd()
        # Use equals form so tasks that begin with dashes are treated as values.
        os.execvp(kd, [kd, f"--task={task_text}"])
    else:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call but could not extract task.\n")
        sys.stderr.write('  Usage: kd --task "..."\n')
        sys.exit(2)
else:
    if REAL_PI:
        os.execvp(REAL_PI, [REAL_PI] + args)
    else:
        sys.stderr.write("[kimi-delegate] Error: real pi binary not found.\n")
        sys.stderr.write("  Set PI_REAL_BINARY env var or ensure pi is in PATH.\n")
        sys.exit(1)

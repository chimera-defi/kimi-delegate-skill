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
import subprocess


def is_inside_delegate() -> bool:
    """Detect if we're being called from within kimi-delegate (avoid recursion)."""
    if os.environ.get("KIMI_DELEGATE_ACTIVE"):
        return True
    try:
        # Check parent process tree for delegate.py or kimi-delegate
        ppid = os.getppid()
        with open(f"/proc/{ppid}/cmdline", "rb") as f:
            parent_cmd = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        if "delegate.py" in parent_cmd or "kimi-delegate" in parent_cmd:
            return True
        # Check grandparent too (pi-kimi-subagent → pi)
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


# Find the real pi binary
REAL_PI = os.environ.get("PI_REAL_BINARY", "")
if not REAL_PI:
    for candidate in ["/root/.local/bin/pi.real", "/usr/local/bin/pi", "/usr/bin/pi"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            REAL_PI = candidate
            break

if not REAL_PI:
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    our_dir = os.path.dirname(os.path.abspath(__file__))
    for d in path_dirs:
        if d == our_dir or d == os.path.dirname(our_dir):
            continue
        candidate = os.path.join(d, "pi")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            REAL_PI = candidate
            break

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
if os.path.basename(sys.argv[0]) == "pi-kimi-subagent":
    is_kimi = True
    task_text = " ".join(args)

# Recursion guard: if we're inside the wrapper process tree, forward to real pi
if is_inside_delegate():
    if REAL_PI:
        os.execvp(REAL_PI, [REAL_PI] + args)
    else:
        sys.stderr.write("[kimi-delegate] Error: real pi binary not found (recursion guard).\n")
        sys.exit(1)

if is_kimi:
    if not task_text:
        for arg in reversed(args):
            if not arg.startswith("-"):
                task_text = arg
                break

    # If still no task, read from stdin (handles: cat <<'EOF' | pi-kimi-subagent)
    if not task_text and not sys.stdin.isatty():
        task_text = sys.stdin.read()

    if task_text:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call → routing through kd\n")
        task_text = task_text.strip('"\'').strip()

        kd = os.environ.get("KIMI_DELEGATE_SCRIPT", "")
        if not kd:
            for candidate in ["/root/.local/bin/kimi-delegate", "/usr/local/bin/kimi-delegate"]:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    kd = candidate
                    break

        if not kd:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            kd = os.path.join(script_dir, "delegate.py")

        os.execvp(kd, [kd, "--task", task_text])
    else:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call but could not extract task.\n")
        sys.stderr.write("  Usage: kd --task \"...\"\n")
        sys.exit(2)
else:
    if REAL_PI:
        os.execvp(REAL_PI, [REAL_PI] + args)
    else:
        sys.stderr.write("[kimi-delegate] Error: real pi binary not found.\n")
        sys.stderr.write("  Set PI_REAL_BINARY env var or ensure pi is in PATH.\n")
        sys.exit(1)

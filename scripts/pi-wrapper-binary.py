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

# Find the real pi binary
REAL_PI = os.environ.get("PI_REAL_BINARY", "")
if not REAL_PI:
    # Try common locations
    for candidate in ["/root/.local/bin/pi.real", "/usr/local/bin/pi", "/usr/bin/pi"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            REAL_PI = candidate
            break

if not REAL_PI:
    # Try to find pi in PATH, but skip ourselves
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    our_dir = os.path.dirname(os.path.abspath(__file__))
    for d in path_dirs:
        if d == our_dir or d == os.path.dirname(our_dir):
            continue
        candidate = os.path.join(d, "pi")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            REAL_PI = candidate
            break

# Check if this is a Kimi call
args = sys.argv[1:]
is_kimi = False
task_text = None
has_stdin = not sys.stdin.isatty()

# Pattern: pi --provider kimi-coding ...
for i, arg in enumerate(args):
    if arg == "--provider" and i + 1 < len(args) and args[i + 1] == "kimi-coding":
        is_kimi = True
    # Extract task from --print or last positional arg
    if arg == "--print" and i + 1 < len(args):
        task_text = args[i + 1]

# Pattern: pi-kimi-subagent ...
if os.path.basename(sys.argv[0]) == "pi-kimi-subagent":
    is_kimi = True
    task_text = " ".join(args)

if is_kimi:
    # Route through kimi-delegate
    if not task_text:
        # Try to find any quoted string or last positional arg
        for arg in reversed(args):
            if not arg.startswith("-"):
                task_text = arg
                break

    # If still no task, read from stdin (handles: cat <<'EOF' | pi-kimi-subagent)
    if not task_text and has_stdin:
        task_text = sys.stdin.read()

    if task_text:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call → routing through kd\n")
        # Strip surrounding quotes
        task_text = task_text.strip('"\'').strip()

        # Find kimi-delegate
        kd = os.environ.get("KIMI_DELEGATE_SCRIPT", "")
        if not kd:
            for candidate in ["/root/.local/bin/kimi-delegate", "/usr/local/bin/kimi-delegate"]:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    kd = candidate
                    break

        if not kd:
            # Fallback: run delegate.py directly
            script_dir = os.path.dirname(os.path.abspath(__file__))
            kd = os.path.join(script_dir, "delegate.py")

        # For stdin input, pipe it in
        if has_stdin:
            proc = subprocess.Popen([sys.executable, kd, "--task", task_text], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            sys.stdout.buffer.write(stdout)
            sys.stderr.buffer.write(stderr)
            sys.exit(proc.returncode)
        else:
            os.execvp(kd, [kd, "--task", task_text])
    else:
        sys.stderr.write("[kimi-delegate] Intercepted raw pi call but could not extract task.\n")
        sys.stderr.write("  Usage: kd --task \"...\"\n")
        sys.exit(2)
else:
    # Forward to real pi
    if REAL_PI:
        os.execvp(REAL_PI, [REAL_PI] + args)
    else:
        sys.stderr.write("[kimi-delegate] Error: real pi binary not found.\n")
        sys.stderr.write("  Set PI_REAL_BINARY env var or ensure pi is in PATH.\n")
        sys.exit(1)

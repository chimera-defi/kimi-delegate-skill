# kimi-delegate pi shim — intercept raw Kimi calls at the shell level
# Source this in your .bashrc or .zshrc: source "$HOME/.local/share/kimi-delegate-pi-shim.sh"

# Fallback: if kimi-delegate binary is broken, use direct path
_KD_DELEGATE_SCRIPT="${KIMI_DELEGATE_SCRIPT:-$HOME/.agents/skills/kimi-delegate/scripts/delegate.py}"

# Auto-detect repo scale and export PI_KIMI_TIMEOUT for non-intercepted calls
__kd_detect_repo_scale() {
    local repo_root
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
    if [[ -z "$repo_root" ]]; then
        return
    fi
    local mb
    mb=$(du -sm "$repo_root" 2>/dev/null | awk '{print $1}')
    if [[ -z "$mb" ]]; then
        return
    fi
    local current_timeout
    current_timeout="${PI_KIMI_TIMEOUT:-120s}"
    # Remove 's' suffix for comparison
    local current_sec="${current_timeout%s}"

    local target_sec
    if [[ "$mb" -ge 1000 ]]; then
        target_sec=360  # xlarge: 3x default
    elif [[ "$mb" -ge 500 ]]; then
        target_sec=240  # large: 2x default
    else
        target_sec=120  # normal
    fi

    # Only increase, never decrease
    if [[ "$target_sec" -gt "$current_sec" ]]; then
        export PI_KIMI_TIMEOUT="${target_sec}s"
    fi
}

# Run scale detection on shell startup and after every cd
__kd_detect_repo_scale

pi() {
    # Recursion guard: if we're already inside the wrapper, forward to real pi
    if [[ -n "${KIMI_DELEGATE_ACTIVE:-}" ]]; then
        command pi "$@"
        return $?
    fi

    # Check if this is a Kimi subagent call
    local is_kimi=false
    local task_arg=""
    local in_provider=false
    local provider_val=""
    local has_stdin=false

    for arg in "$@"; do
        if [[ "$in_provider" == true ]]; then
            provider_val="$arg"
            in_provider=false
            if [[ "$provider_val" == "kimi-coding" ]]; then
                is_kimi=true
            fi
        fi
        if [[ "$arg" == "--provider" ]]; then
            in_provider=true
        fi
    done

    # Also detect pi-kimi-subagent direct calls
    if [[ "$1" == "pi-kimi-subagent" || "$1" == *"/pi-kimi-subagent" ]]; then
        is_kimi=true
        shift
        task_arg="$*"
    fi

    # Also detect if the command itself is pi-kimi-subagent (not pi with --provider)
    if [[ "$(basename "$1" 2>/dev/null)" == "pi-kimi-subagent" ]]; then
        is_kimi=true
        shift
        task_arg="$*"
    fi

    if [[ "$is_kimi" == true ]]; then
        # Try to extract the actual prompt/task from the arguments
        if [[ -z "$task_arg" ]]; then
            # Look for quoted string or last positional arg
            for arg in "$@"; do
                if [[ "$arg" != --* && "$arg" != "pi" && "$arg" != "pi-kimi-subagent" ]]; then
                    task_arg="$arg"
                fi
            done
        fi

        # If still no task arg, read from stdin (handles: cat <<'EOF' | pi-kimi-subagent)
        if [[ -z "$task_arg" && ! -t 0 ]]; then
            task_arg=$(cat)
            has_stdin=true
        fi

        if [[ -n "$task_arg" ]]; then
            echo "[kimi-delegate] Intercepted raw pi call → routing through kd" >&2
            # Strip surrounding quotes if present
            task_arg="${task_arg%\"}"
            task_arg="${task_arg#\"}"
            task_arg="${task_arg%\'}"
            task_arg="${task_arg#\'}"
            if command -v kimi-delegate >/dev/null 2>&1; then
                if [[ "$has_stdin" == true ]]; then
                    echo "$task_arg" | kimi-delegate --task -
                else
                    kimi-delegate --task "$task_arg"
                fi
            else
                if [[ "$has_stdin" == true ]]; then
                    echo "$task_arg" | python3 "$_KD_DELEGATE_SCRIPT" --task -
                else
                    python3 "$_KD_DELEGATE_SCRIPT" --task "$task_arg"
                fi
            fi
            return $?
        else
            echo "[kimi-delegate] Intercepted raw pi call but could not extract task. Pass explicitly:" >&2
            echo "  kd --task \"...\"" >&2
            return 2
        fi
    fi

    # Not a Kimi call — forward to real pi binary
    command pi "$@"
}

# Also intercept pi-kimi-subagent if called directly
pi-kimi-subagent() {
    # Recursion guard: if we're already inside the wrapper, forward to real binary
    if [[ -n "${KIMI_DELEGATE_ACTIVE:-}" ]]; then
        command pi-kimi-subagent "$@"
        return $?
    fi

    echo "[kimi-delegate] Intercepted pi-kimi-subagent → routing through kd" >&2
    local task_arg="$*"
    local has_stdin=false

    # If no positional args, read from stdin
    if [[ -z "$task_arg" && ! -t 0 ]]; then
        task_arg=$(cat)
        has_stdin=true
    fi

    # Strip surrounding quotes
    task_arg="${task_arg%\"}"
    task_arg="${task_arg#\"}"
    task_arg="${task_arg%\'}"
    task_arg="${task_arg#\'}"
    if [[ -n "$task_arg" ]]; then
        if command -v kimi-delegate >/dev/null 2>&1; then
            if [[ "$has_stdin" == true ]]; then
                echo "$task_arg" | kimi-delegate --task -
            else
                kimi-delegate --task "$task_arg"
            fi
        else
            if [[ "$has_stdin" == true ]]; then
                echo "$task_arg" | python3 "$_KD_DELEGATE_SCRIPT" --task -
            else
                python3 "$_KD_DELEGATE_SCRIPT" --task "$task_arg"
            fi
        fi
    else
        echo "[kimi-delegate] No task provided. Usage: kd --task \"...\"" >&2
        return 2
    fi
}

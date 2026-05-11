# kimi-delegate pi shim — intercept raw Kimi calls at the shell level
# Source this in your .bashrc or .zshrc: source "$HOME/.local/share/kimi-delegate-pi-shim.sh"

# Fallback: if kimi-delegate binary is broken, use direct path
_KD_DELEGATE_SCRIPT="${KIMI_DELEGATE_SCRIPT:-$HOME/.agents/skills/kimi-delegate/scripts/delegate.py}"

pi() {
    # Check if this is a Kimi subagent call
    local is_kimi=false
    local task_arg=""
    local in_provider=false
    local provider_val=""

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
        # Extract task from --task flag
        if [[ "$arg" == --task=* ]]; then
            task_arg="${arg#*=}"
        elif [[ "$arg" == "--task" ]]; then
            : # next arg will be the task
        elif [[ -n "$task_arg" && "$arg" != --* && "$arg" != "--task" ]]; then
            # If we already saw --task but no =, this arg is the task value
            : # handled below
        fi
    done

    # Also detect pi-kimi-subagent direct calls
    if [[ "$1" == "pi-kimi-subagent" || "$1" == *"/pi-kimi-subagent" ]]; then
        is_kimi=true
        # The remaining args are the prompt
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

        if [[ -n "$task_arg" ]]; then
            echo "[kimi-delegate] Intercepted raw pi call → routing through kd" >&2
            # Strip surrounding quotes if present
            task_arg="${task_arg%\"}"
            task_arg="${task_arg#\"}"
            task_arg="${task_arg%\'}"
            task_arg="${task_arg#\'}"
            if command -v kimi-delegate >/dev/null 2>&1; then
                kimi-delegate --task "$task_arg"
            else
                python3 "$_KD_DELEGATE_SCRIPT" --task "$task_arg"
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
    echo "[kimi-delegate] Intercepted pi-kimi-subagent → routing through kd" >&2
    local task_arg="$*"
    # Strip surrounding quotes
    task_arg="${task_arg%\"}"
    task_arg="${task_arg#\"}"
    task_arg="${task_arg%\'}"
    task_arg="${task_arg#\'}"
    if [[ -n "$task_arg" ]]; then
        if command -v kimi-delegate >/dev/null 2>&1; then
            kimi-delegate --task "$task_arg"
        else
            python3 "$_KD_DELEGATE_SCRIPT" --task "$task_arg"
        fi
    else
        echo "[kimi-delegate] No task provided. Usage: kd --task \"...\"" >&2
        return 2
    fi
}

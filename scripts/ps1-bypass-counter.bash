# kimi-delegate PS1 bypass counter — show bypass rate in shell prompt
# Source this in your .bashrc or .zshrc after the pi shim.

__kd_bypass_count() {
    local count
    count=$(python3 -c "
import json, sys, os
from pathlib import Path

# Quick count of raw Kimi calls in last 24h for current repo
repo = Path.cwd()
workspace = Path('/root/.openclaw/workspace/dev')

# Find which workspace repo we're in
for p in [repo] + list(repo.parents):
    if (p / '.git').exists() and workspace in p.parents or p == workspace:
        repo = p
        break

# Count bypasses from telemetry
bypass_file = Path.home() / '.kimi-delegate' / 'telemetry' / 'bypass-daily.json'
if bypass_file.exists():
    data = json.loads(bypass_file.read_text())
    repo_slug = str(repo).replace('/', '-').replace('.', '-')
    print(data.get('bypasses_by_repo', {}).get(repo_slug, 0))
else:
    print(0)
" 2>/dev/null)
    echo "${count:-0}"
}

__kd_ps1_indicator() {
    local count
    count=$(__kd_bypass_count)
    if [ "$count" -gt 0 ]; then
        echo " [kd: ${count} bypass]"
    else
        echo " [kd: ✅]"
    fi
}

# Bash: update PS1
if [ -n "${BASH_VERSION:-}" ]; then
    # Only modify PS1 if it doesn't already contain kd indicator
    if [[ "${PS1:-}" != *'kd:'* ]]; then
        PS1='\u@\h:\w$(__kd_ps1_indicator)\$ '
    fi
fi

# Zsh: update PROMPT
if [ -n "${ZSH_VERSION:-}" ]; then
    if [[ "${PROMPT:-}" != *'kd:'* ]]; then
        setopt PROMPT_SUBST
        PROMPT='%n@%m:%~$(__kd_ps1_indicator)$ '
    fi
fi

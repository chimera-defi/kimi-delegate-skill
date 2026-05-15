#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR" "$HOME/.agents/skills" "$HOME/.openclaw/skills" "${CODEX_HOME:-$HOME/.codex}/skills"

ln -sfn "$SKILL_ROOT" "$HOME/.agents/skills/kimi-delegate"
ln -sfn "$HOME/.agents/skills/kimi-delegate" "$HOME/.openclaw/skills/kimi-delegate"
ln -sfn "$SKILL_ROOT" "${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"

# Ensure Takopi defaults align with this skill's intended provider/model.
if command -v takopi >/dev/null 2>&1; then
    takopi config set pi.provider kimi-coding >/dev/null 2>&1 || true
    takopi config set pi.model k2p6 >/dev/null 2>&1 || true
    echo "  takopi defaults set: pi.provider=kimi-coding, pi.model=k2p6"
fi

cat > "$BIN_DIR/kimi-delegate" <<WRAP
#!/usr/bin/env bash
exec "$SKILL_ROOT/scripts/delegate.py" "\$@"
WRAP
chmod +x "$BIN_DIR/kimi-delegate"

# Inject shell aliases for frictionless usage
SHELL_RC=""
if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "${BASH_VERSION:-}" ] || [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
    if ! grep -q "alias kd='kimi-delegate'" "$SHELL_RC" 2>/dev/null; then
        {
            echo ""
            echo "# kimi-delegate aliases"
            echo "alias kd='kimi-delegate'"
            echo "alias kd-check='kimi-delegate --check'"
            echo "alias kd-i='kimi-delegate --interactive'"
            echo "alias kd-stats='kimi-delegate --stats'"
            echo "alias kd-nudge='kimi-delegate-manage.sh session-nudge'"
            echo "alias kd-last='kimi-delegate --last'"
            echo "alias kd-history='kimi-delegate --history'"
            echo "alias kd-retry='kimi-delegate --retry'"
        } >> "$SHELL_RC"
        echo "  aliases added to $SHELL_RC: kd, kd-check, kd-i, kd-stats, kd-nudge, kd-last, kd-history, kd-retry"
    else
        echo "  aliases already present in $SHELL_RC"
    fi
    # Auto-nudge on shell startup (only for interactive shells)
    NUDGE_BLOCK='# kimi-delegate startup nudge\nif [[ $- == *i* ]]; then\n  nudge_out=$(kimi-delegate-manage.sh session-nudge --quiet 2>/dev/null)\n  if [ -n "$nudge_out" ]; then\n    echo "$nudge_out"\n  fi\nfi\n'
    if ! grep -q "kimi-delegate startup nudge" "$SHELL_RC" 2>/dev/null; then
        echo -e "\n$NUDGE_BLOCK" >> "$SHELL_RC"
        echo "  startup nudge added to $SHELL_RC"
    else
        echo "  startup nudge already present in $SHELL_RC"
    fi
fi

# Shell completion
cat > "$HOME/.local/share/kimi-delegate-completion.bash" <<'COMP'
_kimi_delegate_completions() {
    local cur prev opts
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="--task --context-file --task-class --dry-run --print-envelope --check --stats --interactive -i --batch --last --quick -q --cost --template --templates --suggest --history --retry --timeout-override --health --help"
    case "$prev" in
        --task-class)
            COMPREPLY=( $(compgen -W "search summarize review draft implementation-lite" -- "$cur") )
            return 0
            ;;
        --context-file|--batch)
            COMPREPLY=( $(compgen -f -- "$cur") )
            return 0
            ;;
    esac
    COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
}
complete -F _kimi_delegate_completions kimi-delegate
complete -F _kimi_delegate_completions kd
COMP

# Source completion in shell rc
if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
    COMP_LINE='source "$HOME/.local/share/kimi-delegate-completion.bash"'
    if ! grep -q "kimi-delegate-completion" "$SHELL_RC" 2>/dev/null; then
        echo -e "\n# kimi-delegate shell completion\n$COMP_LINE" >> "$SHELL_RC"
        echo "  shell completion added to $SHELL_RC"
    else
        echo "  shell completion already present in $SHELL_RC"
    fi
fi

# Install pi shim (intercepts raw pi --provider kimi-coding calls)
SHIM_SOURCE="$SKILL_ROOT/scripts/pi-shim.bash"
SHIM_TARGET="$HOME/.local/share/kimi-delegate-pi-shim.sh"
if [ -f "$SHIM_SOURCE" ]; then
    mkdir -p "$(dirname "$SHIM_TARGET")"
    cp "$SHIM_SOURCE" "$SHIM_TARGET"
    if [ -n "$SHELL_RC" ] && [ -f "$SHELL_RC" ]; then
        SHIM_LINE='source "$HOME/.local/share/kimi-delegate-pi-shim.sh"'
        if ! grep -q "kimi-delegate-pi-shim" "$SHELL_RC" 2>/dev/null; then
            echo -e "\n# kimi-delegate pi shim (intercepts raw Kimi calls)\n$SHIM_LINE" >> "$SHELL_RC"
            echo "  pi shim added to $SHELL_RC"
        else
            echo "  pi shim already present in $SHELL_RC"
        fi
    fi
    echo "  shim:    $SHIM_TARGET"
fi

# Install binary wrapper (works in non-interactive shells where .bashrc isn't sourced)
WRAPPER_SOURCE="$SKILL_ROOT/scripts/pi-wrapper-binary.py"
WRAPPER_TARGET="$BIN_DIR/pi"
if [ -f "$WRAPPER_SOURCE" ]; then
    if [ -f "$WRAPPER_TARGET" ] && ! grep -q "kimi-delegate" "$WRAPPER_TARGET" 2>/dev/null; then
        # Real pi binary exists — back it up and install wrapper in its place
        mv "$WRAPPER_TARGET" "$WRAPPER_TARGET.real"
        echo "  backed up real pi → $WRAPPER_TARGET.real"
    fi
    cp "$WRAPPER_SOURCE" "$WRAPPER_TARGET"
    chmod +x "$WRAPPER_TARGET"
    echo "  binary wrapper: $WRAPPER_TARGET (intercepts pi --provider kimi-coding)"

    # Also intercept direct pi-kimi-subagent calls (common in Codex sessions)
    SUBAGENT_TARGET="$BIN_DIR/pi-kimi-subagent"
    if [ -f "$SUBAGENT_TARGET" ] && ! grep -q "kimi-delegate" "$SUBAGENT_TARGET" 2>/dev/null; then
        mv "$SUBAGENT_TARGET" "$SUBAGENT_TARGET.real"
        echo "  backed up real pi-kimi-subagent → $SUBAGENT_TARGET.real"
    fi
    ln -sf "$WRAPPER_TARGET" "$SUBAGENT_TARGET"
    echo "  subagent wrapper: $SUBAGENT_TARGET → $WRAPPER_TARGET"
fi

echo "kimi-delegate installed"
echo "  agents:  $HOME/.agents/skills/kimi-delegate"
echo "  openclaw:$HOME/.openclaw/skills/kimi-delegate"
echo "  codex:   ${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"
echo "  bin:     $BIN_DIR/kimi-delegate"
echo "  completion: $HOME/.local/share/kimi-delegate-completion.bash"
echo "  shim:    $HOME/.local/share/kimi-delegate-pi-shim.sh"
echo "  wrapper: $BIN_DIR/pi (binary-level interception)"

if ! command -v kimi-delegate >/dev/null 2>&1; then
  echo "warning: $BIN_DIR is not on PATH. Add 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your shell rc."
fi

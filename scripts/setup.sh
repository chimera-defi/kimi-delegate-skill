#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR" "$HOME/.agents/skills" "$HOME/.openclaw/skills" "${CODEX_HOME:-$HOME/.codex}/skills"

ln -sfn "$SKILL_ROOT" "$HOME/.agents/skills/kimi-delegate"
ln -sfn "$HOME/.agents/skills/kimi-delegate" "$HOME/.openclaw/skills/kimi-delegate"
ln -sfn "$SKILL_ROOT" "${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"

cat > "$BIN_DIR/kimi-delegate" <<'WRAP'
#!/usr/bin/env bash
exec "$SKILL_ROOT/scripts/delegate.py" "$@"
WRAP
chmod +x "$BIN_DIR/kimi-delegate"

# Inject shell aliases for frictionless usage
SHELL_RC=""
if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
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
        } >> "$SHELL_RC"
        echo "  aliases added to $SHELL_RC: kd, kd-check"
    else
        echo "  aliases already present in $SHELL_RC"
    fi
fi

echo "kimi-delegate installed"
echo "  agents:  $HOME/.agents/skills/kimi-delegate"
echo "  openclaw:$HOME/.openclaw/skills/kimi-delegate"
echo "  codex:   ${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"
echo "  bin:     $BIN_DIR/kimi-delegate"

if ! command -v kimi-delegate >/dev/null 2>&1; then
  echo "warning: $BIN_DIR is not on PATH. Add 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your shell rc."
fi

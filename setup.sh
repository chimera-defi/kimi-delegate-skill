#!/usr/bin/env bash
# Root-level shim: delegates to scripts/setup.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/setup.sh" "$@"

#!/usr/bin/env python3
"""Install pre-commit hooks across workspace repos to block commits when bypasses detected."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from repo_scan import iter_workspace_repos

HOOK_NAME = "pre-commit"
HOOK_MARKER = "# kimi-delegate bypass gate"


def hook_script(skill_root: str) -> str:
    """Return the pre-commit hook script content."""
    return f"""#!/usr/bin/env bash
{HOOK_MARKER}
# Blocks commits if raw Kimi calls bypassing the wrapper were detected in this repo.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
SKILL_ROOT="{skill_root}"
BYPASS_OUT=$("$SKILL_ROOT/scripts/detect_bypass.py" --repo "$REPO_ROOT" --days 1 --nudge 2>&1)
BYPASS_COUNT=$(echo "$BYPASS_OUT" | grep -oP 'Raw Kimi calls.*?: \\K[0-9]+' || echo "0")

if [ "$BYPASS_COUNT" -gt 0 ]; then
    echo ""
    echo "❌ COMMIT BLOCKED by kimi-delegate bypass gate"
    echo ""
    echo "$BYPASS_OUT"
    echo ""
    echo "Fix: re-run your tasks through the wrapper before committing:"
    echo "  kd --task \"...\""
    echo ""
    echo "To bypass this check (not recommended):"
    echo "  git commit --no-verify"
    exit 1
fi

exit 0
"""


def resolve_hooks_dir(repo_path: Path) -> Path | None:
    """Resolve the active hooks directory for a repo/worktree.

    Uses `git rev-parse --git-path hooks` so custom `core.hooksPath`
    and worktree setups are handled correctly.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_path / path).resolve()
    return path


def install_hook(repo_path: Path, skill_root: Path, dry_run: bool = False) -> dict:
    """Install pre-commit hook into a single repo."""
    hooks_dir = resolve_hooks_dir(repo_path)
    if hooks_dir is None:
        return {"repo": str(repo_path), "status": "no_git", "action": "skipped"}

    hook_path = hooks_dir / HOOK_NAME
    existing = hook_path.read_text(encoding="utf-8", errors="ignore") if hook_path.exists() else ""

    if HOOK_MARKER in existing:
        return {
            "repo": str(repo_path),
            "status": "already_installed",
            "action": "skipped",
            "hook_path": str(hook_path),
        }

    if dry_run:
        return {
            "repo": str(repo_path),
            "status": "would_install",
            "action": "dry_run",
            "hook_path": str(hook_path),
        }

    hooks_dir.mkdir(parents=True, exist_ok=True)

    new_hook = hook_script(str(skill_root))
    if existing:
        # Append after existing hook content
        new_hook = existing.rstrip("\n") + "\n\n" + new_hook

    hook_path.write_text(new_hook, encoding="utf-8")
    hook_path.chmod(0o755)
    return {
        "repo": str(repo_path),
        "status": "installed",
        "action": "installed",
        "hook_path": str(hook_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install kimi-delegate pre-commit hooks")
    parser.add_argument("--workspace-root", default=os.environ.get("KIMI_DELEGATE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", help="JSON output path")
    args = parser.parse_args()

    skill_root = Path(__file__).parent.parent.resolve()
    results = []

    for repo in iter_workspace_repos(Path(args.workspace_root)):
        result = install_hook(repo, skill_root, dry_run=args.dry_run)
        results.append(result)

    report = {
        "installed": sum(1 for r in results if r["action"] == "installed"),
        "already_installed": sum(1 for r in results if r["action"] == "skipped" and r["status"] == "already_installed"),
        "skipped_no_git": sum(1 for r in results if r["status"] == "no_git"),
        "dry_run": sum(1 for r in results if r["action"] == "dry_run"),
        "total": len(results),
        "results": results,
    }

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

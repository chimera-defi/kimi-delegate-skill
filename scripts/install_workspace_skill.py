#!/usr/bin/env python3
"""Install kimi-delegate into workspace repos and inject routing instructions."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from repo_scan import iter_workspace_repos, repo_label
except ModuleNotFoundError:  # pragma: no cover
    import sys

    sys.path.append(str(Path(__file__).resolve().parent))
    from repo_scan import iter_workspace_repos, repo_label


BLOCK_START = "<!-- kimi-delegate:begin -->"
BLOCK_END = "<!-- kimi-delegate:end -->"
KIMI_BLOCK = f"""{BLOCK_START}
## Kimi Delegate Routing — MANDATORY

All Kimi subagent calls MUST route through the skill wrapper. Direct `pi --provider kimi-coding` calls are **prohibited** — they bypass telemetry, fallback, auth detection, and timeout scaling.

- **One-liner:** `kimi-delegate --task "..."`
- **Interactive:** `kimi-delegate --interactive`
- **Long path (fallback):** `./skills/kimi-delegate/scripts/delegate.py --task "..."`

**Why this matters:**
- Structured envelopes prevent vague handoffs
- Auto-scaling timeouts prevent hangs on large repos
- Auth error detection gives explicit resume steps instead of silent failures
- Codex fallback ensures tasks always complete
- Telemetry enables continuous improvement

**Bypassing the wrapper will be detected and reported.**

- Always produce an envelope first with `./skills/kimi-delegate/scripts/plan_prompt.py --task "..."`.
- Keep delegation scoped and include acceptance criteria.
- If Kimi fails, keep fallback enabled and inspect telemetry (`./skills/kimi-delegate/scripts/kimi_delegate_telemetry.py summary --days 14`).
{BLOCK_END}
"""
BLOCK_RE = re.compile(rf"{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}", re.DOTALL)

CLAUDE_BLOCK_START = "<!-- kimi-delegate-claude:begin -->"
CLAUDE_BLOCK_END = "<!-- kimi-delegate-claude:end -->"
CLAUDE_BLOCK = f"""{CLAUDE_BLOCK_START}
## Kimi Delegation (enforced)

NEVER write `pi --provider kimi-coding`. Always use `kd --task "..."` instead.

Wrong: `pi --provider kimi-coding "summarize this"`
Right: `kd --task "summarize this"`

The wrapper handles auth, timeouts, fallback, and telemetry automatically.
{CLAUDE_BLOCK_END}
"""
CLAUDE_BLOCK_RE = re.compile(rf"{re.escape(CLAUDE_BLOCK_START)}.*?{re.escape(CLAUDE_BLOCK_END)}", re.DOTALL)


@dataclass
class RepoInstallResult:
    repo: str
    skill_link: str
    doc_file: str
    doc_action: str
    claude_action: str
    changed: bool


def ensure_skill_link(repo: Path, skill_source: Path, force_relink: bool, dry_run: bool) -> tuple[str, bool]:
    skills_dir = repo / "skills"
    target = skills_dir / "kimi-delegate"

    if target.is_symlink() and target.exists() and target.resolve() == skill_source.resolve():
        return "already-linked", False

    if target.exists() or target.is_symlink():
        if not force_relink:
            return "conflict-existing-path", False
        if not dry_run:
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
            else:
                shutil.rmtree(target)

    if not dry_run:
        skills_dir.mkdir(parents=True, exist_ok=True)
        target.symlink_to(skill_source)
    return "linked", True


def target_doc(repo: Path) -> Path:
    agents = repo / "AGENTS.md"
    if agents.exists():
        return agents
    claude = repo / "CLAUDE.md"
    if claude.exists():
        return claude
    return agents


def ensure_doc_block(path: Path, dry_run: bool) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    block = KIMI_BLOCK.strip()

    if BLOCK_RE.search(text):
        updated = BLOCK_RE.sub(block, text)
        changed = updated != text
        if changed and not dry_run:
            path.write_text(updated.rstrip() + "\n", encoding="utf-8")
        return "block-replaced", changed

    if text.strip():
        updated = text.rstrip() + "\n\n" + block + "\n"
        action = "block-added"
    else:
        updated = "# Agent Instructions\n\n" + block + "\n"
        action = "file-created"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action, True


def ensure_claude_md_block(repo: Path, dry_run: bool) -> tuple[str, bool]:
    """Inject short enforcement rule into CLAUDE.md (system prompt, not just AGENTS.md)."""
    claude_md = repo / "CLAUDE.md"
    if not claude_md.exists():
        return "no-claude-md", False

    text = claude_md.read_text(encoding="utf-8", errors="ignore")
    block = CLAUDE_BLOCK.strip()

    if CLAUDE_BLOCK_RE.search(text):
        updated = CLAUDE_BLOCK_RE.sub(block, text)
        changed = updated != text
        if changed and not dry_run:
            claude_md.write_text(updated.rstrip() + "\n", encoding="utf-8")
        return "claude-block-replaced", changed

    # Append to existing CLAUDE.md
    updated = text.rstrip() + "\n\n" + block + "\n"
    if not dry_run:
        claude_md.write_text(updated, encoding="utf-8")
    return "claude-block-added", True


def install_workspace(
    workspace_root: Path,
    skill_source: Path,
    include_self: bool,
    include_worktrees: bool,
    force_relink: bool,
    dry_run: bool,
) -> dict:
    rows: list[RepoInstallResult] = []
    source = skill_source.resolve()

    for repo in iter_workspace_repos(workspace_root, include_worktrees=include_worktrees):
        if not include_self and repo.resolve() == source:
            continue
        link_action, link_changed = ensure_skill_link(repo, source, force_relink, dry_run)
        doc = target_doc(repo)
        doc_action, doc_changed = ensure_doc_block(doc, dry_run)
        claude_action, claude_changed = ensure_claude_md_block(repo, dry_run)
        rows.append(
            RepoInstallResult(
                repo=repo_label(repo, workspace_root),
                skill_link=link_action,
                doc_file=doc.name,
                doc_action=doc_action,
                claude_action=claude_action,
                changed=bool(link_changed or doc_changed or claude_changed),
            )
        )

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "skill_source": str(source),
        "repo_count": len(rows),
        "repos_changed": sum(1 for row in rows if row.changed),
        "dry_run": dry_run,
        "results": [asdict(row) for row in rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default=os.environ.get("KIMI_DELEGATE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"))
    parser.add_argument("--skill-source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--no-worktrees", action="store_true")
    parser.add_argument("--force-relink", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = install_workspace(
        workspace_root=Path(args.workspace_root).resolve(),
        skill_source=Path(args.skill_source).resolve(),
        include_self=args.include_self,
        include_worktrees=not args.no_worktrees,
        force_relink=args.force_relink,
        dry_run=args.dry_run,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

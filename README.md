# kimi-delegate-skill

Reusable delegation skill for planning with a stronger orchestrator and executing scoped subtasks with cheaper Kimi workers.

## What this ships

- Structured delegation envelopes (`prompts/plan.md`, `scripts/plan_prompt.py`)
- Kimi execution runner with Codex-first fallback (`scripts/delegate.py`, `scripts/fallback.py`)
- Local telemetry loop (`scripts/kimi_delegate_telemetry.py`)
- Workspace propagation tooling (`scripts/install_workspace_skill.py`, `scripts/audit_workspace_skills.py`)

## Quick start

```bash
./scripts/setup.sh
./scripts/plan_prompt.py --task "summarize this PR risk"
./scripts/delegate.py --task "summarize this PR risk"
./scripts/delegate.py --check --task "ping"              # pre-flight env check
./scripts/env_check.py --repo-root .                      # detailed env + repo scale
./scripts/install_workspace_skill.py --workspace-root /root/.openclaw/workspace/dev
./scripts/audit_workspace_skills.py --workspace-root /root/.openclaw/workspace/dev
./scripts/kimi_delegate_telemetry.py summary --days 14
./scripts/audit_workspace_usage.py --days 14
./scripts/kimi-delegate-manage.sh workspace-sync
```

`audit_workspace_usage.py` measures adoption from Claude project sessions (`~/.claude/projects`), Codex rollout sessions (`~/.codex/sessions`), and repo-local telemetry events.

## Shorthand

If `setup.sh` has been run, `kimi-delegate` is available on PATH:

```bash
kimi-delegate --task "summarize this failing CI log"
kimi-delegate --check --task "ping"
```

## Smart timeout scaling

For large repos (≥10k files or ≥500MB), timeouts auto-scale 2×. For xlarge repos (≥50k files or ≥1GB), 3×. Configurable in `config/kimi-delegate.json`.

## Auth error handling

If Kimi returns an auth/session error, the skill prints explicit resume steps instead of silently falling back to Codex. This preserves the user's intent to use the cheaper model.

## Routing defaults

See `config/routing.json` and `config/kimi-delegate.json`.

## References

- Skill propagation process: `references/skill-propagation-process.md`
- Token-reduce integration target: `token-reduce-skill` companion-tool workflow

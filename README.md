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
./scripts/kimi_delegate_telemetry.py summary --days 14
```

## Routing defaults

See `config/routing.json` and `config/kimi-delegate.json`.

## References

- Skill propagation process: `references/skill-propagation-process.md`
- Token-reduce integration target: `token-reduce-skill` companion-tool workflow

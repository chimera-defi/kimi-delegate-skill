# kimi-delegate-skill

Reusable delegation skill for planning with a stronger orchestrator and executing scoped subtasks with cheaper Kimi workers.

## What this ships

- Structured delegation envelopes (`prompts/plan.md`, `scripts/plan_prompt.py`)
- Kimi execution runner with Codex-first fallback (`scripts/delegate.py`, `scripts/fallback.py`)
- Local telemetry loop (`scripts/kimi_delegate_telemetry.py`)
- Workspace propagation tooling (`scripts/install_workspace_skill.py`, `scripts/audit_workspace_skills.py`)
- **Bypass detection** (`scripts/detect_bypass.py`) — scans session logs for raw Kimi calls that route around the wrapper
- **Timeout tuning** (`scripts/tune_timeouts.py`) — analyzes telemetry to suggest threshold adjustments
- **Environment check** (`scripts/env_check.py`) — pre-flight auth + repo scale verification

## Quick start

```bash
./scripts/setup.sh
./scripts/plan_prompt.py --task "summarize this PR risk"
./scripts/delegate.py --task "summarize this PR risk"
./scripts/delegate.py --check --task "ping"              # pre-flight env check
./scripts/env_check.py --repo-root .                      # detailed env + repo scale
./scripts/detect_bypass.py --days 7 --nudge                # find raw Kimi calls bypassing wrapper
./scripts/tune_timeouts.py --days 14                      # analyze telemetry for threshold tuning
./scripts/install_workspace_skill.py --workspace-root /root/.openclaw/workspace/dev
./scripts/audit_workspace_skills.py --workspace-root /root/.openclaw/workspace/dev
./scripts/kimi_delegate_telemetry.py summary --days 14
./scripts/audit_workspace_usage.py --days 14
./scripts/kimi-delegate-manage.sh workspace-sync
```

`setup.sh` also sets Takopi defaults to `pi.provider=kimi-coding` and `pi.model=k2p6` when `takopi` is installed.

`audit_workspace_usage.py` measures adoption from Claude project sessions (`~/.claude/projects`), Codex rollout sessions (`~/.codex/sessions`), and repo-local telemetry events. It also tracks **bypass rate** — raw Kimi calls that route around the skill wrapper.

## Shorthand

If `setup.sh` has been run, `kimi-delegate` is available on PATH with shell aliases:

```bash
kimi-delegate --task "summarize this failing CI log"
kd --task "summarize this failing CI log"        # alias (after setup.sh)
kd-check --task "ping"                           # alias for --check
```

## Quick reference

| Alias | Command | Purpose |
|---|---|---|
| `kd` | `kimi-delegate` | One-liner delegation |
| `kd-check` | `kimi-delegate --check` | Pre-flight env check |
| `kd-i` | `kimi-delegate --interactive` | Interactive envelope builder |
| `kd-stats` | `kimi-delegate --stats` | Inline telemetry summary |
| `kd-nudge` | `kimi-delegate-manage.sh session-nudge` | Print bypass nudge |

## Per-repo config overrides

Create `.kimi-delegate.json` in your repo root to override global settings:

```json
{
  "large_repo_timeout_multiplier": 2.5,
  "xlarge_repo_timeout_multiplier": 4.0,
  "timeout_seconds": 180,
  "max_retries": 2
}
```

See `config/.kimi-delegate.json.example` for the full template.

## Smart timeout scaling

For large repos (≥10k files or ≥500MB), timeouts auto-scale 2×. For xlarge repos (≥50k files or ≥1GB), 3×. Configurable in `config/kimi-delegate.json`.

## Auth error handling

If Kimi returns an auth/session error, the skill prints explicit resume steps instead of silently falling back to Codex. Exit code 126.

## Bypass detection

`detect_bypass.py` scans agent session logs and reports how many Kimi calls bypassed the wrapper:

```bash
./scripts/detect_bypass.py --days 7 --nudge
```

## Routing defaults

See `config/routing.json` and `config/kimi-delegate.json`.

## References

- Skill propagation process: `references/skill-propagation-process.md`
- Token-reduce integration target: `token-reduce-skill` companion-tool workflow
# pre-commit hook test

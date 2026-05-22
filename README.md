# kimi-delegate

Route bounded Kimi subagent tasks through a structured envelope with auto-scaling timeouts, Codex fallback, telemetry, and bypass detection.

## What problem this solves

You want cheaper Kimi subagents for scoped work (search, summarize, draft), but:
- Direct `pi --provider kimi-coding` calls bypass telemetry and fallback routing
- Kimi times out on large repos (2.5GB, 80k files)
- Auth/session expiry kills the subagent silently
- You don't know how often your agents are routing around the wrapper

**This skill fixes all of that.** One command, structured handoff, fallback if Kimi fails, data on what's actually happening.

## Prerequisites

- `pi` CLI (for Kimi subagent)
- `codex` CLI (for fallback)
- `python3`
- `git`

## Quick start

```bash
# 1. Install
./scripts/setup.sh

# 2. Verify
kimi-delegate --check --task "ping"

# 3. Run
kimi-delegate --task "summarize this failing CI log"
```

That's it. `setup.sh` installs `kimi-delegate` to `~/.local/bin`, adds `kd` alias, links the skill into Codex/Claude repos, and wraps `pi`/`pi-kimi-subagent` so raw Kimi calls are detected.

## Commands

| Command | What it does |
|---|---|
| `kimi-delegate --task "..."` | Run a scoped task through Kimi with Codex fallback |
| `kimi-delegate --check --task "..."` | Pre-flight check: binaries, auth, repo scale |
| `kimi-delegate --interactive` | Build an envelope interactively |
| `kimi-delegate-manage.sh workspace-sync` | Install skill + routing blocks across all workspace repos |
| `kimi-delegate-manage.sh bypass --days 7` | Detect raw Kimi calls that bypassed the wrapper |
| `kimi-delegate-manage.sh telemetry --days 14` | Summary: success rate, fallback rate, auth errors, bypass rate |

## Aliases (after setup.sh)

| Alias | Command |
|---|---|
| `kd` | `kimi-delegate` |
| `kd-check` | `kimi-delegate --check` |
| `kd-i` | `kimi-delegate --interactive` |
| `kd-stats` | `kimi-delegate --stats` |
| `kd-nudge` | `kimi-delegate-manage.sh session-nudge` |

## How it works

1. **Envelope** — `plan_prompt.py` builds a structured task envelope from your description
2. **Run** — `delegate.py` calls Kimi with auto-scaled timeouts by repo size (2× for large, 3× for xlarge)
3. **Fallback** — if Kimi times out or errors, automatic Codex fallback (unless auth error → exit 126 with resume steps)
4. **Telemetry** — every run writes to `events.jsonl` and `history.jsonl` (rotated at 10MB)
5. **Bypass detection** — `detect_bypass.py` scans `~/.claude/projects` and `~/.codex/sessions` for raw `pi --provider kimi-coding` calls

## Repo-level routing block

Every workspace repo gets this in `AGENTS.md`/`CLAUDE.md`:

```markdown
<!-- kimi-delegate:begin -->
All Kimi subagent calls MUST route through the skill wrapper.
Direct `pi --provider kimi-coding` calls bypass telemetry and fallback.
Use: `kimi-delegate --task "..."` or `./skills/kimi-delegate/scripts/delegate.py`
<!-- kimi-delegate:end -->
```

Install across workspace:
```bash
./scripts/kimi-delegate-manage.sh workspace-sync
```

## Per-repo overrides

Create `.kimi-delegate.json` in repo root:

```json
{
  "timeout_seconds": 180,
  "max_retries": 2,
  "large_repo_timeout_multiplier": 2.5,
  "xlarge_repo_timeout_multiplier": 4.0
}
```

See `config/.kimi-delegate.json.example`.

## Pre-commit bypass gate

`workspace-sync` installs a pre-commit hook that blocks commits if the repo's Kimi bypass rate exceeds 20% in the last 24 hours. This forces developers to use the wrapper.

## Troubleshooting

**"pi finished without an agent_end event"**
- Structured pi stream calls (`--mode json` + `--session`) pass through unchanged
- Wrapper only intercepts raw/direct Kimi calls
- Telemetry records `provider_warnings=["agent_end_missing"]` if a delegated run shows this

**Push to protected branch fails**
- `Etc-mono-repo` uses branch protection on `main` — open a PR instead of direct push
- Other repos push directly; the skill auto-detects and uses PRs when needed

## References

- Skill propagation: `references/skill-propagation-process.md`
- Meta learnings: `references/meta-learnings-2026-05-19.md`
- Companion: `token-reduce-skill` (token reduction for large repo queries)

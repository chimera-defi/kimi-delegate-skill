# kimi-delegate

Route Kimi subagent tasks through structured envelopes with auto-scaling timeouts, Codex fallback, telemetry, and bypass detection.

## Why This Matters

Direct `pi --provider kimi-coding` calls bypass telemetry, fallback routing, and timeout scaling. Kimi times out on large repos, auth expiry kills subagents silently, and you lose visibility into agent behavior. This skill fixes all of that with one command.

## Prerequisites

- `pi` CLI (for Kimi subagent)
- `codex` CLI (for fallback)
- `python3`
- `git`

## Quick Start

```bash
./scripts/setup.sh
kimi-delegate --task "summarize this failing CI log"
```

`setup.sh` installs to `~/.local/bin`, adds `kd` alias, and wraps `pi` to detect bypasses.

## Commands

| Command | Purpose |
|---------|---------|
| `kimi-delegate --task "..."` | Run task through Kimi with Codex fallback |
| `kimi-delegate --check` | Pre-flight check: binaries, auth, repo scale |
| `kimi-delegate --interactive` | Build envelope interactively |
| `kimi-delegate --stats` | 14-day usage summary: calls, fallback rate, tokens saved |
| `kimi-delegate --dry-run "..."` | Build envelope without executing |
| `kimi-delegate --batch tasks.jsonl` | Process tasks from JSONL file |
| `kimi-delegate --suggest` | Auto-suggest a task from git status |
| `kimi-delegate --history` | Show recent task history |
| `kimi-delegate --retry` | Retry the last failed task |
| `kimi-delegate --last` | Re-run the previous task |
| `kimi-delegate --health` | Quick health check and exit |
| `kimi-delegate-manage.sh workspace-sync` | Install routing blocks across workspace repos |
| `kimi-delegate-manage.sh bypass --days 7` | Detect raw Kimi calls bypassing wrapper |
| `kimi-delegate-manage.sh telemetry --days 14` | Success rate, fallback rate, bypass rate |

## CLI Reference

| Flag | Description |
|------|-------------|
| `TASK` (positional) | Task description (positional, or use `--task`) |
| `--task TEXT` | Task description (flag form) |
| `--task-class TEXT` | `research`, `implement`, `debug`, `review`, `browser` |
| `--context-file PATH` | Load additional context from a file |
| `--timeout-override SEC` | Override the computed timeout (seconds) |
| `--dry-run` | Build envelope without executing |
| `--print-envelope` | Print the envelope JSON and exit |
| `--check` | Pre-flight env check only (binaries, auth, repo scale) |
| `--health` | Quick health check and exit |
| `--stats` | Print recent telemetry summary |
| `--history` | Show recent task history |
| `--last` | Re-run the previous task from history |
| `--retry` | Retry the last failed task |
| `--suggest` | Auto-suggest a task from git status |
| `--interactive`, `-i` | Interactive envelope builder |
| `--quick`, `-q` | Quick mode: suppress extra output |
| `--cost` | Show estimated cost/savings after run |
| `--repo-scale` | Show repo scale and computed timeout, then exit |
| `--template NAME` | Use a named task template |
| `--templates` | List available templates |
| `--batch PATH` | Path to JSONL file of tasks to delegate in batch |
| `--parallel N` | Max concurrent tasks in batch mode (default 1, cap 3) |

## Aliases

| Alias | Command |
|-------|---------|
| `kd` | `kimi-delegate` |
| `kd-check` | `kimi-delegate --check` |
| `kd-i` | `kimi-delegate --interactive` |
| `kd-stats` | `kimi-delegate --stats` |
| `kd-nudge` | `kimi-delegate-manage.sh session-nudge` |

## How It Works

1. **Envelope** — `plan_prompt.py` builds structured task envelope from your description
2. **Run** — `delegate.py` calls Kimi with auto-scaled timeouts (2× large, 3× xlarge repos)
3. **Fallback** — Automatic Codex fallback on timeout/error (auth errors exit 126 with resume steps)
4. **Telemetry** — Every run to `events.jsonl` / `history.jsonl` (rotated at 10MB)
5. **Bypass detection** — `detect_bypass.py` scans for raw `pi --provider kimi-coding` calls

## Repo Routing Block

Every workspace repo gets this in `AGENTS.md`/`CLAUDE.md`:

```markdown
<!-- kimi-delegate:begin -->
Kimi subagent calls MUST route through the skill wrapper.
Direct `pi --provider kimi-coding` calls bypass telemetry and fallback.
Use: `kimi-delegate --task "..."` or `./skills/kimi-delegate/scripts/delegate.py`
<!-- kimi-delegate:end -->
```

Install across workspace:
```bash
./scripts/kimi-delegate-manage.sh workspace-sync
```

## Per-Repo Overrides

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

## Pre-Commit Bypass Gate

Pre-commit hook blocks commits if bypass rate exceeds 20% in 24h, forcing wrapper usage.

## Troubleshooting

**"pi finished without an agent_end event"** — Structured pi stream calls pass through unchanged. Wrapper only intercepts raw Kimi calls. Telemetry records this as `provider_warnings=["agent_end_missing"]`.

**Push to protected branch fails** — Open a PR instead of direct push.

## References

- Skill propagation: `references/skill-propagation-process.md`
- Meta learnings: `references/meta-learnings-2026-05-19.md`
- Companion: `token-reduce-skill` (token reduction for large repo queries)

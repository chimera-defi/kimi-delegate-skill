---
name: kimi-delegate
preamble-tier: 4
version: 0.3.9
description: |
  Route bounded coding subtasks through a cheap Kimi subagent using a structured delegation envelope,
  fallback routing, and telemetry for continuous improvement.
triggers:
  - delegate to Kimi
  - kimi-delegate
  - cheap bounded subagent
  - cheap research or review subtask
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Kimi Delegate Skill

## When to Use

- Delegate bounded subtasks to cheaper Kimi worker
- Reduce parent-agent token usage for search/summarize/draft/check
- Need telemetry on delegation quality and fallback rates
- **NEVER** call `pi --provider kimi-coding` directly — bypasses envelope, fallback, telemetry

## When to Skip

- Tiny local edits (delegation overhead > direct execution)
- Full-repo/global reasoning without clean scope boundaries
- Tasks with secrets that cannot leave local execution boundary

## First Move

```bash
# Pre-flight check (recommended)
./scripts/delegate.py --check --task "..."

# Build envelope
./scripts/plan_prompt.py --task "..."

# Delegate
./scripts/delegate.py --task "..." --context-file /tmp/context.txt
```

## Process

1. Classify task: `search`, `summarize`, `draft`, `review`, `implementation-lite`
2. Build envelope JSON: goal, scope, constraints, acceptance checks, output schema
3. Auto-scale timeout by repo size (large 2×, xlarge 3×)
4. Execute with Kimi using budgets from `config/routing.json`
5. Validate schema; retry once if invalid
6. Auth/session errors → emit resume steps (exit 126), no blind fallback
7. Other failures → Codex fallback
8. Record telemetry to `events.jsonl` / `history.jsonl`

## Error Handling

| Failure | Behavior |
|---|---|
| **Timeout** | Retry once, then Codex fallback. Auto-scales for large repos. |
| **Auth / Session expired** | Print resume steps. Exit 126. No fallback. |
| **Schema invalid** | Retry once, then Codex fallback. |
| **Provider error** | Immediate Codex fallback. |

## Environment Check

```bash
./scripts/delegate.py --check
./scripts/env_check.py --repo-root .
```

Returns: binary availability, auth health, repo scale (normal/large/xlarge).

## Success Criteria

- Every run has explicit envelope + acceptance criteria
- Logs include: model, latency, fallback reason, token savings
- Fallback is deterministic and visible in telemetry
- Repo-level instructions include delegation routing block

## Usage

```
/kimi-delegate "summarize this failing CI log"
/kimi-delegate "draft migration checklist for auth module"
/kimi-delegate
```

## Bypass Detection

```bash
./scripts/detect_bypass.py --nudge              # check for raw pi calls
./scripts/detect_bypass.py --watch              # continuous watch
./scripts/detect_bypass.py --output report.json # save report
```

## Kimi vs Devin Delegate

| Dimension | kimi-delegate | devin-delegate |
|---|---|---|
| **Speed** | ~45s | ~14s |
| **Tasks** | search, summarize, draft, review, implementation-lite | research, implement, debug, review, browser |
| **Sandbox** | CLI-only | Full (browser, shell, file editing) |
| **Tokens** | 500–1200 output | 1200–2000 output |
| **Timeout** | 120s (max 600s) | 300s (max 600s) |
| **Best for** | Cheap bounded research | Implementation, debugging, browser/UI |
| **Fallback** | Codex gpt-5.3 | Codex gpt-5.5 |

Use `kimi-delegate` for cheap bounded research. Use `devin-delegate` for sandbox/full implementation.

See also: `/root/.agents/skills/devin-delegate/`

---
Read `references/architecture.md` for architecture and rollout guidance.

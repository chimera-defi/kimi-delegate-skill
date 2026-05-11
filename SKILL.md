---
name: kimi-delegate
license: MIT
description: |
  Route bounded coding subtasks through a cheap Kimi subagent using a structured delegation envelope,
  fallback routing, and telemetry for continuous improvement.
metadata:
  author: "GPT-5 Codex"
  category: "orchestration"
  version: "0.3.6"
  argument_hint: "[task-or-scope]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Kimi Delegate Skill

## Description

Use this skill when you want a stronger parent agent to plan and guardrails-check a task, then delegate a narrowly scoped execution subtask to a cheaper Kimi worker.

## Triggers

- The user asks to delegate to Kimi or a cheap subagent.
- The task can be split into a bounded subtask with explicit acceptance criteria.
- You want to reduce parent-agent token usage for search/summarize/draft/check steps.
- You need telemetry on delegation quality, cost behavior, and fallback rates.
- **Do NOT call `pi --provider kimi-coding` directly** — that bypasses the envelope, fallback, and telemetry this skill provides.

## Skip

- Tiny local edits where delegation overhead is larger than direct execution.
- Tasks requiring full-repo/global reasoning without clean scope boundaries.
- Any task where required secrets or sensitive content cannot leave the local execution boundary.

## First Move

1. Pre-flight check (optional but recommended):
   - `./scripts/delegate.py --check --task "..."`
   - Or: `./scripts/env_check.py`
2. Build a structured envelope:
   - `./scripts/plan_prompt.py --task "..."`
3. Delegate through the runner:
   - `./scripts/delegate.py --task "..." --context-file /tmp/context.txt`

## Process

1. Classify task (`search`, `summarize`, `draft`, `review`, `implementation-lite`).
2. Build envelope JSON with goal, scope, constraints, acceptance checks, and output schema.
3. **Auto-scale timeout** by repo size (large/xlarge repos get 2x–3x timeout automatically).
4. Execute with Kimi using conservative budgets from `config/routing.json`.
5. Validate response schema; retry once if invalid.
6. **If auth/session error detected**, emit manual resume steps instead of blind fallback.
7. If Kimi fails (timeout/schema/provider), route via Codex fallback by default.
8. Record telemetry for every call and periodically summarize trends.

## Error Handling

| Failure | Behavior |
|---|---|
| **Timeout** | Retry once, then Codex fallback. Timeout auto-scales for large repos. |
| **Auth / Session expired** | Print explicit resume steps. Exit code 126. No blind fallback. |
| **Schema invalid** | Retry once, then Codex fallback. |
| **Provider error** | Immediate Codex fallback. |

## Environment Check

```bash
./scripts/delegate.py --check --task "ping"
./scripts/env_check.py --repo-root .
```

Returns JSON with binary availability, auth health, and repo scale (normal / large / xlarge).

## Success Criteria

- Every delegated run has an explicit envelope and acceptance criteria.
- Delegation logs include model, latency, fallback reason, and estimated token savings.
- Fallback is deterministic and visible in telemetry.
- Repo-level instructions include the delegation routing block.

## Usage

```
/kimi-delegate "summarize this failing CI log"
/kimi-delegate "draft migration checklist for auth module"
/kimi-delegate
```

## Bypass Detection

```bash
./scripts/detect_bypass.py --nudge              # check for raw pi --provider kimi-coding calls
./scripts/detect_bypass.py --watch              # continuous watch mode
./scripts/detect_bypass.py --output report.json # save full report
```

## Comparison: Kimi vs Devin Delegate

Both skills share the same envelope/fallback/telemetry architecture. Choose based on task type:

| Dimension | kimi-delegate | devin-delegate |
|---|---|---|
| **Speed** | ~45s (model inference) | ~14s (sandbox warm) |
| **Task classes** | search, summarize, draft, review, implementation-lite | research, implement, debug, review, browser |
| **Sandbox** | CLI-only | Full (browser, shell, file editing) |
| **Token budget** | 500–1200 output tokens | 1200–2000 output tokens |
| **Base timeout** | 120s (max 600s w/ scaling) | 300s (max 600s w/ scaling) |
| **Best for** | Search, summarize, lightweight drafting | Implementation, debugging, browser/UI tasks |
| **Fallback** | Codex gpt-5.3 | Codex o3-mini |

Use `kimi-delegate` for cheap bounded research. Use `devin-delegate` when you need a sandbox or full implementation.

See also: `/root/.agents/skills/devin-delegate/`

---
Read `references/architecture.md` for architecture and rollout guidance.

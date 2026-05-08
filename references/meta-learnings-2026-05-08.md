# Meta Learnings — 2026-05-08

## What broke / needed fixing

- `escalate_if` in `routing.json` was dead config — never consumed by code.
- `output_is_valid` was too permissive: body text matching counted as valid heading.
- `last-envelope.json` leaked as an orphan artifact after fallback consumption.
- Retry latency was summed without per-attempt breakdown, losing granularity.
- `setup.sh` created `~/.local/bin/kimi-delegate` but never warned if PATH was missing.
- Pre-loop `schema_valid` assignment in `delegate.py` was technically dead code.

## Fixes applied

- Removed dead `escalate_if` from `routing.json`.
- Tightened validator to heading-only match.
- Added `envelope_path.unlink(missing_ok=True)` after fallback.
- Refactored retry loop to accumulate `attempt_latency_ms` per try.
- Added PATH check warning in `setup.sh`.
- Restructured retry loop so `schema_valid` is only evaluated inside the loop.
- Added `scripts/tests/__init__.py` for cleaner pytest discovery.
- Strengthened AGENTS.md routing blocks from "prefer" to "use the skill wrapper" across 24 repos.
- Added anti-direct-Kimi nudge: direct `pi --provider kimi-coding` calls bypass telemetry and fallback.
- Documented shorthand `kimi-delegate` alias in README and routing blocks.

## Adoption reality check (30 days)

- 262 sessions across workspace.
- Only 1 session used `delegate.py` (0.38% adoption).
- 2 sessions used Kimi subagent directly (0.76% adoption).
- 37 kimi subagent commands total, but only 3 went through the skill wrapper.
- The active repo (`SharedStake-ui/.worktrees/main`) uses Kimi heavily but bypasses the skill.

## Root cause of low adoption

- Routing block said "prefer" — too weak. Agents treated it as optional.
- Path `./skills/kimi-delegate/scripts/delegate.py` is verbose; no shorter alias was advertised.
- SKILL.md triggers did not explicitly prohibit direct `pi --provider kimi-coding` calls.
- Agents don't feel friction when bypassing the wrapper, so they take the shortest path.

## Improvements shipped today

- Routing blocks now say **"use the skill wrapper"** and **"Direct `pi --provider kimi-coding` calls bypass telemetry and fallback."**
- Added `kimi-delegate` shorthand reference for agents that have run `setup.sh`.
- Updated SKILL.md triggers with explicit **"Do NOT call `pi --provider kimi-coding` directly"** directive.
- Updated README with shorthand docs and session path assumptions for usage auditing.

## Next iteration ideas

- Add a friction hook: if `pi --provider kimi-coding` is detected in session logs, emit a nudge reminder.
- Consider a bash alias or function injection into agent shell rc files so `kd` is always available.
- Track "direct kimi bypass rate" as a new telemetry metric vs "skill-wrapper rate".
- Add a quick `delegate.py --check` that verifies `pi-kimi-subagent` and PATH without running a task.

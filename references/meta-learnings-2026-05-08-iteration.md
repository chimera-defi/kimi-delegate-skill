# Meta Learnings — 2026-05-08 (Aggressive Iteration)

## Problems the user reported

1. **Kimi subagent timeouts in Codex use in Etc-mono-repo** — large repo (2.5GB, 80k files) with default 60s timeout for search tasks.
2. **Auth errors where Kimi doesn't finish** — user needs to manually resume after session expiry.
3. **Telemetry not helping improve the skill** — needed richer data to diagnose the above.

## Fixes shipped today (aggressive iteration)

### 1. Auto-scaling timeouts by repo size

- `estimate_repo_scale()` uses `git ls-files` + `du -sm` to measure repo scale.
- `compute_timeout()` applies multipliers:
  - Normal repo: 1× base timeout
  - Large (≥10k files or ≥500MB): 2×
  - XLarge (≥50k files or ≥1GB): 3×
- Configurable thresholds in `config/kimi-delegate.json`.
- **Etc-mono-repo result**: search task timeout went from 60s → 180s (xlarge by MB).

### 2. Auth error detection + manual resume guidance

- `detect_auth_error()` scans stderr for auth/session/token/credential patterns.
- `classify_error()` categorizes: timeout, auth_error, provider_error, schema_invalid.
- **Auth errors bypass automatic fallback** — instead of silently routing to Codex:
  - Print explicit resume steps
  - Exit code 126 (distinct from generic error)
  - Record telemetry with `error_category: auth_error`

### 3. Richer telemetry for diagnostic power

- `attempt_latencies[]` array: per-attempt latency, not just sum
- `repo_scale`: files + mb per invocation
- `error_category`: auth_error, timeout, provider_error, schema_invalid
- Telemetry summary now shows:
  - `auth_errors` count
  - `timeouts` count
  - `timeouts_in_large_repos` count
  - `repo_scale_distribution`: normal/large/xlarge/unknown
  - `error_categories` breakdown

### 4. Pre-flight environment check

- `delegate.py --check` or `env_check.py` verifies:
  - `pi-kimi-subagent`, `pi`, `codex`, `kimi-delegate` binary availability
  - Auth health (no-op ping via pi)
  - Repo scale classification
- Returns JSON + exit code 126 for auth issues.

### 5. Task-class timeout scaling

- `routing.json` now has `timeout_scale` per task class:
  - review/implementation-lite: 1.5× (heavier tasks need more time)
  - search/summarize/draft: 1.0×

## Test results

- 13/13 tests pass
- `env_check.py` on Etc-mono-repo correctly classifies it as `xlarge` (2473MB)
- `delegate.py --check` confirms all binaries present and auth healthy

## Adoption still low — next levers

- **SharedStake-ui** (the only active repo) uses Kimi heavily (37 commands) but bypasses the skill wrapper (only 3 delegate commands).
- Need to either:
  a) Add session-log friction detection (nudge when raw `pi --provider kimi-coding` detected)
  b) Make the skill wrapper the *only* way to call Kimi (e.g., alias injection)
  c) Track "bypass rate" metric and set a target

## Telemetry-driven improvement loop is now closed

Before: telemetry only tracked ok/error + fallback rate.
After: telemetry tells us *why* things failed (auth vs timeout vs provider), *where* (repo scale), and *how long* each attempt took. This lets us tune thresholds with data.

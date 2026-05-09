# Changelog

All notable changes to the kimi-delegate skill.

## [0.3.1] - 2026-05-08

### Added
- **Positional task argument** (`delegate.py`). `kd 'summarize logs'` works without `--task` flag.
- **Task history** (`--last`). Re-runs the previous task from `history.jsonl`.
- **Quick mode** (`--quick` / `-q`). Suppresses post-run summary for clean output.
- **Post-run confirmation** printed after successful delegation.
- **Shell completion** installed by `setup.sh`. Bash completion script with flag and task-class suggestions. Alias `kd-last` added.

## [0.3.0] - 2026-05-08

### Added (6 adoption levers)
- **Mandatory routing blocks** in AGENTS.md. Language changed from advisory "prefer" to **"MANDATORY"** with explicit prohibition on direct `pi --provider kimi-coding` calls.
- **Smart task classifier** (`plan_prompt.py`). Scoring-based classification with tie-break priority and expanded keyword coverage (look, scan, discover, condense, recap, overview, security, vulnerability, pentest, assess, evaluate, check, inspect, create, generate, produce, author, refactor, upgrade, add, remove, change, modify, convert, rewrite).
- **Interactive default** (`delegate.py`). Running `kimi-delegate` with no `--task` automatically launches the interactive envelope builder.
- **Batch delegation** (`delegate.py --batch`). Reads a JSONL file of tasks and delegates each sequentially with telemetry for every run.
- **Real-time bypass watch** (`detect_bypass.py --watch`). Polls session files continuously and emits nudges when new bypasses are detected.
- **CI gate** (`scripts/ci_gate.py`). Fails builds if bypass rate exceeds threshold (default 20%). Returns exit code 1 with actionable fix instructions.

### Changed
- Refactored `delegate.py`: extracted `run_delegate()` and `run_batch()` functions.
- Added `ci-gate` subcommand to `kimi-delegate-manage.sh`.

## [0.2.4] - 2026-05-08

### Added
- **Quick reference card** in README.md with all aliases and commands.
- **Per-repo config example** (`config/.kimi-delegate.json.example`) documenting override keys.

## [0.2.3] - 2026-05-08

### Added
- **Per-repo config overrides** (`delegate.py`). Reads `.kimi-delegate.json` from repo root and merges overrides into global config. Enables per-repo timeout/threshold tuning.
- **Auto-nudge on shell startup** (`setup.sh`). Injects a bash function into `.bashrc` / `.zshrc` that runs `session-nudge --quiet` on every interactive shell startup.

## [0.2.2] - 2026-05-08

### Added
- **Session nudge** (`scripts/session_nudge.py`). Checks recent bypass rate and prints a nudge if above threshold. Returns exit code 1 when threshold exceeded for CI-style gating.
- **Inline stats** (`delegate.py --stats`). Prints a concise 14-day telemetry summary inline.
- `kimi-delegate-manage.sh` subcommand: `session-nudge`.
- Shell aliases: `kd-stats`, `kd-nudge`.

### Fixed
- Restored missing `setup` case in `kimi-delegate-manage.sh` that was accidentally dropped.
- Added missing `import sys` to `delegate.py`.

## [0.2.1] - 2026-05-08

### Added
- **Interactive envelope builder** (`scripts/interactive.py`). Guided walkthrough with smart defaults per task class. Offers immediate delegation after building.
- **HTML telemetry dashboard** (`scripts/generate_dashboard.py` + `telemetry/dashboard.html`). Dark-themed report with cards and tables for status, fallback reasons, error categories, repo scale distribution.
- `kimi-delegate-manage.sh` subcommands: `interactive|i`, `dashboard`.
- Shell alias `kd-i` for interactive mode.

## [0.2.0] - 2026-05-08

### Added
- **Auto-scaling timeouts** by repo size. Large repos (≥10k files or ≥500MB) get 2× timeout. XLarge repos (≥50k files or ≥1GB) get 3×. Configurable thresholds in `config/kimi-delegate.json`.
- **Auth error detection** with manual resume guidance. Detects auth/session/token/credential errors and prints explicit resume steps instead of silently falling back to Codex. Exit code 126.
- **Pre-flight environment check** via `delegate.py --check` and standalone `env_check.py`. Verifies binaries, auth health, and repo scale classification.
- **Bypass detection** via `detect_bypass.py`. Scans Claude (`~/.claude/projects`) and Codex (`~/.codex/sessions`) session logs for raw Kimi calls that bypass the skill wrapper. `--nudge` mode prints actionable reminders.
- **Timeout threshold tuning** via `tune_timeouts.py`. Analyzes telemetry by repo scale and suggests multiplier adjustments when timeout rate > 15%.
- **Bash alias injection** in `setup.sh`. Injects `kd='kimi-delegate'` and `kd-check='kimi-delegate --check'` into `.bashrc` / `.zshrc`.
- **Bypass rate tracking** in `audit_workspace_usage.py`. Tracks `raw_kimi_cmd_count` per repo and reports `bypass_rate_pct` with target <20%.
- **Richer telemetry**: `attempt_latencies[]`, `repo_scale`, `error_category`. Summary shows `auth_errors`, `timeouts`, `timeouts_in_large_repos`, `repo_scale_distribution`, `error_categories`.
- **Task-class timeout scaling** in `routing.json`. Review/implementation-lite tasks get 1.5× multiplier.
- **5 new tests** for delegate helper functions and bypass detection.

### Changed
- `output_is_valid` tightened to require actual markdown headings (removed body-text fallback).
- `last-envelope.json` cleaned up after fallback consumption.
- Retry loop refactored to accumulate per-attempt latency properly.
- `setup.sh` warns if `~/.local/bin` is not on PATH.
- Routing blocks strengthened from "prefer" to "use the skill wrapper" with anti-direct-Kimi nudge.

### Fixed
- Dead `escalate_if` config removed from `routing.json`.
- Orphan `last-envelope.json` leak after fallback.
- Dead pre-loop `schema_valid` assignment in `delegate.py`.
- Missing `scripts/tests/__init__.py`.

## [0.1.0] - 2026-05-07

### Added
- Initial skill package: `SKILL.md`, scripts, config, prompts, telemetry, references.
- Structured delegation envelope generation (`plan_prompt.py`).
- Kimi execution runner with Codex fallback (`delegate.py`, `fallback.py`).
- Local telemetry loop (`kimi_delegate_telemetry.py`).
- Workspace propagation tooling (`install_workspace_skill.py`, `audit_workspace_skills.py`).
- `kimi-delegate-manage.sh` unified CLI.
- 8 initial tests covering plan, telemetry, repo scan, audit, and Codex session parsing.

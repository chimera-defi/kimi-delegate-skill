# Maintenance State
last_run: 2026-09-05
focus: observability
status: completed
completed:
  - fix(delegate): catch TimeoutExpired in build_envelope() - subprocess.run had timeout=30 but no except clause
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: install-layout dependent
  - test_env_check_catches_timeout: subprocess.run mock
attempt_counts:

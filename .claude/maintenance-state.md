# Maintenance State
last_run: 2026-06-27
focus: observability
status: completed
completed:
  - fix(delegate.py): add FileNotFoundError catch in call() so missing binary returns rc=127 instead of crashing
  - fix(delegate.py): change check=True to check=False in generate_envelope() to preserve stderr on failure
  - fix(delegate.py): wrap future.result() in try/except in run_batch() to prevent single-task crash from aborting entire batch
  - fix(delegate.py): guard interactive subprocess call against FileNotFoundError/OSError
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: install-layout dependent
  - test_env_check_catches_timeout: subprocess.run mock

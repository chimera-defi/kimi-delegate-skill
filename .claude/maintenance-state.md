# Maintenance State
last_run: 2026-06-08
focus: deps
status: completed
completed: [no npm/Python deps to bump; skills telemetry: 56 tests passing baseline]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: old assertion checked ".openclaw"/"workspace" in path — install-layout dependent; fixed to assert Path equality to parents[3]
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which guard; fixed by also mocking shutil.which
  - CI was missing pip install pytest step: added in PR #15
skip_next_run: []
attempt_counts:

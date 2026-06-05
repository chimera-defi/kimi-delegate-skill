# Maintenance State
last_run: 2026-06-04
focus: test-coverage
status: completed
completed: [fix 2 pre-existing baseline failures in test_edge_cases.py (54→56 tests), add pip install pytest to CI workflow, PR #15 open and green]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: old assertion checked ".openclaw"/"workspace" in path — install-layout dependent; fixed to assert Path equality to parents[3]
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which guard; fixed by also mocking shutil.which
  - Codex review (P2): addressed — tightened assertion to exact equality + non-root + startswith checks (commit ab74d71)
  - CI was missing pip install pytest step: added in same PR
skip_next_run: [test_edge_cases.py baseline fixes — already merged to PR]

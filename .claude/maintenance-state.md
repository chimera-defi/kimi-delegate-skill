# Maintenance State
last_run: 2026-06-12
focus: dead-code
status: completed
completed: [dead code scan — no actionable removals found]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: old assertion checked ".openclaw"/"workspace" in path — install-layout dependent; fixed to assert Path equality to parents[3]
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which guard; fixed by also mocking shutil.which
  - Codex review (P2): addressed — tightened assertion to exact equality + non-root + startswith checks (commit ab74d71)
  - CI was missing pip install pytest step: added in same PR
  - pi binary not available in sandbox — pi-wrapper-binary.py --help passthrough fails; telemetry check skipped
skip_next_run: [test_edge_cases.py baseline fixes — already merged to PR]

## Dead Code Scan Notes (2026-06-12)
- rg TODO/FIXME/HACK: no results
- rg dead print(): no results
- vulture --min-confidence 80: no results
- pi-wrapper-binary.py entrypoint: requires real pi binary for help passthrough — telemetry flag check not possible in sandbox

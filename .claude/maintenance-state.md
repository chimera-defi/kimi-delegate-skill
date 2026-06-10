# Maintenance State
last_run: 2026-06-10
focus: security
status: completed
completed: [add .env/.env.*/.env.local to .gitignore (was missing — preventative hardening); secret scan passed (test_edge_cases.py match is a fake fixture token)]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: old assertion checked path layout — fixed to assert Path equality
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which guard — fixed by also mocking shutil.which
  - CI was missing pip install pytest step: added in same PR
skip_next_run: [test_edge_cases.py baseline fixes — already merged to PR]

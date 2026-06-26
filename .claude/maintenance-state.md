# Maintenance State
last_run: 2026-06-23
focus: ts-cleanup
status: completed
completed: [AST-based unused import scan clean — no unused imports, no TODOs/FIXMEs in any Python file]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: install-layout dependent; fixed assertion
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which; fixed by mocking shutil.which
skip_next_run: []

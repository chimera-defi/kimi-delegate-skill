# Maintenance State
last_run: 2026-06-19
focus: dead-code
status: completed
completed: [dead code scan clean — vulture --min-confidence 80 found nothing, pyflakes found no unused imports, no TODOs/FIXMEs. print() statements in scripts are all intentional JSON/text output (not debug logs).]
in_progress:
pending: []
known_failures:
  - test_repo_root_from_script_when_git_missing: install-layout dependent; fixed assertion
  - test_env_check_catches_timeout: subprocess.run mock bypassed by shutil.which; fixed by mocking shutil.which
skip_next_run: []

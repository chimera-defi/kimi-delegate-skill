import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_EXTRAS = Path(os.environ.get(
    "DELEGATE_EXTRAS_DIR",
    str(Path.home() / ".claude" / "skills" / "delegate-skill" / "delegate-extras" / "kimi"),
))
if _EXTRAS.is_dir() and str(_EXTRAS) not in sys.path:
    sys.path.insert(0, str(_EXTRAS))

collect_ignore = []
if not _EXTRAS.is_dir():
    collect_ignore += ["test_audit_workspace.py", "test_usage_parser.py"]

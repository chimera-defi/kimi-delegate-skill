#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("audit_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _audit_script() -> Path:
    extras = Path(os.environ.get(
        "DELEGATE_EXTRAS_DIR",
        str(Path.home() / ".claude" / "skills" / "delegate-skill" / "delegate-extras" / "kimi"),
    ))
    cand = extras / "audit_workspace_skills.py"
    if cand.exists():
        return cand
    return Path(__file__).resolve().parents[2] / "scripts" / "audit_workspace_skills.py"


def test_has_doc_block_requires_markers(tmp_path: Path) -> None:
    mod = load_module(_audit_script())

    repo = tmp_path / "repo"
    repo.mkdir()

    readme = repo / "README.md"
    readme.write_text("this mentions kimi-delegate but has no routing block\n", encoding="utf-8")
    present, hits = mod.has_doc_block(repo)
    assert not present
    assert hits == []

    agents = repo / "AGENTS.md"
    agents.write_text(
        "<!-- kimi-delegate:begin -->\nfoo\n<!-- kimi-delegate:end -->\n",
        encoding="utf-8",
    )
    present, hits = mod.has_doc_block(repo)
    assert present
    assert "AGENTS.md" in hits

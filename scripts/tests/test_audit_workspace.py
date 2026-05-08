#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("audit_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_has_doc_block_requires_markers(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "audit_workspace_skills.py")

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

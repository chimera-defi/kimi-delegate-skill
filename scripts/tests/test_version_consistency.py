#!/usr/bin/env python3
"""Ensure all version fields stay in sync across JSON, markdown, and SKILL metadata."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _changelog_top_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"No version header found in {path}")
    return m.group(1)


def test_version_consistency_across_files() -> None:
    root = Path(__file__).resolve().parents[2]
    changelog_version = _changelog_top_version(root / "CHANGELOG.md")

    # config/kimi-delegate.json
    config = json.loads((root / "config" / "kimi-delegate.json").read_text(encoding="utf-8"))
    assert config["version"] == changelog_version, (
        f"config/kimi-delegate.json version {config['version']} != {changelog_version}"
    )

    # config/routing.json
    routing = json.loads((root / "config" / "routing.json").read_text(encoding="utf-8"))
    assert routing["version"] == changelog_version, (
        f"config/routing.json version {routing['version']} != {changelog_version}"
    )

    # SKILL.md front-matter
    skill_md = (root / "SKILL.md").read_text(encoding="utf-8")
    skill_version_match = re.search(r"^version:\s*(\d+\.\d+\.\d+)", skill_md, re.MULTILINE)
    assert skill_version_match is not None, "No version field in SKILL.md front-matter"
    assert skill_version_match.group(1) == changelog_version, (
        f"SKILL.md version {skill_version_match.group(1)} != {changelog_version}"
    )

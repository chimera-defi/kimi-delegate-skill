#!/usr/bin/env python3
"""Ensure all .py files in scripts/ compile without syntax errors."""
from __future__ import annotations

import py_compile
from pathlib import Path


def test_all_scripts_compile() -> None:
    root = Path(__file__).resolve().parents[2]
    scripts_dir = root / "scripts"
    failures: list[str] = []
    for py_file in scripts_dir.rglob("*.py"):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(f"{py_file.relative_to(root)}: {exc}")
    assert not failures, "Syntax errors found:\n" + "\n".join(failures)

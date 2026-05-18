#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest import mock


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("hooks_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_resolve_hooks_dir_honors_core_hookspath(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "install_git_hooks.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"], check=True, capture_output=True, text=True)

    hooks_dir = mod.resolve_hooks_dir(repo)
    assert hooks_dir is not None
    assert hooks_dir == (repo / ".githooks").resolve()


def test_install_hook_uses_resolved_hook_path(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "install_git_hooks.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks_dir = tmp_path / "custom-hooks"
    skill_root = tmp_path / "skill-root"
    skill_root.mkdir()

    with mock.patch.object(mod, "resolve_hooks_dir", return_value=hooks_dir):
        result = mod.install_hook(repo, skill_root, dry_run=False)

    hook_path = hooks_dir / "pre-commit"
    assert result["status"] == "installed"
    assert result["hook_path"] == str(hook_path)
    assert hook_path.exists()
    content = hook_path.read_text(encoding="utf-8")
    assert mod.HOOK_MARKER in content
    assert str(skill_root) in content


def test_install_hook_is_idempotent(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "install_git_hooks.py")
    repo = tmp_path / "repo"
    repo.mkdir()
    hooks_dir = tmp_path / "hooks"
    skill_root = tmp_path / "skill-root"
    skill_root.mkdir()

    with mock.patch.object(mod, "resolve_hooks_dir", return_value=hooks_dir):
        first = mod.install_hook(repo, skill_root, dry_run=False)
        second = mod.install_hook(repo, skill_root, dry_run=False)

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"

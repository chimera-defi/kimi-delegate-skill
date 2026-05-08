#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("repo_scan_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_iter_workspace_repos_includes_worktrees(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "repo_scan.py")

    workspace = tmp_path / "workspace"
    repo = workspace / "demo-repo"
    worktree = repo / ".worktrees" / "main"
    other = workspace / "not-a-repo"

    worktree.mkdir(parents=True)
    other.mkdir(parents=True)
    (repo / ".git").write_text("gitdir: /tmp/demo\n", encoding="utf-8")
    (worktree / ".git").write_text("gitdir: /tmp/demo-main\n", encoding="utf-8")

    repos_with_worktrees = mod.iter_workspace_repos(workspace, include_worktrees=True)
    labels_with = [mod.repo_label(p, workspace) for p in repos_with_worktrees]
    assert labels_with == ["demo-repo", "demo-repo/.worktrees/main"]

    repos_no_worktrees = mod.iter_workspace_repos(workspace, include_worktrees=False)
    labels_without = [mod.repo_label(p, workspace) for p in repos_no_worktrees]
    assert labels_without == ["demo-repo"]


def test_iter_workspace_repos_skips_symlink_children(tmp_path: Path) -> None:
    mod = load_module(Path(__file__).resolve().parents[2] / "scripts" / "repo_scan.py")

    workspace = tmp_path / "workspace"
    real_repo = workspace / "real-repo"
    linked_repo = workspace / "linked-repo"

    real_repo.mkdir(parents=True)
    (real_repo / ".git").write_text("gitdir: /tmp/real\n", encoding="utf-8")
    linked_repo.symlink_to(real_repo, target_is_directory=True)

    labels = [mod.repo_label(p, workspace) for p in mod.iter_workspace_repos(workspace, include_worktrees=True)]
    assert labels == ["real-repo"]

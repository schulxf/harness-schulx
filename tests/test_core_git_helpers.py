from __future__ import annotations

import subprocess
from pathlib import Path

from harness_core import git_helpers
from harness_core.defaults import DEFAULT_PROTECTED_BRANCHES
from harness_core.git_helpers import (
    current_git_branch,
    discover_git_dir,
    git_output,
    is_git_repo,
    protected_branches,
)
from harness_core.paths import config_path
from harness_core.storage import write_json


def test_discover_git_dir_finds_parent_git_directory(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    nested = tmp_path / "a" / "b"
    git_dir.mkdir()
    nested.mkdir(parents=True)

    assert discover_git_dir(nested) == git_dir


def test_discover_git_dir_resolves_gitdir_file(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    actual_git = tmp_path / "actual" / "gitdir"
    worktree.mkdir()
    actual_git.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../actual/gitdir\n", encoding="utf-8")

    assert discover_git_dir(worktree) == actual_git.resolve(strict=False)


def test_current_git_branch_reads_head_ref(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/test\n", encoding="utf-8")

    assert current_git_branch(tmp_path) == "feature/test"


def test_current_git_branch_returns_detached_short_sha(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("abcdef1234567890\n", encoding="utf-8")

    assert current_git_branch(tmp_path) == "abcdef123456"


def test_is_git_repo_false_without_git_dir(tmp_path: Path) -> None:
    assert is_git_repo(tmp_path) is False


def test_is_git_repo_uses_git_rev_parse(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout="true\n", stderr="")

    monkeypatch.setattr(git_helpers.subprocess, "run", fake_run)

    assert is_git_repo(tmp_path) is True


def test_git_output_returns_stdout_or_stderr(monkeypatch, tmp_path: Path) -> None:
    def ok_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(git_helpers.subprocess, "run", ok_run)
    assert git_output(tmp_path, ["status"]) == "ok"

    def fail_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 1, stdout="", stderr="boom\n")

    monkeypatch.setattr(git_helpers.subprocess, "run", fail_run)
    assert git_output(tmp_path, ["status"]) == "boom"


def test_git_output_handles_missing_git(monkeypatch, tmp_path: Path) -> None:
    def missing_run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(git_helpers.subprocess, "run", missing_run)

    assert git_output(tmp_path, ["status"]) == "git nao esta instalado ou nao esta no PATH."


def test_protected_branches_reads_config_or_default(tmp_path: Path) -> None:
    assert protected_branches(tmp_path) == DEFAULT_PROTECTED_BRANCHES

    write_json(config_path(tmp_path), {"protected_branches": ["release"]})

    assert protected_branches(tmp_path) == ["release"]

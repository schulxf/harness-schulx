from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from harness_core.paths import config_path
from harness_core.repo_guard import (
    prepared_repo,
    require_existing_root,
    require_safe_branch,
    root_from_args,
)
from harness_core.storage import write_json


def test_root_from_args_expands_and_resolves_repo(tmp_path: Path) -> None:
    args = argparse.Namespace(repo=str(tmp_path))

    assert root_from_args(args) == tmp_path.resolve()


def test_require_existing_root_rejects_missing_or_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Diretorio do repo nao existe"):
        require_existing_root(tmp_path / "missing")

    file_path = tmp_path / "not-a-dir"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="nao e um diretorio"):
        require_existing_root(file_path)


def test_prepared_repo_requires_harness_config(tmp_path: Path) -> None:
    args = argparse.Namespace(repo=str(tmp_path), allow_main=False)

    with pytest.raises(SystemExit, match="Harness nao inicializado"):
        prepared_repo(args)

    write_json(config_path(tmp_path), {"project_name": "test"})
    assert prepared_repo(args) == tmp_path.resolve()


def test_require_safe_branch_blocks_protected_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("harness_core.repo_guard.current_git_branch", lambda root: "main")
    monkeypatch.setattr("harness_core.repo_guard.protected_branches", lambda root: ["main"])

    with pytest.raises(SystemExit, match="Operacao bloqueada"):
        require_safe_branch(tmp_path, argparse.Namespace(allow_main=False), "start")

    require_safe_branch(tmp_path, argparse.Namespace(allow_main=True), "start")


def test_require_safe_branch_allows_no_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("harness_core.repo_guard.current_git_branch", lambda root: None)

    require_safe_branch(tmp_path, argparse.Namespace(allow_main=False), "start")

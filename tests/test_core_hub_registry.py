from __future__ import annotations

from pathlib import Path

from harness_core.hub_registry import (
    hub_repo_registry_entries,
    load_hub_repo_registry,
    remove_hub_repo,
    save_hub_repo_registry,
    set_hub_repo_hidden,
)
from harness_core.paths import hub_repo_registry_path
from harness_core.storage import read_json, write_json


def test_hub_repo_registry_round_trip_normalizes_and_deduplicates(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    save_hub_repo_registry(tmp_path, [str(repo_a), str(repo_b), str(repo_a)])

    assert load_hub_repo_registry(tmp_path) == [str(repo_a.resolve()), str(repo_b.resolve())]
    payload = read_json(hub_repo_registry_path(tmp_path))
    assert "updated_at" in payload


def test_load_hub_repo_registry_ignores_blank_entries(tmp_path: Path) -> None:
    write_json(hub_repo_registry_path(tmp_path), {"repos": ["", "  ", "repo"]})

    assert load_hub_repo_registry(tmp_path) == ["repo"]


def test_load_hub_repo_registry_handles_malformed_payload(tmp_path: Path) -> None:
    write_json(hub_repo_registry_path(tmp_path), ["not", "a", "dict"])

    assert load_hub_repo_registry(tmp_path) == []


def test_hidden_repo_stays_registered_but_is_not_returned_for_monitoring(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    save_hub_repo_registry(tmp_path, [str(repo_a), str(repo_b)])

    set_hub_repo_hidden(tmp_path, str(repo_b), hidden=True)

    assert load_hub_repo_registry(tmp_path) == [str(repo_a.resolve())]
    assert hub_repo_registry_entries(tmp_path) == [
        {"path": str(repo_a.resolve()), "hidden": False},
        {"path": str(repo_b.resolve()), "hidden": True},
    ]

    set_hub_repo_hidden(tmp_path, str(repo_b), hidden=False)
    assert load_hub_repo_registry(tmp_path) == [str(repo_a.resolve()), str(repo_b.resolve())]


def test_removing_repo_only_changes_registry_and_keeps_folder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = repo / "arquivo-do-usuario.txt"
    marker.write_text("preservar", encoding="utf-8")
    save_hub_repo_registry(tmp_path, [str(repo)])
    set_hub_repo_hidden(tmp_path, str(repo), hidden=True)

    remove_hub_repo(tmp_path, str(repo))

    assert hub_repo_registry_entries(tmp_path) == []
    assert marker.read_text(encoding="utf-8") == "preservar"


def test_save_registry_preserves_hidden_state_for_existing_repos(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    save_hub_repo_registry(tmp_path, [str(repo_a), str(repo_b)])
    set_hub_repo_hidden(tmp_path, str(repo_b), hidden=True)

    save_hub_repo_registry(tmp_path, [str(repo_b), str(repo_a), str(repo_b)])

    assert hub_repo_registry_entries(tmp_path)[0] == {
        "path": str(repo_b.resolve()),
        "hidden": True,
    }

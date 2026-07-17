from __future__ import annotations

from pathlib import Path

from harness_core.hub_registry import (
    HUB_CONTROL_REPO_ENV,
    add_hub_repo,
    discover_hub_control_repo,
    hub_repo_registry_entries,
    load_hub_repo_registry,
    register_implementation_repo,
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


def test_discover_hub_control_repo_uses_explicit_or_windows_default_path(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-control"
    write_json(explicit / ".harness" / "config.json", {})
    assert discover_hub_control_repo({HUB_CONTROL_REPO_ENV: str(explicit)}) == explicit.resolve()

    local_app_data = tmp_path / "local-app-data"
    default_control = local_app_data / "HarnessAcompanhamento" / "control"
    write_json(default_control / ".harness" / "config.json", {})
    assert discover_hub_control_repo({"LOCALAPPDATA": str(local_app_data)}) == default_control.resolve()

    assert discover_hub_control_repo({HUB_CONTROL_REPO_ENV: ""}) is None


def test_implementer_registration_preserves_hidden_choice_and_readds_removed_repo(tmp_path: Path) -> None:
    control = tmp_path / "control"
    repo = tmp_path / "projeto"
    repo.mkdir()
    write_json(control / ".harness" / "config.json", {})
    environment = {HUB_CONTROL_REPO_ENV: str(control)}

    first = register_implementation_repo(repo, environ=environment)
    assert first["status"] == "added"
    assert first["hidden"] is False

    set_hub_repo_hidden(control, str(repo), hidden=True)
    existing = register_implementation_repo(repo, environ=environment)
    assert existing["status"] == "already_registered"
    assert existing["hidden"] is True
    assert load_hub_repo_registry(control) == []

    remove_hub_repo(control, str(repo))
    restored = register_implementation_repo(repo, environ=environment)
    assert restored["status"] == "added"
    assert restored["hidden"] is False
    assert load_hub_repo_registry(control) == [str(repo.resolve())]


def test_regular_add_still_shows_a_previously_hidden_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    save_hub_repo_registry(tmp_path, [str(repo)])
    set_hub_repo_hidden(tmp_path, str(repo), hidden=True)

    assert add_hub_repo(tmp_path, str(repo)) is False
    assert load_hub_repo_registry(tmp_path) == [str(repo.resolve())]

from __future__ import annotations

from pathlib import Path

from harness_core.hub_registry import load_hub_repo_registry, save_hub_repo_registry
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

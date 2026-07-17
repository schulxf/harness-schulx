from __future__ import annotations

from pathlib import Path

from harness_core import hub_state
from harness_core.paths import config_path, queue_path, tasks_index_path
from harness_core.storage import write_json


def init_hub_repo(root: Path) -> None:
    write_json(config_path(root), {"project_name": "Hub Repo", "active_profile": "balanced"})
    write_json(
        tasks_index_path(root),
        [
            {
                "task_id": "TASK-001",
                "title": "Build login",
                "status": "in_progress",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )
    write_json(queue_path(root), [{"id": "QUEUE-001", "task_id": "TASK-001", "status": "active"}])


def test_collect_hub_repo_state_reports_missing_or_uninitialized_repo(tmp_path: Path) -> None:
    missing = hub_state.collect_hub_repo_state(tmp_path / "missing", index=2)
    assert missing["phase"] == "offline"
    assert missing["error"] == "repo_missing"

    uninitialized = tmp_path / "repo"
    uninitialized.mkdir()
    state = hub_state.collect_hub_repo_state(uninitialized, index=3)
    assert state["phase"] == "offline"
    assert state["error"] == "harness_not_initialized"


def test_collect_hub_repo_state_builds_synthetic_agent(tmp_path: Path) -> None:
    init_hub_repo(tmp_path)

    state = hub_state.collect_hub_repo_state(tmp_path)

    assert state["project"] == "Hub Repo"
    assert state["phase"] == "build"
    assert state["active_task"]["task_id"] == "TASK-001"
    assert state["agents"][0]["role"] == "builder"
    assert state["counts"]["active"] == 1


def test_collect_hub_repo_state_cache_returns_deep_copy(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_collect(root: Path, index: int = 0) -> dict:
        calls.append(index)
        return {"index": index, "items": []}

    monkeypatch.setattr(hub_state, "collect_hub_repo_state", fake_collect)

    first = hub_state.collect_hub_repo_state_cached(tmp_path, index=4, ttl_seconds=60)
    first["items"].append("mutated")
    second = hub_state.collect_hub_repo_state_cached(tmp_path, index=4, ttl_seconds=60)

    assert calls == [4]
    assert second == {"index": 4, "items": []}


def test_collect_dashboard_hub_state_aggregates_repos(monkeypatch, tmp_path: Path) -> None:
    init_hub_repo(tmp_path)
    monkeypatch.setattr(hub_state, "collect_wmux_state", lambda: {"available": False})

    state = hub_state.collect_dashboard_hub_state([tmp_path], action_token="tok")

    assert state["repo_count"] == 1
    assert state["active_repos"] == 1
    assert state["total_tasks"] == 1
    assert state["wmux"] == {"available": False}
    assert state["action_token"] == "tok"

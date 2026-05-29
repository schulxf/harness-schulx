from __future__ import annotations

from pathlib import Path

from harness_core.agent_registry import (
    agent_status_from_state,
    load_agent_registry,
    load_hub_agents,
    save_agent_registry,
    upsert_agent,
)


def test_agent_registry_round_trip(tmp_path: Path) -> None:
    registry = {"agents": [{"id": "agent-1"}], "updated_at": "now"}

    save_agent_registry(tmp_path, registry)

    assert load_agent_registry(tmp_path) == registry


def test_agent_status_from_state_maps_active_states_to_working() -> None:
    assert agent_status_from_state("idle") == "idle"
    assert agent_status_from_state("done") == "done"
    assert agent_status_from_state("blocked") == "blocked"
    assert agent_status_from_state("review") == "working"


def test_upsert_agent_creates_and_updates_existing_agent(tmp_path: Path) -> None:
    created = upsert_agent(
        tmp_path,
        "agent-1",
        name="Builder",
        role="builder",
        state="working",
        task_id="TASK-001",
        task_title="Build",
        speech="Working",
        event_id="event-1",
    )

    assert created["id"] == "agent-1"
    assert created["status"] == "working"
    assert created["phase"] == "builder"
    assert created["last_event_id"] == "event-1"

    updated = upsert_agent(
        tmp_path,
        "agent-1",
        name="Builder",
        role="builder",
        state="idle",
        phase="report",
        speech="Done",
    )

    assert updated["created_at"] == created["created_at"]
    assert updated["status"] == "idle"
    assert updated["phase"] == "report"
    assert updated["last_event_id"] == "event-1"
    assert len(load_agent_registry(tmp_path)["agents"]) == 1


def test_load_hub_agents_filters_inactive_and_returns_last_eight(tmp_path: Path) -> None:
    agents = [
        {"id": f"agent-{index}", "state": "working" if index % 2 else "done"}
        for index in range(20)
    ]
    save_agent_registry(tmp_path, {"agents": agents})

    hub_agents = load_hub_agents(tmp_path)

    assert len(hub_agents) == 8
    assert [agent["id"] for agent in hub_agents] == [
        "agent-5",
        "agent-7",
        "agent-9",
        "agent-11",
        "agent-13",
        "agent-15",
        "agent-17",
        "agent-19",
    ]

from __future__ import annotations

from pathlib import Path

from harness_core.agent_registry import (
    agent_status_from_state,
    default_agent_transcript_path,
    load_agent_registry,
    load_hub_agents,
    save_agent_registry,
    upsert_agent,
)


def test_agent_registry_round_trip(tmp_path: Path) -> None:
    registry = {"agents": [{"id": "agent-1"}], "updated_at": "now"}

    save_agent_registry(tmp_path, registry)

    loaded = load_agent_registry(tmp_path)
    assert loaded["updated_at"] == "now"
    assert loaded["agents"][0] == {
        "id": "agent-1",
        "cli": "codex",
        "sector": "idle",
        "pty_id": "",
        "repo_root": str(tmp_path.resolve(strict=False)),
        "cwd": str(tmp_path.resolve(strict=False)),
        "transcript_path": default_agent_transcript_path("agent-1"),
        "spawned_by": "ui",
    }


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
        cli="claude",
        sector="implement",
        pty_id="pty-1",
        repo_root=str(tmp_path),
        cwd=str(tmp_path / "work"),
        transcript_path=".harness/agents/agent-1/custom.jsonl",
        spawned_by="supervisor",
    )

    assert created["id"] == "agent-1"
    assert created["status"] == "working"
    assert created["phase"] == "builder"
    assert created["last_event_id"] == "event-1"
    assert created["cli"] == "claude"
    assert created["sector"] == "implement"
    assert created["pty_id"] == "pty-1"
    assert created["repo_root"] == str(tmp_path)
    assert created["cwd"] == str(tmp_path / "work")
    assert created["transcript_path"] == ".harness/agents/agent-1/custom.jsonl"
    assert created["spawned_by"] == "supervisor"

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
    assert updated["cli"] == "claude"
    assert updated["sector"] == "implement"
    assert updated["pty_id"] == "pty-1"
    assert updated["repo_root"] == str(tmp_path)
    assert updated["cwd"] == str(tmp_path / "work")
    assert updated["transcript_path"] == ".harness/agents/agent-1/custom.jsonl"
    assert updated["spawned_by"] == "supervisor"
    assert len(load_agent_registry(tmp_path)["agents"]) == 1


def test_upsert_agent_defaults_new_hub_metadata(tmp_path: Path) -> None:
    agent = upsert_agent(
        tmp_path,
        "builder-1",
        name="Builder",
        role="builder",
        state="working",
        event_id="EV-1",
    )

    assert agent["cli"] == "codex"
    assert agent["sector"] == "implement"
    assert agent["pty_id"] == ""
    assert agent["repo_root"] == str(tmp_path.resolve(strict=False))
    assert agent["cwd"] == str(tmp_path.resolve(strict=False))
    assert agent["transcript_path"] == default_agent_transcript_path("builder-1")
    assert agent["spawned_by"] == "event"


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

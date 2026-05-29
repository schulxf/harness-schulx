"""Hub agent registry helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.paths import agent_registry_path
from harness_core.storage import read_json, write_json


def load_agent_registry(root: Path) -> dict[str, Any]:
    return read_json(agent_registry_path(root), {"agents": []})


def save_agent_registry(root: Path, registry: dict[str, Any]) -> None:
    write_json(agent_registry_path(root), registry)


def agent_status_from_state(state: str) -> str:
    if state in {"idle", "done", "blocked"}:
        return state
    return "working"


def upsert_agent(
    root: Path,
    agent_id: str,
    *,
    name: str,
    role: str,
    state: str,
    task_id: str = "",
    task_title: str = "",
    phase: str = "",
    speech: str = "",
    run_dir: str = "",
    surface_id: str = "",
    event_id: str = "",
) -> dict[str, Any]:
    registry = load_agent_registry(root)
    agents = [agent for agent in registry.get("agents", []) if isinstance(agent, dict)]
    now = utc_now()
    found: dict[str, Any] | None = None
    for agent in agents:
        if agent.get("id") == agent_id:
            found = agent
            break
    if not found:
        found = {"id": agent_id, "created_at": now}
        agents.append(found)
    found.update(
        {
            "name": name,
            "role": role,
            "state": state,
            "status": agent_status_from_state(state),
            "task_id": task_id,
            "task_title": task_title,
            "phase": phase or role,
            "speech": speech,
            "run_dir": run_dir,
            "surface_id": surface_id or found.get("surface_id", ""),
            "last_event_id": event_id or found.get("last_event_id", ""),
            "heartbeat_at": now,
            "updated_at": now,
        }
    )
    registry["agents"] = agents
    registry["updated_at"] = now
    save_agent_registry(root, registry)
    return found


def load_hub_agents(root: Path) -> list[dict[str, Any]]:
    agents = [agent for agent in load_agent_registry(root).get("agents", []) if isinstance(agent, dict)]
    if not agents:
        return []
    active_states = {"working", "idle", "blocked"}
    return [
        agent
        for agent in agents
        if str(agent.get("state") or agent.get("status") or "idle") in active_states
    ][-8:]

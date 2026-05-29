"""Hub agent registry helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.defaults import DEFAULT_HUB_CONFIG
from harness_core.hub_agents import sector_for_role
from harness_core.paths import agent_registry_path
from harness_core.storage import read_json, write_json


def default_agent_transcript_path(agent_id: str) -> str:
    return f".harness/agents/{agent_id}/transcript.jsonl"


def _repo_root_text(root: Path) -> str:
    return str(root.resolve(strict=False))


def normalize_agent_record(root: Path, agent: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(agent)
    agent_id = str(normalized.get("id") or "")
    role = str(normalized.get("role") or "")
    repo_root = _repo_root_text(root)
    normalized["cli"] = str(normalized.get("cli") or DEFAULT_HUB_CONFIG["default_cli"])
    normalized["sector"] = str(normalized.get("sector") or sector_for_role(role))
    normalized["pty_id"] = str(normalized.get("pty_id") or "")
    normalized["repo_root"] = str(normalized.get("repo_root") or repo_root)
    normalized["cwd"] = str(normalized.get("cwd") or normalized["repo_root"])
    normalized["transcript_path"] = str(
        normalized.get("transcript_path") or default_agent_transcript_path(agent_id)
    )
    normalized["spawned_by"] = str(
        normalized.get("spawned_by") or ("event" if normalized.get("last_event_id") else "ui")
    )
    return normalized


def load_agent_registry(root: Path) -> dict[str, Any]:
    registry = read_json(agent_registry_path(root), {"agents": []})
    if not isinstance(registry, dict):
        registry = {"agents": []}
    agents = [
        normalize_agent_record(root, agent)
        for agent in registry.get("agents", [])
        if isinstance(agent, dict)
    ]
    registry = dict(registry)
    registry["agents"] = agents
    return registry


def _preserve_or_default(
    found: dict[str, Any],
    key: str,
    value: str,
    default: str,
) -> str:
    return value or str(found.get(key) or default)


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
    cli: str = "",
    sector: str = "",
    pty_id: str = "",
    repo_root: str = "",
    cwd: str = "",
    transcript_path: str = "",
    spawned_by: str = "",
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
    previous_role = str(found.get("role") or "")
    default_repo_root = _repo_root_text(root)
    default_sector = (
        str(found.get("sector") or "")
        if previous_role == role and str(found.get("sector") or "")
        else sector_for_role(role)
    )
    resolved_repo_root = _preserve_or_default(found, "repo_root", repo_root, default_repo_root)
    resolved_cwd = _preserve_or_default(found, "cwd", cwd, resolved_repo_root)
    resolved_spawned_by = _preserve_or_default(
        found,
        "spawned_by",
        spawned_by,
        "event" if event_id else "ui",
    )
    found.update(
        {
            "name": name,
            "role": role,
            "state": state,
            "status": agent_status_from_state(state),
            "cli": _preserve_or_default(
                found,
                "cli",
                cli,
                str(DEFAULT_HUB_CONFIG["default_cli"]),
            ),
            "sector": sector or default_sector,
            "pty_id": _preserve_or_default(found, "pty_id", pty_id, ""),
            "repo_root": resolved_repo_root,
            "cwd": resolved_cwd,
            "transcript_path": _preserve_or_default(
                found,
                "transcript_path",
                transcript_path,
                default_agent_transcript_path(agent_id),
            ),
            "spawned_by": resolved_spawned_by,
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

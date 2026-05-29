"""Dashboard hub state collection and caching."""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from harness_core.agent_registry import load_hub_agents
from harness_core.artifacts import collect_run_artifacts
from harness_core.checkpoints import latest_checkpoint_summary
from harness_core.clock import utc_now
from harness_core.context_preflight import load_config
from harness_core.dashboard_hub import write_dashboard_hub_files
from harness_core.events import read_recent_harness_events
from harness_core.git_helpers import current_git_branch
from harness_core.hub_agents import (
    hub_agent_name_for_role,
    hub_agent_role_for_phase,
    hub_agent_speech,
    hub_agent_state_for_phase,
    hub_repo_phase,
)
from harness_core.paths import config_path, dashboard_hub_root, normalize_path_key, security_root
from harness_core.queue_state import load_queue, sorted_queue_items
from harness_core.run_state import find_unevaluated_runs, latest_run_dir_or_none
from harness_core.status import (
    QUEUE_STATUS_ACTIVE,
    QUEUE_STATUS_DONE,
    QUEUE_STATUS_QUEUED,
    TASK_STATUS_SENSORS_PASSED,
    TASK_STATUSES_COMPLETE,
    TASK_STATUSES_WORKING,
)
from harness_core.storage import read_json
from harness_core.task_store import load_tasks
from harness_core.wmux import collect_wmux_state

HUB_REPO_STATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def collect_hub_repo_state_cached(root: Path, index: int = 0, ttl_seconds: float = 0.0) -> dict[str, Any]:
    if ttl_seconds <= 0:
        return collect_hub_repo_state(root, index)
    key = f"{normalize_path_key(root)}::{index}"
    now = time.monotonic()
    cached = HUB_REPO_STATE_CACHE.get(key)
    if cached and cached[0] > now:
        return copy.deepcopy(cached[1])
    state = collect_hub_repo_state(root, index)
    HUB_REPO_STATE_CACHE[key] = (now + ttl_seconds, copy.deepcopy(state))
    return state


def collect_hub_repo_state(root: Path, index: int = 0) -> dict[str, Any]:
    if not root.exists() or not root.is_dir():
        return {
            "index": index,
            "project": root.name,
            "root": str(root),
            "error": "repo_missing",
            "phase": "offline",
            "tasks": [],
            "queue": [],
            "agents": [],
        }
    if not config_path(root).exists():
        return {
            "index": index,
            "project": root.name,
            "root": str(root),
            "error": "harness_not_initialized",
            "phase": "offline",
            "tasks": [],
            "queue": [],
            "agents": [],
        }
    config = load_config(root)
    tasks = load_tasks(root)
    queue = sorted_queue_items(load_queue(root))
    security_report = read_json(security_root(root) / "scan-latest.json", {})
    active = next((item for item in queue if item.get("status") == QUEUE_STATUS_ACTIVE), None)
    active_task_id = str(active.get("task_id") or "") if active else ""
    active_task = next((task for task in tasks if task.get("task_id") == active_task_id), None)
    if not active_task:
        active_task = next((task for task in tasks if task.get("status") in TASK_STATUSES_WORKING), None)
        active_task_id = str(active_task.get("task_id") or "") if active_task else ""
    phase = hub_repo_phase(tasks, queue, security_report)
    if not active_task:
        phase_statuses = {
            "review": {TASK_STATUS_SENSORS_PASSED},
            "report": TASK_STATUSES_COMPLETE,
        }.get(phase, set())
        active_task = next(
            (task for task in reversed(tasks) if task.get("status") in phase_statuses),
            None,
        )
        active_task_id = str(active_task.get("task_id") or "") if active_task else ""
    latest_run = latest_run_dir_or_none(root, active_task_id) if active_task_id else None
    role = hub_agent_role_for_phase(phase)
    agent_state = hub_agent_state_for_phase(phase, active_task_id)
    registry_agents = load_hub_agents(root)
    agents = registry_agents or [
        {
            "id": f"{index}-{role}",
            "name": hub_agent_name_for_role(role),
            "role": role,
            "state": agent_state,
            "task_id": active_task_id,
            "task_title": active_task.get("title") if active_task else "",
            "phase": phase,
            "speech": hub_agent_speech(phase, active_task, queue, security_report),
            "synthetic": True,
        }
    ]
    events = read_recent_harness_events(root, limit=30)
    return {
        "index": index,
        "project": config.get("project_name") or root.name,
        "root": str(root),
        "branch": current_git_branch(root),
        "phase": phase,
        "active_profile": config.get("active_profile", "balanced"),
        "active_task": active_task,
        "active_queue": active,
        "latest_run": str(latest_run) if latest_run else "",
        "latest_checkpoint": latest_checkpoint_summary(root, active_task_id),
        "counts": {
            "tasks": len(tasks),
            "queued": len([item for item in queue if item.get("status") == QUEUE_STATUS_QUEUED]),
            "active": len([item for item in queue if item.get("status") == QUEUE_STATUS_ACTIVE]),
            "done": len([item for item in queue if item.get("status") == QUEUE_STATUS_DONE]),
            "security_findings": len(security_report.get("findings") or []),
            "artifacts": len(collect_run_artifacts(root)),
            "unevaluated_runs": len(find_unevaluated_runs(root)),
        },
        "tasks": tasks[-10:],
        "queue": queue[-10:],
        "security": security_report,
        "agents": agents,
        "events": events,
    }


def collect_dashboard_hub_state(
    paths: list[Path],
    action_token: str = "",
    cache_ttl_seconds: float = 0.0,
) -> dict[str, Any]:
    repos = [
        collect_hub_repo_state_cached(path, index, cache_ttl_seconds)
        for index, path in enumerate(paths)
    ]
    return {
        "generated_at": utc_now(),
        "repo_count": len(repos),
        "active_repos": len([repo for repo in repos if repo.get("phase") not in {"idle", "offline"}]),
        "total_tasks": sum(int(repo.get("counts", {}).get("tasks") or 0) for repo in repos),
        "total_findings": sum(int(repo.get("counts", {}).get("security_findings") or 0) for repo in repos),
        "repos": repos,
        "wmux": collect_wmux_state(),
        "action_token": action_token,
    }


def write_dashboard_hub(root: Path, paths: list[Path], refresh_seconds: int = 3) -> dict[str, Any]:
    state = collect_dashboard_hub_state(paths)
    target = dashboard_hub_root(root)
    write_dashboard_hub_files(target, state, refresh_seconds)
    return {"state": state, "path": target / "index.html", "state_path": target / "hub-state.json"}

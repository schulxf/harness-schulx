"""Hub phase and avatar state helpers."""

from __future__ import annotations

from typing import Any

from harness_core.status import (
    QUEUE_STATUS_ACTIVE,
    QUEUE_STATUS_QUEUED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NEEDS_WORK,
    TASK_STATUS_SENSORS_PASSED,
    TASK_STATUSES_COMPLETE,
    TASK_STATUSES_WORKING,
)

ROLE_SECTORS = {
    "planner": "plan",
    "architect": "plan",
    "builder": "implement",
    "developer": "implement",
    "implementer": "implement",
    "coder": "implement",
    "reviewer": "review",
    "evaluator": "review",
    "research": "research",
    "researcher": "research",
    "security": "security",
    "auditor": "security",
    "sentinel": "security",
    "reporter": "report",
    "archivist": "report",
}


def sector_for_role(role: str) -> str:
    return ROLE_SECTORS.get(str(role or "").strip().lower(), "idle")


def sector_for_event(event_type: str, payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    event_type = str(event_type or "").strip().lower()
    if event_type == "agent_sector_changed":
        return str(payload.get("sector") or "idle")
    if event_type == "agent_spawned":
        return sector_for_role(str(payload.get("role") or ""))
    if event_type.startswith("security_") or event_type in {"security_scan", "security_finding"}:
        return "security"
    if event_type in {"task_created", "queue_item_added", "queue_item_activated"}:
        return "plan"
    if event_type.startswith("contract_"):
        return "plan"
    if event_type in {"run_started", "fix_brief_created"} or event_type.startswith("sensors_"):
        return "implement"
    if event_type == "evaluation_brief_created":
        return "review"
    if event_type == "evaluation_recorded":
        return "report" if payload.get("status") == "pass" else "implement"
    if event_type == "report_created":
        return "report"
    return "idle"


def hub_repo_phase(tasks: list[dict[str, Any]], queue: list[dict[str, Any]], security: dict[str, Any]) -> str:
    if security.get("findings"):
        return "security"
    active = next((item for item in queue if item.get("status") == QUEUE_STATUS_ACTIVE), None)
    active_task = None
    if active and active.get("task_id"):
        active_task = next((task for task in tasks if task.get("task_id") == active.get("task_id")), None)
    if active_task:
        status = str(active_task.get("status") or "")
        if status in TASK_STATUSES_WORKING:
            return "build"
        if status == TASK_STATUS_SENSORS_PASSED:
            return "review"
        if status in TASK_STATUSES_COMPLETE:
            return "report"
    if any(task.get("status") in {TASK_STATUS_IN_PROGRESS, TASK_STATUS_NEEDS_WORK} for task in tasks):
        return "build"
    if any(task.get("status") == TASK_STATUS_SENSORS_PASSED for task in tasks):
        return "review"
    if any(item.get("status") == QUEUE_STATUS_QUEUED for item in queue):
        return "queue"
    if any(task.get("status") in TASK_STATUSES_COMPLETE for task in tasks):
        return "report"
    return "idle"


def hub_agent_role_for_phase(phase: str) -> str:
    if phase == "review":
        return "reviewer"
    if phase == "security":
        return "security"
    if phase == "report":
        return "reporter"
    if phase == "build":
        return "builder"
    return "operator"


def hub_agent_name_for_role(role: str) -> str:
    return {
        "builder": "Builder",
        "reviewer": "Reviewer",
        "security": "Sentinel",
        "reporter": "Archivist",
        "operator": "Operator",
    }.get(role, "Operator")


def hub_agent_state_for_phase(phase: str, active_task_id: str) -> str:
    if active_task_id and phase in {"build", "review", "security", "report"}:
        return "working"
    return "idle"


def hub_agent_speech(
    phase: str,
    task: dict[str, Any] | None,
    queue: list[dict[str, Any]],
    security_report: dict[str, Any],
) -> str:
    task_id = str((task or {}).get("task_id") or "")
    title = str((task or {}).get("title") or "").strip()
    task_label = f"{task_id}: {title}" if task_id and title else task_id or title
    if phase == "security":
        count = len(security_report.get("findings") or [])
        return f"Encontrei {count} alerta(s) de seguranca." if count else "Conferindo seguranca."
    if phase == "review":
        return f"Revisando {task_label}." if task_label else "Preparando revisao."
    if phase == "report":
        return f"Fechando relatorio de {task_label}." if task_label else "Organizando relatorios."
    if phase == "build":
        return f"Trabalhando em {task_label}." if task_label else "Implementando a task ativa."
    queued = len([item for item in queue if item.get("status") == QUEUE_STATUS_QUEUED])
    if queued:
        return f"Livre. {queued} item(ns) na fila."
    return "Livre. Patrulhando o laboratorio."

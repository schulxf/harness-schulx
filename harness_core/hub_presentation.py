"""Non-technical project presentation data for the Harness dashboard."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_core.paths import contract_file_path
from harness_core.run_state import latest_run_dir_or_none
from harness_core.storage import read_json, read_text

COMPLETE_STATUSES = {"passed", "done"}
ATTENTION_STATUSES = {"failed", "needs_work", "review_followup", "sensors_failed"}
WORKING_STATUSES = {"in_progress", *ATTENTION_STATUSES}
REVIEW_STATUSES = {"sensors_passed"}


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or fallback


def _ensure_period(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return text if text[-1] in ".!?" else f"{text}."


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_iso(values: list[Any]) -> str:
    parsed = [item for item in (_parse_time(value) for value in values) if item]
    return max(parsed).isoformat().replace("+00:00", "Z") if parsed else ""


def _markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text or "")
    if not match:
        return ""
    body = match.group(1).strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    return _clean_text(paragraphs[0]) if paragraphs else ""


def _task_file_text(root: Path, task: dict[str, Any]) -> str:
    relative = str(task.get("task_file") or "").strip()
    if not relative:
        return ""
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return ""
    return read_text(candidate) if candidate.is_file() else ""


def _task_contract(root: Path, task_id: str) -> dict[str, Any]:
    path = contract_file_path(root, task_id)
    return read_json(path, {}) if path.is_file() else {}


def _task_result(root: Path, task: dict[str, Any]) -> str:
    task_id = str(task.get("task_id") or "")
    run_dir = latest_run_dir_or_none(root, task_id) if task_id else None
    if run_dir:
        plain = run_dir / "plain-summary.md"
        if plain.is_file():
            text = read_text(plain)
            result = _markdown_section(text, "Resultado") or _markdown_section(text, "O que foi feito")
            if result:
                return _ensure_period(result)
        evaluation = read_json(run_dir / "evaluation.json", {})
        notes = _clean_text(evaluation.get("notes"))
        if notes:
            return _ensure_period(notes)
    return "A task foi concluída e conferida."


def _task_description(root: Path, task: dict[str, Any]) -> str:
    direct = _clean_text(task.get("description") or task.get("body"))
    if direct:
        return _ensure_period(direct)
    section = _markdown_section(_task_file_text(root, task), "O que construir")
    if section:
        return _ensure_period(section)
    title = _clean_text(task.get("title"), "esta etapa")
    return f"O trabalho desta etapa é {title.lower()}."


def _task_state(status: Any, current_task_id: str) -> str:
    normalized = str(status or "planned").lower()
    if normalized in COMPLETE_STATUSES:
        return "done"
    if current_task_id and normalized in WORKING_STATUSES | REVIEW_STATUSES:
        return "doing"
    return "waiting"


def _event_message(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    messages = {
        "task_created": "Uma nova task foi preparada.",
        "queue_item_added": "A task entrou na sequência de trabalho.",
        "queue_item_activated": "O trabalho da task começou.",
        "run_started": "A implementação desta task começou.",
        "sensors_completed": (
            "A conferência terminou sem encontrar problemas."
            if payload.get("passed")
            else "A conferência encontrou pontos que precisam de ajuste."
        ),
        "evaluation_brief_created": "O resultado ficou pronto para revisão.",
        "evaluation_recorded": (
            "A revisão confirmou que a task está pronta."
            if str(payload.get("status") or "").lower() == "pass"
            else "A revisão pediu alguns ajustes antes da conclusão."
        ),
        "fix_brief_created": "Os ajustes necessários foram organizados.",
        "report_created": "O resultado final da task foi registrado.",
        "agent_done": "O trabalho desta etapa foi encerrado.",
    }
    return messages.get(event_type, "")


def _recent_updates(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    for event in reversed(events):
        message = _event_message(event)
        if not message:
            continue
        updates.append({"at": str(event.get("ts") or ""), "text": message})
        if len(updates) == 4:
            break
    return updates


def _stage_for(status: str, events: list[dict[str, Any]], completed: bool) -> int:
    if completed:
        return 4
    event_types = {str(event.get("type") or "") for event in events[-8:]}
    if status in REVIEW_STATUSES:
        return 3 if "evaluation_brief_created" in event_types else 2
    if status in ATTENTION_STATUSES and "sensors_completed" in event_types:
        return 2
    if status in WORKING_STATUSES:
        return 1
    return 0


def unavailable_presentation(project: str, error: str = "") -> dict[str, Any]:
    message = (
        "Este projeto ainda não foi preparado para o acompanhamento."
        if error == "harness_not_initialized"
        else "Não foi possível receber informações deste projeto no momento."
    )
    return {
        "id": project,
        "status": "indisponivel",
        "status_label": "Indisponível",
        "implementation": "Informações temporariamente indisponíveis",
        "summary": "",
        "situation": "Indisponível",
        "updated_at": "",
        "stage": 0,
        "tasks": [],
        "current": None,
        "last_completed": None,
        "recent_updates": [],
        "unavailable_message": message,
    }


def build_project_presentation(
    root: Path,
    config: dict[str, Any],
    tasks: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    events: list[dict[str, Any]],
    security: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable, human-readable view from Harness state."""

    security = security or {}
    queue_ids = [str(item.get("task_id") or "") for item in queue if item.get("task_id")]
    task_by_id = {str(task.get("task_id") or ""): task for task in tasks}
    ordered = [task_by_id[task_id] for task_id in queue_ids if task_id in task_by_id]
    ordered.extend(task for task in tasks if task not in ordered)

    active_queue = next((item for item in queue if str(item.get("status")) == "active"), None)
    active_id = str((active_queue or {}).get("task_id") or "")
    current = task_by_id.get(active_id)
    if current is None:
        current = next(
            (
                task
                for task in ordered
                if str(task.get("status") or "") in WORKING_STATUSES | REVIEW_STATUSES
            ),
            None,
        )
    if current is None and ordered:
        current = next(
            (task for task in ordered if str(task.get("status") or "") not in COMPLETE_STATUSES),
            ordered[-1],
        )
    current_id = str((current or {}).get("task_id") or "")
    current_status = str((current or {}).get("status") or "planned").lower()

    details: list[dict[str, Any]] = []
    for index, task in enumerate(ordered, start=1):
        task_id = str(task.get("task_id") or "")
        status = str(task.get("status") or "planned").lower()
        state = _task_state(status, current_id if task_id == current_id else "")
        details.append(
            {
                "id": task_id,
                "number": index,
                "title": _clean_text(task.get("title"), f"Task {index}"),
                "description": _task_description(root, task),
                "state": state,
                "result": _task_result(root, task) if state == "done" else "",
                "updated_at": str(task.get("updated_at") or task.get("created_at") or ""),
            }
        )

    completed = bool(details) and all(item["state"] == "done" for item in details)
    recent = _recent_updates(events)
    findings = list(security.get("findings") or [])
    blocked_queue = next((item for item in queue if str(item.get("status")) == "blocked"), None)
    needs_attention = current_status in ATTENTION_STATUSES or bool(findings) or blocked_queue is not None
    if completed:
        status = "concluido"
    elif needs_attention:
        status = "atencao"
    elif current_status in REVIEW_STATUSES:
        status = "revisao" if any(event.get("type") == "evaluation_brief_created" for event in events[-8:]) else "conferencia"
    else:
        status = "andamento"

    status_label = {
        "andamento": "Em andamento",
        "conferencia": "Em conferência",
        "revisao": "Em revisão",
        "atencao": "Precisa de atenção",
        "concluido": "Concluído",
    }[status]
    stage = _stage_for(current_status, events, completed)
    stage_labels = ["Preparando", "Construindo", "Conferindo", "Revisando", "Concluído"]

    hub_config = config.get("hub") if isinstance(config.get("hub"), dict) else {}
    contract = _task_contract(root, current_id) if current_id else {}
    current_title = _clean_text((current or {}).get("title"), "Acompanhamento da implementação")
    implementation = _clean_text(
        hub_config.get("implementation_name")
        or config.get("implementation_name")
        or (current or {}).get("implementation")
        or current_title,
        "Implementação em acompanhamento",
    )
    goal = _clean_text(contract.get("goal") or (current or {}).get("goal") or current_title)
    summary = _ensure_period(
        _clean_text(
            hub_config.get("implementation_summary")
            or config.get("implementation_summary")
            or goal,
            f"Acompanhar a implementação {implementation.lower()}",
        )
    )
    criteria = [
        _ensure_period(_clean_text(item))
        for item in contract.get("acceptance_criteria", [])
        if _clean_text(item)
    ]
    current_detail = next((item for item in details if item["id"] == current_id), None)
    last_update = recent[0]["text"] if recent else "O acompanhamento está aguardando uma nova atualização."
    if completed:
        what_doing = "Todas as tasks desta implementação foram concluídas e conferidas."
        when_done = "A implementação está pronta para a próxima decisão da equipe."
        remaining = "Nada ficou pendente."
    else:
        what_doing = (current_detail or {}).get("description") or f"O trabalho atual é {current_title.lower()}."
        when_done = criteria[0] if criteria else f"A task {current_title.lower()} ficará pronta para conferência."
        remaining = (
            "Falta conferir: " + " ".join(criteria[:3])
            if criteria
            else "Falta concluir esta task e conferir o resultado."
        )

    blocker = None
    if needs_attention:
        if findings:
            blocker_message = "A conferência encontrou um problema que precisa ser corrigido antes da conclusão."
        elif blocked_queue:
            blocker_message = "O trabalho está aguardando a resolução de um bloqueio antes de continuar."
        else:
            blocker_message = "A conferência encontrou pontos que precisam de ajuste. O trabalho de correção está em andamento."
        blocker = {"title": "Precisa de atenção", "message": blocker_message}

    completed_items = [item for item in details if item["state"] == "done"]
    last_completed = completed_items[-1] if completed_items else None
    updated_at = _latest_iso(
        [
            *(task.get("updated_at") or task.get("created_at") for task in tasks),
            *(event.get("ts") for event in events),
        ]
    )

    return {
        "status": status,
        "status_label": status_label,
        "implementation": implementation,
        "summary": summary,
        "situation": stage_labels[stage] if status != "atencao" else "Precisa de atenção",
        "updated_at": updated_at,
        "stage": stage,
        "tasks": details,
        "current": {
            "id": current_id,
            "number": (current_detail or {}).get("number", len(details) or 1),
            "total": len(details),
            "title": current_title,
            "what_doing": _ensure_period(what_doing),
            "why": _ensure_period(f"Isso está sendo feito para {goal.lower()}") if goal else summary,
            "when_done": _ensure_period(when_done),
            "last_update": last_update,
            "remaining": _ensure_period(remaining),
        },
        "last_completed": (
            {
                "title": last_completed["title"],
                "result": last_completed["result"],
                "completed_at": last_completed["updated_at"],
            }
            if last_completed
            else None
        ),
        "recent_updates": recent,
        "blocker": blocker,
        "stale_after_seconds": 300,
    }

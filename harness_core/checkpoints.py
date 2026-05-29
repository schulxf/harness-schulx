"""Checkpoint persistence and resume brief helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.git_helpers import git_output, is_git_repo
from harness_core.paths import checkpoints_root, contract_file_path
from harness_core.queue_state import active_queue_item
from harness_core.run_state import latest_run_dir_or_none
from harness_core.sensors import fastest_available_sensor_tier
from harness_core.status import (
    TASK_STATUS_SENSORS_PASSED,
    TASK_STATUSES_COMPLETE,
    TASK_STATUSES_READY_TO_START,
    TASK_STATUSES_WORKING,
)
from harness_core.storage import read_json, write_json
from harness_core.task_store import find_task


def create_checkpoint(
    root: Path,
    task_id: str,
    reason: str,
    run_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    task = find_task(root, task_id)
    run_dir = run_dir or latest_run_dir_or_none(root, task_id)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "title": task.get("title"),
        "task_status": task.get("status"),
        "reason": reason,
        "created_at": utc_now(),
        "run_dir": str(run_dir) if run_dir else None,
        "contract_exists": contract_file_path(root, task_id).exists(),
        "git_status": git_output(root, ["status", "--short"]) if is_git_repo(root) else "",
        "queue": active_queue_item(root),
        "budget": task.get("budget", {}),
    }
    if run_dir:
        for name in ["sensors.json", "evaluation.json"]:
            path = run_dir / name
            if path.exists():
                payload[name.removesuffix(".json")] = read_json(path, {})
    if extra:
        payload.update(extra)
    root_dir = checkpoints_root(root, task_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root_dir / f"checkpoint-{stamp}.json"
    write_json(path, payload)
    write_json(root_dir / "latest.json", payload)
    return path


def latest_checkpoint_path(root: Path, task_id: str) -> Path | None:
    latest = checkpoints_root(root, task_id) / "latest.json"
    if latest.exists():
        return latest
    paths = sorted(checkpoints_root(root, task_id).glob("checkpoint-*.json"))
    return paths[-1] if paths else None


def latest_checkpoint_summary(root: Path, task_id: str | None) -> str:
    if not task_id:
        return ""
    path = latest_checkpoint_path(root, task_id)
    if not path:
        return ""
    payload = read_json(path, {})
    return str(payload.get("summary") or payload.get("reason") or payload.get("created_at") or "")


def render_resume_brief(
    root: Path,
    task_id: str,
    checkpoint: dict[str, Any],
    *,
    harness_script: Path | None = None,
) -> str:
    script = harness_script or Path("bin/harness.py")
    task = find_task(root, task_id)
    contract = read_json(contract_file_path(root, task_id), {}) if contract_file_path(root, task_id).exists() else {}
    run_dir = checkpoint.get("run_dir") or "sem run ainda"
    next_steps = []
    status = task.get("status")
    if not contract:
        next_steps.append(f"1. Criar contrato: python {script} --repo {root} contract {task_id}")
    elif status in TASK_STATUSES_READY_TO_START:
        next_steps.append(f"1. Iniciar run: python {script} --repo {root} start {task_id}")
    elif status in TASK_STATUSES_WORKING:
        tier = fastest_available_sensor_tier(contract)
        next_steps.append(
            f"1. Rodar sensores rapidos: python {script} --repo {root} sensors {task_id} --tier {tier} --reviewed"
        )
        next_steps.append(f"2. Gerar avaliacao/review: python {script} --repo {root} evaluate {task_id}")
    elif status == TASK_STATUS_SENSORS_PASSED:
        next_steps.append(f"1. Registrar avaliacao ou gerar handoffs: python {script} --repo {root} evaluate {task_id}")
    elif status in TASK_STATUSES_COMPLETE:
        next_steps.append(f"1. Gerar relatorio: python {script} --repo {root} report {task_id}")
    else:
        next_steps.append("1. Rodar `status` e decidir a proxima etapa.")
    return (
        f"# Resume brief - {task_id}\n\n"
        f"Task: {task.get('title')}\n"
        f"Status atual: {status}\n"
        f"Checkpoint: {checkpoint.get('created_at')}\n"
        f"Motivo: {checkpoint.get('reason')}\n"
        f"Run: {run_dir}\n\n"
        "## Proximo passo recomendado\n\n"
        f"{chr(10).join(next_steps)}\n\n"
        "## Status do Git no checkpoint\n\n"
        f"```text\n{checkpoint.get('git_status') or 'sem status registrado'}\n```\n"
    )

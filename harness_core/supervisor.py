from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import load_contract
from .paths import contract_file_path
from .sensors import fastest_available_sensor_tier
from .status import (
    TASK_STATUS_SENSORS_PASSED,
    TASK_STATUSES_COMPLETE,
    TASK_STATUSES_READY_TO_START,
    TASK_STATUSES_WORKING,
)
from .task_store import find_task

HARNESS_CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "harness.py"


def supervisor_recommendation(root: Path, item: dict[str, Any]) -> str:
    task_id = item.get("task_id")
    if not task_id:
        return "Item de fila sem task. Use `queue add --create-task` ou crie uma task a partir do corpo."
    task = find_task(root, task_id)
    status = task.get("status")
    if not contract_file_path(root, task_id).exists():
        return f"Criar contrato: python {HARNESS_CLI_PATH} --repo {root} contract {task_id}"
    if status in TASK_STATUSES_READY_TO_START:
        return f"Iniciar: python {HARNESS_CLI_PATH} --repo {root} start {task_id}"
    if status in TASK_STATUSES_WORKING:
        contract = load_contract(root, task_id)
        tier = fastest_available_sensor_tier(contract)
        return f"Rodar sensores: python {HARNESS_CLI_PATH} --repo {root} sensors {task_id} --tier {tier} --reviewed"
    if status == TASK_STATUS_SENSORS_PASSED:
        return f"Avaliar: python {HARNESS_CLI_PATH} --repo {root} evaluate {task_id}"
    if status in TASK_STATUSES_COMPLETE:
        return f"Fechar fila: python {HARNESS_CLI_PATH} --repo {root} queue done {item.get('id')}"
    return "Revisar status manualmente."

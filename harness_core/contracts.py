"""Contract file helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.paths import contract_file_path
from harness_core.storage import read_json
from harness_core.task_store import find_task


def task_file_path(root: Path, task_id: str) -> Path:
    task = find_task(root, task_id)
    return root / task["task_file"]


def load_contract(root: Path, task_id: str) -> dict[str, Any]:
    path = contract_file_path(root, task_id)
    if not path.exists():
        raise SystemExit(f"Contrato nao encontrado para {task_id}. Rode: harness contract {task_id}")
    return read_json(path, {})

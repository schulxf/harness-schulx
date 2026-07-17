from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.contracts import load_contract, task_file_path
from harness_core.paths import contract_file_path, tasks_index_path
from harness_core.storage import write_json


def test_task_file_path_resolves_from_task_index(tmp_path: Path) -> None:
    write_json(
        tasks_index_path(tmp_path),
        [{"task_id": "TASK-001", "task_file": ".harness/tasks/TASK-001.md"}],
    )

    assert task_file_path(tmp_path, "TASK-001") == tmp_path / ".harness" / "tasks" / "TASK-001.md"


def test_load_contract_reads_existing_contract(tmp_path: Path) -> None:
    write_json(contract_file_path(tmp_path, "TASK-001"), {"task_id": "TASK-001", "ok": True})

    assert load_contract(tmp_path, "TASK-001") == {"task_id": "TASK-001", "ok": True}


def test_load_contract_explains_missing_contract(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Contrato nao encontrado para TASK-001"):
        load_contract(tmp_path, "TASK-001")

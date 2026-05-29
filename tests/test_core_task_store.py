from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.task_store import (
    find_task,
    load_tasks,
    next_task_id,
    save_tasks,
    update_task,
)


def test_task_store_round_trip(tmp_path: Path) -> None:
    tasks = [{"task_id": "TASK-001", "title": "First"}]

    save_tasks(tmp_path, tasks)

    assert load_tasks(tmp_path) == tasks


def test_find_task_returns_matching_record(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {"task_id": "TASK-001", "title": "First"},
            {"task_id": "TASK-002", "title": "Second"},
        ],
    )

    assert find_task(tmp_path, "TASK-002")["title"] == "Second"


def test_find_task_raises_for_missing_task(tmp_path: Path) -> None:
    save_tasks(tmp_path, [])

    with pytest.raises(SystemExit, match="Task nao encontrada: TASK-999"):
        find_task(tmp_path, "TASK-999")


def test_update_task_persists_updates_and_timestamp(tmp_path: Path) -> None:
    save_tasks(tmp_path, [{"task_id": "TASK-001", "title": "First", "status": "planned"}])

    update_task(tmp_path, "TASK-001", status="in_progress")

    task = find_task(tmp_path, "TASK-001")
    assert task["status"] == "in_progress"
    assert "updated_at" in task


def test_next_task_id_ignores_nonstandard_ids(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {"task_id": "TASK-001"},
            {"task_id": "TASK-010"},
            {"task_id": "external-5"},
        ],
    )

    assert next_task_id(tmp_path) == "TASK-011"


def test_next_task_id_starts_at_one(tmp_path: Path) -> None:
    save_tasks(tmp_path, [])

    assert next_task_id(tmp_path) == "TASK-001"

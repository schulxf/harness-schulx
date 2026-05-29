"""Task index persistence helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.paths import tasks_index_path
from harness_core.records import TaskRecord
from harness_core.storage import read_json, write_json


def load_tasks(root: Path) -> list[TaskRecord]:
    return read_json(tasks_index_path(root), [])


def save_tasks(root: Path, tasks: list[TaskRecord]) -> None:
    write_json(tasks_index_path(root), tasks)


def find_task(root: Path, task_id: str) -> TaskRecord:
    for task in load_tasks(root):
        if task["task_id"] == task_id:
            return task
    raise SystemExit(f"Task nao encontrada: {task_id}")


def update_task(root: Path, task_id: str, **updates: Any) -> None:
    tasks = load_tasks(root)
    for task in tasks:
        if task["task_id"] == task_id:
            task.update(updates)
            task["updated_at"] = utc_now()
            save_tasks(root, tasks)
            return
    raise SystemExit(f"Task nao encontrada: {task_id}")


def next_task_id(root: Path) -> str:
    numbers = []
    for task in load_tasks(root):
        match = re.match(r"TASK-(\d+)$", task["task_id"])
        if match:
            numbers.append(int(match.group(1)))
    return f"TASK-{(max(numbers) + 1) if numbers else 1:03d}"

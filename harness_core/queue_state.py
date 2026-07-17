"""Queue record persistence and selection rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.paths import queue_path
from harness_core.records import QueueRecord
from harness_core.status import QUEUE_STATUS_ACTIVE, QUEUE_STATUS_QUEUED
from harness_core.storage import read_json, state_lock, write_json


def next_queue_id(root: Path) -> str:
    return next_queue_id_from(load_queue(root))


def next_queue_id_from(items: list[QueueRecord]) -> str:
    numbers = []
    for item in items:
        value = str(item.get("id", ""))
        if value.startswith("QUEUE-") and value[6:].isdigit():
            numbers.append(int(value[6:]))
    return f"QUEUE-{(max(numbers) + 1) if numbers else 1:03d}"


def load_queue(root: Path) -> list[QueueRecord]:
    return read_json(queue_path(root), [])


def save_queue(root: Path, items: list[QueueRecord]) -> None:
    write_json(queue_path(root), items)


def queue_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in load_queue(root):
        status = str(item.get("status") or QUEUE_STATUS_QUEUED)
        counts[status] = counts.get(status, 0) + 1
    return counts


def sorted_queue_items(items: list[QueueRecord]) -> list[QueueRecord]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def next_queued_item(root: Path) -> QueueRecord | None:
    for item in sorted_queue_items(load_queue(root)):
        if item.get("status") == QUEUE_STATUS_QUEUED:
            return item
    return None


def active_queue_item(root: Path) -> QueueRecord | None:
    for item in sorted_queue_items(load_queue(root)):
        if item.get("status") == QUEUE_STATUS_ACTIVE:
            return item
    return None


def update_queue_item(root: Path, item_id: str, **updates: Any) -> QueueRecord:
    with state_lock(root, "queue"):
        items = load_queue(root)
        for item in items:
            if item.get("id") == item_id:
                item.update(updates)
                item["updated_at"] = utc_now()
                save_queue(root, items)
                return item
    raise SystemExit(f"Item de fila nao encontrado: {item_id}")

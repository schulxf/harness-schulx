from __future__ import annotations

from pathlib import Path

import pytest

from harness_core import queue_state


def test_queue_counts_defaults_missing_status_to_queued(tmp_path: Path) -> None:
    queue_state.save_queue(
        tmp_path,
        [
            {"id": "QUEUE-001", "status": "active"},
            {"id": "QUEUE-002"},
            {"id": "QUEUE-003", "status": "done"},
        ],
    )

    assert queue_state.queue_counts(tmp_path) == {"active": 1, "queued": 1, "done": 1}


def test_sorted_queue_items_uses_priority_created_at_and_id() -> None:
    items = [
        {"id": "QUEUE-003", "priority": 2, "created_at": "2026-01-02"},
        {"id": "QUEUE-002", "priority": 1, "created_at": "2026-01-02"},
        {"id": "QUEUE-001", "priority": 1, "created_at": "2026-01-01"},
    ]

    assert [item["id"] for item in queue_state.sorted_queue_items(items)] == [
        "QUEUE-001",
        "QUEUE-002",
        "QUEUE-003",
    ]


def test_active_and_next_queued_item_follow_sorted_order(tmp_path: Path) -> None:
    queue_state.save_queue(
        tmp_path,
        [
            {"id": "QUEUE-002", "status": "queued", "priority": 5},
            {"id": "QUEUE-001", "status": "queued", "priority": 1},
            {"id": "QUEUE-003", "status": "active", "priority": 10},
        ],
    )

    assert queue_state.next_queued_item(tmp_path)["id"] == "QUEUE-001"
    assert queue_state.active_queue_item(tmp_path)["id"] == "QUEUE-003"


def test_update_queue_item_persists_updates(tmp_path: Path) -> None:
    queue_state.save_queue(tmp_path, [{"id": "QUEUE-001", "status": "queued"}])

    item = queue_state.update_queue_item(tmp_path, "QUEUE-001", status="active")

    assert item["status"] == "active"
    assert item["updated_at"]
    assert queue_state.load_queue(tmp_path)[0]["status"] == "active"


def test_update_queue_item_errors_for_missing_item(tmp_path: Path) -> None:
    queue_state.save_queue(tmp_path, [])

    with pytest.raises(SystemExit, match="Item de fila nao encontrado"):
        queue_state.update_queue_item(tmp_path, "QUEUE-404", status="active")

from __future__ import annotations

from pathlib import Path

from harness_core.memory import load_memory, next_memory_id, render_memory_context, save_memory


def test_memory_round_trip(tmp_path: Path) -> None:
    entries = [{"id": "MEM-001", "text": "Prefer quick sensors", "tags": ["testing"]}]

    save_memory(tmp_path, entries)

    assert load_memory(tmp_path) == entries


def test_next_memory_id_increments_existing_numeric_ids(tmp_path: Path) -> None:
    save_memory(tmp_path, [{"id": "MEM-002"}, {"id": "manual"}, {"id": "MEM-010"}])

    assert next_memory_id(tmp_path) == "MEM-011"


def test_render_memory_context_filters_by_task_and_limits(tmp_path: Path) -> None:
    save_memory(
        tmp_path,
        [
            {"id": "MEM-001", "text": "Global note", "tags": ["global"]},
            {"id": "MEM-002", "text": "Task note", "task_id": "TASK-001", "tags": ["task"]},
            {"id": "MEM-003", "text": "Other note", "task_id": "TASK-002"},
        ],
    )

    rendered = render_memory_context(tmp_path, task_id="TASK-001", limit=2)

    assert "- Task note (TASK-001) [task]" in rendered
    assert "- Global note [global]" in rendered
    assert "Other note" not in rendered


def test_render_memory_context_empty_state(tmp_path: Path) -> None:
    assert render_memory_context(tmp_path) == "- Nenhuma memoria registrada ainda."

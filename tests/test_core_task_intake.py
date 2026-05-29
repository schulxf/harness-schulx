from pathlib import Path

from harness_core.events import read_recent_harness_events
from harness_core.storage import read_text
from harness_core.task_intake import (
    create_task,
    create_task_from_telegram_item,
    first_heading_or_filename,
    short_title,
)
from harness_core.task_store import load_tasks


def test_first_heading_or_filename_prefers_markdown_heading(tmp_path: Path) -> None:
    path = tmp_path / "fallback-name.md"

    assert first_heading_or_filename(path, "\n# Real title\nbody") == "Real title"


def test_first_heading_or_filename_falls_back_to_clean_filename(tmp_path: Path) -> None:
    path = tmp_path / "fallback-name_here.md"

    assert first_heading_or_filename(path, "body only") == "Fallback Name Here"


def test_short_title_uses_first_non_empty_clean_line() -> None:
    assert short_title("\n\n- `Implementar` tela nova") == "Implementar tela nova"


def test_create_task_writes_task_file_index_and_event(tmp_path: Path) -> None:
    task = create_task(tmp_path, "Nova Task", "Construir comportamento.", "manual")

    assert task["task_id"] == "TASK-001"
    assert task["status"] == "planned"
    assert load_tasks(tmp_path)[0]["title"] == "Nova Task"
    assert "Construir comportamento." in read_text(tmp_path / task["task_file"])
    events = read_recent_harness_events(tmp_path, limit=5)
    assert events[-1]["type"] == "task_created"
    assert events[-1]["task_id"] == "TASK-001"


def test_create_task_from_telegram_item_uses_prompt_and_origin(tmp_path: Path) -> None:
    task = create_task_from_telegram_item(
        tmp_path,
        {
            "id": "tg-1",
            "prompt_text": "Criar resumo via Telegram",
            "chat_id": "123",
            "message_id": 456,
            "media": [],
        },
    )

    assert task["title"] == "Criar resumo via Telegram"
    assert task["source"] == "telegram:tg-1"
    assert "Origem: telegram:tg-1" in read_text(tmp_path / task["task_file"])

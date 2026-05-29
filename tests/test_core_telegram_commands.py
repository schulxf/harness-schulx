from pathlib import Path

from harness_core.paths import config_path
from harness_core.storage import read_json, write_json
from harness_core.task_store import save_tasks
from harness_core.telegram_commands import (
    handle_telegram_command,
    handle_telegram_update,
    prepare_telegram_exec_update,
    telegram_status_summary,
    telegram_tasks_summary,
)


def test_telegram_tasks_summary_lists_recent_tasks(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Criar dashboard",
                "status": "planned",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )

    assert telegram_tasks_summary(tmp_path) == "Tasks:\n- TASK-001 [planned] Criar dashboard"


def test_telegram_status_summary_includes_project_and_tasks(tmp_path: Path) -> None:
    write_json(config_path(tmp_path), {"project_name": "Projeto Telegram"})
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Criar dashboard",
                "status": "planned",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )

    summary = telegram_status_summary(tmp_path)

    assert "Projeto: Projeto Telegram" in summary
    assert "TASK-001 [planned] Criar dashboard" in summary


def test_handle_telegram_command_new_creates_task_without_reply(tmp_path: Path) -> None:
    config = {"telegram": {"allow_task_creation": True, "allowed_chat_ids": ["123"]}}
    item = {"id": "tg-1", "chat_id": "123", "message_id": 1, "media": []}

    result = handle_telegram_command(tmp_path, config, "123", "/new Criar exportacao", item, False, reply=False)

    assert result["action"] == "task_created"
    assert result["created_task_id"] == "TASK-001"


def test_handle_telegram_update_rejects_unlisted_chat(tmp_path: Path) -> None:
    config = {"telegram": {"allowed_chat_ids": ["123"]}}

    path = handle_telegram_update(
        tmp_path,
        config,
        {
            "update_id": 1,
            "message": {
                "message_id": 2,
                "chat": {"id": 999},
                "from": {"id": 999},
                "text": "oi",
            },
        },
        reply=False,
    )

    assert path is not None
    assert read_json(path, {})["action"] == "rejected_chat"


def test_prepare_telegram_exec_update_extracts_codex_command_prompt(tmp_path: Path) -> None:
    config = {"telegram": {"allowed_chat_ids": ["123"]}}

    result = prepare_telegram_exec_update(
        tmp_path,
        config,
        {
            "update_id": 1,
            "message": {
                "message_id": 2,
                "chat": {"id": 123},
                "from": {"id": 123},
                "text": "/codex implementar relatorio",
            },
        },
        command_prefixes=("/codex",),
        download_media=False,
        reply_to_harness_commands=False,
    )

    assert result["ready"] is True
    assert result["prompt_text"] == "implementar relatorio"
    assert result["item"]["action"] == "inbox_saved"

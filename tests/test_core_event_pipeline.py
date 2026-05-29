from pathlib import Path

from harness_core.agent_registry import load_agent_registry
from harness_core.event_pipeline import sync_agent_from_event, telegram_event_message
from harness_core.paths import config_path, event_stream_path
from harness_core.storage import read_jsonl, write_json
from harness_core.task_store import save_tasks


def test_telegram_event_message_uses_project_and_report_summary(tmp_path: Path) -> None:
    write_json(config_path(tmp_path), {"project_name": "Projeto Evento"})
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-1"

    message = telegram_event_message(
        tmp_path,
        run_dir,
        "report_created",
        {"task_id": "TASK-001", "plain_summary": "Tudo pronto."},
    )

    assert message == "Harness: Projeto Evento\nRelatorio final criado para TASK-001.\n\nTudo pronto."


def test_sync_agent_from_event_updates_hub_agent_registry(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Implementar evento",
                "status": "in_progress",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )

    sync_agent_from_event(
        tmp_path,
        {
            "id": "EV-001",
            "type": "run_started",
            "task_id": "TASK-001",
            "run_dir": str(tmp_path / ".harness" / "runs" / "TASK-001" / "run-1"),
            "payload": {"task_id": "TASK-001"},
        },
    )

    agents = load_agent_registry(tmp_path)["agents"]
    agent = next(item for item in agents if item["id"] == "builder-task-001")
    assert agent["task_title"] == "Implementar evento"
    assert agent["state"] == "working"
    assert agent["phase"] == "build"
    assert agent["sector"] == "implement"
    assert agent["spawned_by"] == "event"
    assert agent["speech"] == "Comecei TASK-001."

    events = read_jsonl(event_stream_path(tmp_path))
    assert events[-1]["type"] == "agent_sector_changed"
    assert events[-1]["payload"]["agent_id"] == "builder-task-001"
    assert events[-1]["payload"]["sector"] == "implement"

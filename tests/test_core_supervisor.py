from pathlib import Path

from harness_core.paths import contract_file_path
from harness_core.storage import write_json
from harness_core.supervisor import supervisor_recommendation
from harness_core.task_store import save_tasks


def save_task(root: Path, status: str) -> None:
    save_tasks(
        root,
        [
            {
                "task_id": "TASK-001",
                "title": "Rodar supervisor",
                "status": status,
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )


def test_supervisor_recommendation_handles_queue_item_without_task(tmp_path: Path) -> None:
    recommendation = supervisor_recommendation(tmp_path, {"id": "Q-001"})

    assert "Item de fila sem task" in recommendation


def test_supervisor_recommendation_suggests_contract_when_missing(tmp_path: Path) -> None:
    save_task(tmp_path, "planned")

    recommendation = supervisor_recommendation(tmp_path, {"id": "Q-001", "task_id": "TASK-001"})

    assert "contract TASK-001" in recommendation
    assert "bin" in recommendation
    assert "harness.py" in recommendation
    assert "harness_core" not in recommendation


def test_supervisor_recommendation_suggests_start_when_contract_exists(tmp_path: Path) -> None:
    save_task(tmp_path, "contracted")
    write_json(contract_file_path(tmp_path, "TASK-001"), {"task_id": "TASK-001"})

    recommendation = supervisor_recommendation(tmp_path, {"id": "Q-001", "task_id": "TASK-001"})

    assert "start TASK-001" in recommendation


def test_supervisor_recommendation_suggests_fastest_sensor_tier(tmp_path: Path) -> None:
    save_task(tmp_path, "in_progress")
    write_json(
        contract_file_path(tmp_path, "TASK-001"),
        {"task_id": "TASK-001", "sensor_tiers": {"smoke": ["pytest"], "full": ["pytest"]}},
    )

    recommendation = supervisor_recommendation(tmp_path, {"id": "Q-001", "task_id": "TASK-001"})

    assert "sensors TASK-001 --tier smoke --reviewed" in recommendation


def test_supervisor_recommendation_suggests_evaluate_and_queue_done(tmp_path: Path) -> None:
    save_task(tmp_path, "sensors_passed")
    write_json(contract_file_path(tmp_path, "TASK-001"), {"task_id": "TASK-001"})
    assert "evaluate TASK-001" in supervisor_recommendation(tmp_path, {"id": "Q-001", "task_id": "TASK-001"})

    save_task(tmp_path, "passed")
    assert "queue done Q-001" in supervisor_recommendation(tmp_path, {"id": "Q-001", "task_id": "TASK-001"})

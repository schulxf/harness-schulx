from __future__ import annotations

from pathlib import Path

from harness_core.checkpoints import (
    create_checkpoint,
    latest_checkpoint_path,
    latest_checkpoint_summary,
    next_run_checkpoint_path,
    render_resume_brief,
)
from harness_core.paths import contract_file_path
from harness_core.storage import read_json, write_json
from harness_core.task_store import save_tasks


def save_task(root: Path, *, status: str = "planned") -> None:
    save_tasks(
        root,
        [
            {
                "task_id": "TASK-001",
                "title": "Build login",
                "status": status,
                "task_file": ".harness/tasks/TASK-001.md",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    )


def test_create_checkpoint_writes_timestamped_and_latest_files(tmp_path: Path) -> None:
    save_task(tmp_path, status="in_progress")
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-a"
    run_dir.mkdir(parents=True)
    write_json(run_dir / "sensors.json", {"passed": True})

    path = create_checkpoint(tmp_path, "TASK-001", "manual", run_dir, {"summary": "checkpoint"})

    assert path.name.startswith("checkpoint-")
    payload = read_json(path)
    assert payload["task_id"] == "TASK-001"
    assert payload["sensors"] == {"passed": True}
    assert payload["summary"] == "checkpoint"
    assert read_json(tmp_path / ".harness" / "checkpoints" / "TASK-001" / "latest.json")["summary"] == "checkpoint"


def test_latest_checkpoint_path_prefers_latest_file(tmp_path: Path) -> None:
    save_task(tmp_path)
    path = create_checkpoint(tmp_path, "TASK-001", "manual")

    assert latest_checkpoint_path(tmp_path, "TASK-001") == path.parent / "latest.json"


def test_latest_checkpoint_summary_prefers_summary_then_reason(tmp_path: Path) -> None:
    save_task(tmp_path)
    create_checkpoint(tmp_path, "TASK-001", "manual", extra={"summary": "short status"})

    assert latest_checkpoint_summary(tmp_path, "TASK-001") == "short status"
    assert latest_checkpoint_summary(tmp_path, None) == ""


def test_next_run_checkpoint_path_uses_next_numeric_suffix(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    (checkpoints / "checkpoint-001.json").write_text("{}", encoding="utf-8")
    (checkpoints / "checkpoint-009.json").write_text("{}", encoding="utf-8")

    assert next_run_checkpoint_path(tmp_path) == checkpoints / "checkpoint-010.json"


def test_render_resume_brief_recommends_contract_when_missing(tmp_path: Path) -> None:
    save_task(tmp_path, status="planned")

    brief = render_resume_brief(
        tmp_path,
        "TASK-001",
        {"created_at": "now", "reason": "manual", "git_status": "clean"},
        harness_script=Path("bin/harness.py"),
    )

    assert "Criar contrato: python bin\\harness.py" in brief or "Criar contrato: python bin/harness.py" in brief
    assert "Status atual: planned" in brief


def test_render_resume_brief_recommends_sensors_for_working_task(tmp_path: Path) -> None:
    save_task(tmp_path, status="in_progress")
    write_json(
        contract_file_path(tmp_path, "TASK-001"),
        {
            "sensor_tiers": {"smoke": ["python -c pass"], "full": ["python -c pass"]},
            "required_sensors": ["python -c pass"],
        },
    )

    brief = render_resume_brief(
        tmp_path,
        "TASK-001",
        {"created_at": "now", "reason": "manual", "git_status": "clean"},
        harness_script=Path("bin/harness.py"),
    )

    assert "Rodar sensores rapidos" in brief
    assert "--tier smoke" in brief

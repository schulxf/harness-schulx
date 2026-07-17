from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.paths import evaluation_markdown_path
from harness_core.run_state import (
    find_unevaluated_runs,
    latest_run_dir,
    latest_run_dir_or_none,
    run_evaluation_status,
)
from harness_core.storage import write_json, write_text


def write_run(root: Path, task_id: str, run_id: str, payload: dict | None = None) -> Path:
    run_dir = root / ".harness" / "runs" / task_id / run_id
    run_dir.mkdir(parents=True)
    write_json(run_dir / "run.json", {"task_id": task_id, "run_id": run_id, **(payload or {})})
    return run_dir


def test_latest_run_dir_returns_latest_sorted_run(tmp_path: Path) -> None:
    write_run(tmp_path, "TASK-001", "run-20260101T000000Z")
    latest = write_run(tmp_path, "TASK-001", "run-20260102T000000Z")

    assert latest_run_dir(tmp_path, "TASK-001") == latest
    assert latest_run_dir_or_none(tmp_path, "TASK-001") == latest


def test_latest_run_dir_handles_missing_task_runs(tmp_path: Path) -> None:
    assert latest_run_dir_or_none(tmp_path, "TASK-001") is None
    with pytest.raises(SystemExit, match="Nenhuma run encontrada para TASK-001"):
        latest_run_dir(tmp_path, "TASK-001")


def test_run_evaluation_status_reads_json_status(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, "TASK-001", "run-a")
    write_json(run_dir / "evaluation.json", {"status": "pass"})

    assert run_evaluation_status(tmp_path, "TASK-001", run_dir) == "pass"


def test_run_evaluation_status_reads_markdown_fallback(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, "TASK-001", "run-a")
    write_text(
        evaluation_markdown_path(tmp_path, "TASK-001"),
        f"# Evaluation\n\nRun: {run_dir}\n\nStatus: needs_work\n",
    )

    assert run_evaluation_status(tmp_path, "TASK-001", run_dir) == "needs_work"


def test_find_unevaluated_runs_skips_runs_with_evaluation(tmp_path: Path) -> None:
    write_run(tmp_path, "TASK-001", "run-a")
    evaluated = write_run(tmp_path, "TASK-001", "run-b")
    write_json(evaluated / "evaluation.json", {"status": "pass"})
    with_sensors = write_run(tmp_path, "TASK-002", "run-c")
    write_json(with_sensors / "sensors.json", {"passed": True})

    runs = find_unevaluated_runs(tmp_path)

    assert [(item["task_id"], item["run_id"], item["has_sensors"]) for item in runs] == [
        ("TASK-001", "run-a", False),
        ("TASK-002", "run-c", True),
    ]

"""Run discovery and evaluation state helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness_core.artifacts import iter_run_dirs
from harness_core.paths import evaluation_markdown_path, harness_root, to_posix
from harness_core.storage import read_json, read_text


def latest_run_dir(root: Path, task_id: str) -> Path:
    runs_root = harness_root(root) / "runs" / task_id
    if not runs_root.exists():
        raise SystemExit(f"Nenhuma run encontrada para {task_id}. Rode: harness start {task_id}")
    runs = sorted([path for path in runs_root.iterdir() if path.is_dir()])
    if not runs:
        raise SystemExit(f"Nenhuma run encontrada para {task_id}. Rode: harness start {task_id}")
    return runs[-1]


def latest_run_dir_or_none(root: Path, task_id: str) -> Path | None:
    runs_root = harness_root(root) / "runs" / task_id
    if not runs_root.exists():
        return None
    runs = sorted([path for path in runs_root.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def run_evaluation_status(root: Path, task_id: str, run_dir: Path) -> str | None:
    evaluation_path = run_dir / "evaluation.json"
    if evaluation_path.exists():
        evaluation = read_json(evaluation_path, {})
        status = evaluation.get("status")
        return str(status) if status else "recorded"

    markdown_path = evaluation_markdown_path(root, task_id)
    if not markdown_path.exists():
        return None

    markdown = read_text(markdown_path)
    run_path = str(run_dir)
    if run_path not in markdown and to_posix(run_path) not in markdown:
        return None

    match = re.search(r"(?m)^Status:\s*([^\s]+)\s*$", markdown)
    if match:
        return match.group(1)
    return "recorded"


def run_has_evaluation_record(root: Path, task_id: str, run_dir: Path) -> bool:
    return run_evaluation_status(root, task_id, run_dir) is not None


def find_unevaluated_runs(root: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    unevaluated: list[dict[str, Any]] = []
    for run_dir in iter_run_dirs(root, task_id):
        if not (run_dir / "run.json").exists():
            continue
        run = read_json(run_dir / "run.json", {})
        task = run.get("task_id") or run_dir.parent.name
        if run_has_evaluation_record(root, task, run_dir):
            continue
        unevaluated.append(
            {
                "task_id": task,
                "run_id": run.get("run_id") or run_dir.name,
                "run_dir": str(run_dir),
                "has_sensors": (run_dir / "sensors.json").exists(),
            }
        )
    return unevaluated

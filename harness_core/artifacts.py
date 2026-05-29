"""Run artifact discovery and artifact registry helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_core.paths import artifacts_index_path, harness_root, to_posix
from harness_core.storage import read_json, write_json


def load_artifacts(root: Path) -> list[dict[str, Any]]:
    return read_json(artifacts_index_path(root), [])


def save_artifacts(root: Path, artifacts: list[dict[str, Any]]) -> None:
    write_json(artifacts_index_path(root), artifacts)


def artifact_id(task_id: str, path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"ART-{task_id}-{digest}"


def iter_run_dirs(root: Path, task_id: str | None = None) -> list[Path]:
    runs_root = harness_root(root) / "runs"
    if not runs_root.exists():
        return []
    if task_id:
        task_root = runs_root / task_id
        if not task_root.exists():
            return []
        return sorted([path for path in task_root.iterdir() if path.is_dir()])

    run_dirs: list[Path] = []
    for task_runs_root in sorted([path for path in runs_root.iterdir() if path.is_dir()]):
        run_dirs.extend(sorted([path for path in task_runs_root.iterdir() if path.is_dir()]))
    return run_dirs


def collect_run_artifacts(root: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    interesting = {
        "builder-brief.md",
        "evaluator-brief.md",
        "evaluator-agent-handoff.md",
        "greptile-reviewer-agent-handoff.md",
        "review-consolidation.md",
        "parallel-dispatch.md",
        "events.jsonl",
        "evaluation.json",
        "plain-summary.md",
        "run.json",
    }
    for run_dir in iter_run_dirs(root, task_id):
        task = run_dir.parent.name
        for path in sorted(run_dir.iterdir()):
            if not path.is_file():
                continue
            if path.name in interesting or path.name.startswith("sensors") or path.name.startswith("fix-brief"):
                artifacts.append(
                    {
                        "id": artifact_id(task, path),
                        "task_id": task,
                        "run_id": run_dir.name,
                        "path": to_posix(path.relative_to(root)),
                        "kind": path.suffix.lstrip(".") or "file",
                        "label": path.name,
                        "size": path.stat().st_size,
                        "created_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                        .replace(microsecond=0)
                        .isoformat(),
                    }
                )
    artifacts.extend(load_artifacts(root))
    return artifacts

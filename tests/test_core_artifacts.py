from __future__ import annotations

from pathlib import Path

from harness_core.artifacts import (
    artifact_id,
    collect_run_artifacts,
    iter_run_dirs,
    load_artifacts,
    save_artifacts,
)


def test_artifact_registry_round_trip(tmp_path: Path) -> None:
    artifacts = [{"id": "ART-1", "task_id": "TASK-001", "path": "manual.txt"}]

    save_artifacts(tmp_path, artifacts)

    assert load_artifacts(tmp_path) == artifacts


def test_artifact_id_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "artifact.md"

    assert artifact_id("TASK-001", path) == artifact_id("TASK-001", path)
    assert artifact_id("TASK-001", path).startswith("ART-TASK-001-")


def test_iter_run_dirs_lists_all_or_task_scoped(tmp_path: Path) -> None:
    (tmp_path / ".harness" / "runs" / "TASK-001" / "run-a").mkdir(parents=True)
    (tmp_path / ".harness" / "runs" / "TASK-002" / "run-b").mkdir(parents=True)

    assert [path.name for path in iter_run_dirs(tmp_path)] == ["run-a", "run-b"]
    assert [path.name for path in iter_run_dirs(tmp_path, "TASK-001")] == ["run-a"]
    assert iter_run_dirs(tmp_path, "TASK-404") == []


def test_collect_run_artifacts_includes_interesting_files_and_manual_registry(tmp_path: Path) -> None:
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "builder-brief.md").write_text("brief", encoding="utf-8")
    (run_dir / "sensors-fast.json").write_text("{}", encoding="utf-8")
    (run_dir / "ignore.tmp").write_text("ignore", encoding="utf-8")
    save_artifacts(tmp_path, [{"id": "manual", "task_id": "TASK-001", "path": "manual.txt"}])

    artifacts = collect_run_artifacts(tmp_path)

    assert any(artifact["label"] == "builder-brief.md" for artifact in artifacts)
    assert any(artifact["label"] == "sensors-fast.json" for artifact in artifacts)
    assert not any(artifact.get("label") == "ignore.tmp" for artifact in artifacts)
    assert any(artifact["id"] == "manual" for artifact in artifacts)


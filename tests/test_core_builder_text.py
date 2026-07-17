from pathlib import Path

from harness_core.builder_text import render_builder_brief, summarize_context
from harness_core.paths import config_path, context_manifest_path
from harness_core.storage import write_json, write_text


def test_summarize_context_uses_manifest_entries(tmp_path: Path) -> None:
    write_json(
        context_manifest_path(tmp_path),
        [
            {
                "kind": "prd",
                "stored_path": ".harness/context/prd.md",
                "source": "docs/prd.md",
            }
        ],
    )

    assert summarize_context(tmp_path) == "- prd: .harness/context/prd.md (origem: docs/prd.md)"


def test_summarize_context_handles_empty_manifest(tmp_path: Path) -> None:
    assert summarize_context(tmp_path) == "- Nenhum arquivo de contexto ingerido ainda."


def test_render_builder_brief_keeps_public_entrypoint_and_task_context(tmp_path: Path) -> None:
    write_json(config_path(tmp_path), {"project_name": "Teste", "required_context": []})
    task_file = tmp_path / ".harness" / "tasks" / "TASK-001.md"
    write_text(task_file, "# TASK-001\n\nFazer algo observavel.")
    task = {
        "task_id": "TASK-001",
        "title": "Fazer algo",
        "task_file": ".harness/tasks/TASK-001.md",
    }
    contract = {"task_id": "TASK-001", "goal": "Fazer algo", "acceptance_criteria": ["Funciona"]}
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-1"

    brief = render_builder_brief(tmp_path, task, contract, run_dir)

    assert "# Brief do implementador - TASK-001" in brief
    assert "Fazer algo observavel." in brief
    assert '"acceptance_criteria": [' in brief
    assert "bin" in brief
    assert "harness.py" in brief
    assert "harness_core" not in brief

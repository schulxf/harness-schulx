from __future__ import annotations

from pathlib import Path

from harness_core.hub_presentation import build_project_presentation, unavailable_presentation
from harness_core.paths import contract_file_path
from harness_core.storage import write_json, write_text


def task(root: Path, number: int, title: str, status: str) -> dict:
    task_id = f"TASK-{number:03d}"
    task_path = root / ".harness" / "tasks" / f"{task_id}.md"
    write_text(
        task_path,
        f"# {task_id} - {title}\n\n## O que construir\n\nEntregar {title.lower()} para as pessoas usuárias.\n",
    )
    return {
        "task_id": task_id,
        "title": title,
        "status": status,
        "task_file": str(task_path.relative_to(root)),
        "updated_at": f"2026-07-17T14:{number:02d}:00Z",
    }


def test_build_project_presentation_explains_current_task_in_plain_language(tmp_path: Path) -> None:
    tasks = [
        task(tmp_path, 1, "Organizar o pedido", "done"),
        task(tmp_path, 2, "Adicionar cupom de desconto", "in_progress"),
        task(tmp_path, 3, "Conferir o novo valor", "planned"),
    ]
    write_json(
        contract_file_path(tmp_path, "TASK-002"),
        {
            "goal": "permitir que clientes utilizem descontos antes da compra",
            "acceptance_criteria": ["O novo valor aparece antes da confirmação"],
        },
    )
    queue = [
        {"task_id": "TASK-001", "status": "done"},
        {"task_id": "TASK-002", "status": "active"},
        {"task_id": "TASK-003", "status": "queued"},
    ]
    events = [
        {"type": "run_started", "ts": "2026-07-17T14:03:00Z", "payload": {}},
    ]

    result = build_project_presentation(
        tmp_path,
        {"hub": {"implementation_name": "Novo processo de pagamento"}},
        tasks,
        queue,
        events,
        {},
    )

    assert result["status"] == "andamento"
    assert result["implementation"] == "Novo processo de pagamento"
    assert result["current"]["number"] == 2
    assert result["current"]["total"] == 3
    assert "clientes utilizem descontos" in result["current"]["why"]
    assert result["tasks"][0]["state"] == "done"
    assert result["tasks"][1]["state"] == "doing"
    assert result["tasks"][2]["state"] == "waiting"
    assert result["recent_updates"][0]["text"] == "A implementação desta task começou."


def test_build_project_presentation_marks_review_attention_and_completion(tmp_path: Path) -> None:
    review_task = task(tmp_path, 1, "Conferir relatório", "sensors_passed")
    review = build_project_presentation(
        tmp_path,
        {},
        [review_task],
        [{"task_id": "TASK-001", "status": "active"}],
        [{"type": "evaluation_brief_created", "ts": "2026-07-17T15:00:00Z"}],
        {},
    )
    assert review["status"] == "revisao"
    assert review["stage"] == 3

    attention_task = {**review_task, "status": "needs_work"}
    attention = build_project_presentation(
        tmp_path,
        {},
        [attention_task],
        [{"task_id": "TASK-001", "status": "active"}],
        [],
        {},
    )
    assert attention["status"] == "atencao"
    assert attention["blocker"]["title"] == "Precisa de atenção"

    done_task = {**review_task, "status": "done"}
    complete = build_project_presentation(tmp_path, {}, [done_task], [], [], {})
    assert complete["status"] == "concluido"
    assert complete["stage"] == 4
    assert complete["current"]["remaining"] == "Nada ficou pendente."


def test_unavailable_presentation_uses_nontechnical_message() -> None:
    result = unavailable_presentation("Projeto", "harness_not_initialized")

    assert result["status"] == "indisponivel"
    assert "ainda não foi preparado" in result["unavailable_message"]
    assert result["tasks"] == []

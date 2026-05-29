from pathlib import Path

from harness_core.github_pr import render_github_pr_body
from harness_core.paths import harness_root, security_root
from harness_core.storage import write_json, write_text
from harness_core.task_store import save_tasks


def test_render_github_pr_body_uses_report_summary_and_security(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Publicar PR",
                "status": "passed",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )
    run_dir = harness_root(tmp_path) / "runs" / "TASK-001" / "run-1"
    write_json(run_dir / "run.json", {"task_id": "TASK-001"})
    write_text(run_dir / "plain-summary.md", "# Explicacao simples\n\nTudo pronto.")
    write_text(harness_root(tmp_path) / "reports" / "TASK-001.md", "# Relatorio\n\nEvidencia completa.")
    write_json(security_root(tmp_path) / "scan-latest.json", {"findings": [{"type": "secret"}]})

    body = render_github_pr_body(tmp_path, "TASK-001")

    assert "# TASK-001 - Publicar PR" in body
    assert "Tudo pronto." in body
    assert "- Status da task: passed" in body
    assert "- Security scan: 1 finding(s)" in body
    assert "- Relatorio: `.harness/reports/TASK-001.md`" in body
    assert "Evidencia completa." in body


def test_render_github_pr_body_has_fallbacks_without_report(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Sem relatorio",
                "status": "planned",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )

    body = render_github_pr_body(tmp_path, "TASK-001")

    assert "Resumo simples ainda nao gerado." in body
    assert "- Security scan: nao executado" in body
    assert "- Relatorio: `pendente`" in body
    assert "Relatorio ainda nao gerado." in body

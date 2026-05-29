from __future__ import annotations

from pathlib import Path

from .paths import harness_root, security_root, to_posix
from .run_state import latest_run_dir_or_none
from .storage import read_json, read_text
from .task_store import find_task


def render_github_pr_body(root: Path, task_id: str) -> str:
    task = find_task(root, task_id)
    report_path = harness_root(root) / "reports" / f"{task_id}.md"
    run_dir = latest_run_dir_or_none(root, task_id)
    plain = read_text(run_dir / "plain-summary.md") if run_dir and (run_dir / "plain-summary.md").exists() else ""
    report = read_text(report_path) if report_path.exists() else ""
    security = read_json(security_root(root) / "scan-latest.json", {})
    security_line = f"{len(security.get('findings') or [])} finding(s)" if security else "nao executado"
    return (
        f"# {task_id} - {task.get('title')}\n\n"
        "## Resumo simples\n\n"
        f"{plain or 'Resumo simples ainda nao gerado.'}\n\n"
        "## Evidencia Harness\n\n"
        f"- Status da task: {task.get('status')}\n"
        f"- Security scan: {security_line}\n"
        f"- Relatorio: `{to_posix(report_path.relative_to(root)) if report_path.exists() else 'pendente'}`\n\n"
        "## Relatorio completo\n\n"
        f"{report or 'Relatorio ainda nao gerado.'}\n"
    )

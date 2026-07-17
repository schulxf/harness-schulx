from __future__ import annotations

import re
from pathlib import Path

from .evaluation_text import plain_clean, render_plain_summary_for_message
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
    sensors = read_json(run_dir / "sensors.json", {}) if run_dir else {}
    run_security_path = run_dir / "security-scan.json" if run_dir else None
    global_security_path = security_root(root) / "scan-latest.json"
    if run_security_path and run_security_path.exists():
        security = read_json(run_security_path, {})
    else:
        security = read_json(global_security_path, {})
    ptbr_review = read_json(run_dir / "ptbr-review.json", {}) if run_dir else {}
    evaluation = read_json(run_dir / "evaluation.json", {}) if run_dir else {}
    simple_summary = render_plain_summary_for_message(plain) if plain else ""
    if not simple_summary and plain:
        simple_summary = re.sub(r"^\s*# [^\n]*\n+", "", plain, count=1).strip()
    if not simple_summary:
        simple_summary = "Resumo simples ainda nao gerado."
    check_lines = [
        "As conferências automáticas passaram."
        if sensors.get("passed")
        else "As conferências automáticas ainda não passaram.",
        "A verificação de segurança não encontrou segredos."
        if security and not security.get("findings")
        else "A verificação de segurança ainda precisa ser concluída.",
        "Os textos em PT-BR foram revisados."
        if ptbr_review.get("status") == "pass"
        else "A revisão dos textos em PT-BR ainda precisa ser concluída.",
    ]
    gaps = [plain_clean(item) for item in evaluation.get("gaps", []) if plain_clean(item)]
    pending = "\n".join(f"- {gap}" for gap in gaps) if gaps else "Nenhuma."
    security_line = f"{len(security.get('findings') or [])} finding(s)" if security else "nao executado"
    ptbr_checkbox = "x" if ptbr_review.get("status") == "pass" else " "
    return (
        f"# {task_id} - {task.get('title')}\n\n"
        "## Resumo simples\n\n"
        f"{simple_summary}\n\n"
        "## Como conferi\n\n"
        f"{' '.join(check_lines)}\n\n"
        "## Pendências\n\n"
        f"{pending}\n\n"
        "## Checklist\n\n"
        f"- [{ptbr_checkbox}] Revisei ortografia, acentuação e clareza dos textos em PT-BR.\n\n"
        "## Evidência Harness\n\n"
        f"- Status da task: {task.get('status')}\n"
        f"- Security scan: {security_line}\n"
        f"- Relatorio: `{to_posix(report_path.relative_to(root)) if report_path.exists() else 'pendente'}`\n\n"
        "## Relatório completo\n\n"
        f"{report or 'Relatorio ainda nao gerado.'}\n"
    )

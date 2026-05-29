from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .clock import utc_now
from .config import config_bool, evaluation_policy, review_policy
from .context_preflight import check_context_preflight, render_preflight_text
from .git_helpers import git_output, is_git_repo
from .memory import render_memory_context
from .sensors import fastest_available_sensor_tier

HARNESS_CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "harness.py"


def render_evaluator_brief(root: Path, task: dict[str, Any], contract: dict[str, Any], run_dir: Path) -> str:
    from .storage import read_json

    sensors = read_json(run_dir / "sensors.json", {"passed": False, "results": []})
    preflight = check_context_preflight(root, task["task_id"])
    status = git_output(root, ["status", "--short"]) if is_git_repo(root) else "Nao e um repo git."
    diff = git_output(root, ["diff", "--stat"]) if is_git_repo(root) else "Diff git indisponivel."
    full_diff_hint = "Rode `git diff` no repo se precisar inspecionar arquivos em detalhe."
    return (
        f"# Brief do avaliador - {task['task_id']}\n\n"
        "Avalie a implementacao contra o contrato. O implementador nao pode se autoaprovar.\n\n"
        "## Formato da decisao\n\n"
        "Retorne um destes status:\n\n"
        "- PASS: todos os criterios de aceite foram atendidos e os sensores obrigatorios sao aceitaveis.\n"
        "- FAIL: inclua lacunas especificas e o menor fix brief possivel.\n\n"
        "Nao invente escopo novo. Avalie apenas o contrato.\n\n"
        "## Contrato\n\n"
        f"```json\n{json.dumps(contract, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Evidencia dos sensores\n\n"
        f"```json\n{json.dumps(sensors, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Preflight de contexto\n\n"
        f"```json\n{json.dumps(preflight, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Memoria do projeto\n\n"
        f"{render_memory_context(root, task['task_id'])}\n\n"
        "## Status do Git\n\n"
        f"```text\n{status}\n```\n\n"
        "## Estatistica do diff\n\n"
        f"```text\n{diff}\n```\n\n"
        f"{full_diff_hint}\n"
    )


def render_evaluator_agent_handoff(
    root: Path,
    task: dict[str, Any],
    run_dir: Path,
    brief_path: Path,
    config: dict[str, Any],
) -> str:
    policy = evaluation_policy(config)
    return (
        f"# Handoff para agente avaliador - {task['task_id']}\n\n"
        "Este arquivo deve ser entregue a um agente avaliador spawnado sem herdar o contexto da sessao atual.\n\n"
        "## Politica de isolamento\n\n"
        f"- Modo: {policy.get('mode', 'spawned_agent')}\n"
        f"- fork_context: {str(config_bool(policy.get('fork_context'), False)).lower()}\n"
        f"- Escopo de entrada: {policy.get('input_scope', 'evaluator_agent_handoff')}\n"
        "- Nao inclua historico, raciocinio, decisoes informais ou mensagens da sessao do implementador.\n"
        "- Entregue ao avaliador apenas este handoff; ele deve abrir o brief abaixo e inspecionar o repo se necessario.\n\n"
        "## Prompt para o avaliador\n\n"
        "Voce e o avaliador independente desta run do Harness.\n\n"
        f"Repo: `{root}`\n"
        f"Task: `{task['task_id']}`\n"
        f"Run: `{run_dir}`\n"
        f"Brief de avaliacao: `{brief_path}`\n\n"
        "Regras:\n\n"
        "- Avalie somente o contrato, os sensores registrados e o diff da run.\n"
        "- Nao use conhecimento da sessao do implementador; trate o brief e o repo como fonte da verdade.\n"
        "- Nao modifique arquivos.\n"
        "- Nao invente escopo novo.\n"
        "- Se faltar evidencia, retorne FAIL com lacunas especificas e o menor fix brief possivel.\n\n"
        "Saida esperada:\n\n"
        "```text\n"
        "Status: PASS | FAIL\n"
        "Notas: <avaliacao objetiva>\n"
        "Lacunas:\n"
        "- <lacuna ou Nenhuma>\n"
        "```\n\n"
        "Depois que o avaliador responder, registre a decisao com:\n\n"
        f"`python {HARNESS_CLI_PATH} --repo {root} evaluate {task['task_id']} --status <pass|fail> --notes-file <arquivo-com-notas>`\n"
    )


def render_greptile_reviewer_agent_handoff(
    root: Path,
    task: dict[str, Any],
    run_dir: Path,
    config: dict[str, Any],
) -> str:
    policy = review_policy(config)
    blocking = policy.get("blocking_findings", {})
    return (
        f"# Handoff para code reviewer Greptile-style - {task['task_id']}\n\n"
        "Este arquivo deve ser entregue a um segundo agente spawnado sem herdar o contexto da sessao atual.\n"
        "Este agente e reviewer de codigo, nao avaliador contratual do Harness.\n\n"
        "## Politica de isolamento\n\n"
        f"- Modo: {policy.get('mode', 'spawned_agent')}\n"
        f"- fork_context: {str(config_bool(policy.get('fork_context'), False)).lower()}\n"
        f"- Skill esperada: {policy.get('skill', 'greptile-review')}\n"
        f"- Escopo de entrada: {policy.get('input_scope', 'greptile_reviewer_handoff')}\n"
        "- Nao inclua historico, raciocinio, decisoes informais ou mensagens da sessao do implementador.\n"
        "- Entregue ao reviewer apenas este handoff; ele deve inspecionar o repo e o diff se necessario.\n\n"
        "## Prompt para o reviewer\n\n"
        f"Use a skill `{policy.get('skill', 'greptile-review')}` para revisar o diff desta run no formato Greptile.\n\n"
        f"Repo: `{root}`\n"
        f"Task: `{task['task_id']}`\n"
        f"Run: `{run_dir}`\n\n"
        "Responsabilidade:\n\n"
        "- Comece pela superficie alterada e riscos diretos do diff.\n"
        "- Revise bugs, regressao, seguranca, contratos cruzados e inconsistencias com padroes do repo.\n"
        "- Amplie contexto apenas quando houver sinal concreto: imports, chamadores, padroes similares e contratos relevantes.\n"
        "- Nao decida se a task passou no Harness; essa decisao pertence ao avaliador contratual.\n"
        "- Nao modifique arquivos.\n\n"
        "Regra de bloqueio para consolidacao:\n\n"
        f"- P0 bloqueia: {str(config_bool(blocking.get('p0'), True)).lower()}\n"
        f"- P1 dentro da superficie alterada bloqueia: {str(config_bool(blocking.get('p1_in_changed_surface'), True)).lower()}\n"
        f"- P2 bloqueia: {str(config_bool(blocking.get('p2'), False)).lower()}\n\n"
        "Saida esperada:\n\n"
        "```text\n"
        "Resumo: <2-6 frases>\n"
        "Score: <0-5>/5 - <justificativa curta>\n"
        "Achados bloqueantes: <Nenhum | lista de P0/P1>\n"
        "Achados nao bloqueantes: <Nenhum | lista de P2>\n\n"
        "Comentarios inline:\n"
        "**[P1] logic - caminho/arquivo.ts:123**\n"
        "<impacto real e sugestao>\n"
        "```\n"
    )


def render_review_consolidation(
    task: dict[str, Any],
    evaluator_handoff_path: Path,
    reviewer_handoff_path: Path | None,
    config: dict[str, Any],
) -> str:
    policy = review_policy(config)
    blocking = policy.get("blocking_findings", {})
    reviewer_section = (
        f"- Spawn code reviewer Greptile-style com `{reviewer_handoff_path}`.\n"
        if reviewer_handoff_path
        else "- Review Greptile-style desabilitado por `review_policy.enabled=false`.\n"
    )
    return (
        f"# Consolidacao da revisao - {task['task_id']}\n\n"
        "Use este guia depois que os agentes separados responderem.\n\n"
        "## Agentes\n\n"
        f"- Spawn avaliador contratual com `{evaluator_handoff_path}`.\n"
        f"{reviewer_section}"
        "- Dispare os dois em paralelo; eles nao dependem um do outro.\n\n"
        "## Regras de decisao\n\n"
        "- O avaliador contratual responde se a task cumpre contrato, sensores e evidencia.\n"
        "- O code reviewer responde se o diff introduz risco tecnico.\n"
        "- `FAIL` do avaliador contratual bloqueia a task.\n"
        f"- P0 do reviewer bloqueia: {str(config_bool(blocking.get('p0'), True)).lower()}.\n"
        f"- P1 dentro da superficie alterada bloqueia: {str(config_bool(blocking.get('p1_in_changed_surface'), True)).lower()}.\n"
        f"- P2 do reviewer bloqueia: {str(config_bool(blocking.get('p2'), False)).lower()}.\n"
        "- P2 deve virar ajuste opcional ou follow-up, salvo se voce decidir promover a severidade com evidencia.\n\n"
        "## Registro\n\n"
        "- Se houver bloqueador, registre `evaluate --status fail` com gaps concretos.\n"
        "- Se o avaliador retornou PASS e o reviewer nao encontrou P0/P1 bloqueante, registre `evaluate --status pass`.\n"
        "- Inclua nas notas finais o resumo do avaliador e o resumo do reviewer.\n"
    )


def render_parallel_dispatch(
    task: dict[str, Any],
    evaluator_handoff_path: Path,
    reviewer_handoff_path: Path | None,
) -> str:
    reviewer_text = (
        f"2. Em paralelo, spawn Greptile reviewer com `{reviewer_handoff_path}`.\n"
        if reviewer_handoff_path
        else "2. Review Greptile-style esta desabilitado nesta config.\n"
    )
    return (
        f"# Dispatch paralelo - {task['task_id']}\n\n"
        "Use isto para reduzir tempo de parede apos os sensores passarem.\n\n"
        "## Disparo\n\n"
        f"1. Spawn avaliador contratual com `{evaluator_handoff_path}`.\n"
        f"{reviewer_text}"
        "3. Nao espere um terminar para iniciar o outro.\n"
        "4. Quando ambos responderem, use `review-consolidation.md`.\n\n"
        "## Se houver bloqueador\n\n"
        "- P0/P1 bloqueante: corrija na mesma task e gere `fix-brief`.\n"
        "- P2: deixe como follow-up, salvo evidencia de bloqueio.\n"
    )


def plain_clean(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def render_plain_summary(
    task: dict[str, Any],
    contract: dict[str, Any],
    sensors: dict[str, Any],
    evaluation: dict[str, Any],
) -> str:
    goal = plain_clean(contract.get("goal") or task.get("title") or "a tarefa combinada")
    criteria = [plain_clean(item) for item in contract.get("acceptance_criteria", []) if plain_clean(item)]
    gaps = [plain_clean(item) for item in evaluation.get("gaps", []) if plain_clean(item)]
    notes = plain_clean(evaluation.get("notes"))
    status = str(evaluation.get("status") or "nao-registrado")

    if status == "pass":
        result = "A tarefa foi marcada como pronta."
    elif status == "fail":
        result = "A tarefa ainda nao foi aceita."
    elif status == "needs-work":
        result = "A tarefa precisa de ajustes antes de ser considerada pronta."
    else:
        result = "Ainda falta registrar a decisao final desta tarefa."

    sensor_results = sensors.get("results", [])
    if sensors.get("passed"):
        check_text = "As conferencias automaticas passaram."
    elif sensor_results:
        failed = [plain_clean(item.get("command")) for item in sensor_results if item.get("exit_code") != 0]
        if failed:
            check_text = "Algumas conferencias automaticas falharam: " + ", ".join(failed) + "."
        else:
            check_text = "As conferencias automaticas foram registradas, mas ainda nao indicam conclusao."
    else:
        check_text = "Nenhuma conferencia automatica foi registrada ainda."

    reason_lines = [f"- {item}" for item in criteria[:8]]
    if not reason_lines:
        reason_lines = [f"- {goal}"]

    pending_lines = [f"- {item}" for item in gaps]
    if not pending_lines:
        if status == "pass":
            pending_lines = ["- Nada ficou pendente."]
        else:
            pending_lines = ["- Nenhum ponto pendente foi detalhado ainda."]

    note_text = f"\n\nObservacao simples: {notes}\n" if notes else "\n"
    return (
        f"# Explicacao simples - {task.get('task_id', 'TASK')}\n\n"
        "## O que foi feito\n\n"
        f"Foi trabalhada a tarefa \"{plain_clean(task.get('title'))}\".\n\n"
        "## Por que foi feito\n\n"
        f"Isso foi feito para: {goal}.\n\n"
        "Os pontos combinados eram:\n"
        f"{chr(10).join(reason_lines)}\n\n"
        "## Como foi conferido\n\n"
        f"{check_text}\n\n"
        "## Resultado\n\n"
        f"{result}{note_text}"
        "## O que ficou pendente\n\n"
        f"{chr(10).join(pending_lines)}\n"
    )


def render_plain_summary_for_message(summary: str) -> str:
    lines = []
    in_section = False
    for line in summary.splitlines():
        if line.startswith("## "):
            heading = line.lstrip("#").strip()
            in_section = heading in {"O que foi feito", "Resultado", "O que ficou pendente"}
            if in_section:
                lines.append(f"{heading}:")
            continue
        if in_section and line.strip() and not line.startswith("# "):
            lines.append(line.strip())
    return "\n".join(lines[:12]).strip()


def extract_review_findings(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for line in text.splitlines():
        match = re.search(r"\bP([012])\b|\[P([012])\]", line, re.IGNORECASE)
        if not match:
            continue
        severity = f"P{match.group(1) or match.group(2)}".upper()
        findings.append({"severity": severity, "text": plain_clean(line)})
    return findings


def blocking_findings_from_review(text: str, config: dict[str, Any]) -> list[dict[str, str]]:
    policy = review_policy(config)
    blocking = policy.get("blocking_findings", {})
    findings = extract_review_findings(text)
    blockers: list[dict[str, str]] = []
    for finding in findings:
        severity = finding["severity"]
        lowered = finding["text"].lower()
        if severity == "P0" and config_bool(blocking.get("p0"), True):
            blockers.append(finding)
        elif severity == "P1" and config_bool(blocking.get("p1_in_changed_surface"), True):
            if "fora da superficie" not in lowered and "fora do escopo" not in lowered:
                blockers.append(finding)
        elif severity == "P2" and config_bool(blocking.get("p2"), False):
            blockers.append(finding)
    return blockers


def next_fix_brief_path(run_dir: Path) -> Path:
    existing = sorted(run_dir.glob("fix-brief-*.md"))
    numbers = []
    for path in existing:
        match = re.match(r"fix-brief-(\d+)\.md$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return run_dir / f"fix-brief-{(max(numbers) + 1) if numbers else 1:02d}.md"


def render_fix_brief(
    root: Path,
    task: dict[str, Any],
    contract: dict[str, Any],
    run_dir: Path,
    review_text: str,
    evaluator_text: str,
    config: dict[str, Any],
) -> str:
    blockers = blocking_findings_from_review(review_text, config)
    blocker_lines = [f"- {item['severity']}: {item['text']}" for item in blockers]
    if not blocker_lines:
        blocker_lines = ["- Nenhum P0/P1 bloqueante detectado automaticamente. Revise as notas abaixo."]
    quick_tier = fastest_available_sensor_tier(contract)
    quick_command = f"python {HARNESS_CLI_PATH} --repo {root} sensors {task['task_id']} --tier {quick_tier} --reviewed"
    full_command = f"python {HARNESS_CLI_PATH} --repo {root} sensors {task['task_id']} --tier full --reviewed"
    return (
        f"# Fix brief rapido - {task['task_id']}\n\n"
        "Corrija apenas os bloqueadores abaixo dentro da mesma task. Nao crie escopo novo.\n\n"
        "## Bloqueadores detectados\n\n"
        f"{chr(10).join(blocker_lines)}\n\n"
        "## Loop recomendado\n\n"
        "1. Corrija o menor trecho necessario.\n"
        f"2. Rode sensores rapidos: `{quick_command}`\n"
        "3. Se os sensores rapidos passarem, rode novamente `evaluate` para gerar handoffs focados.\n"
        f"4. Antes de `pass`, rode sensores finais: `{full_command}`\n\n"
        "## Notas do reviewer\n\n"
        f"{review_text.strip() or 'Sem notas do reviewer.'}\n\n"
        "## Notas do avaliador\n\n"
        f"{evaluator_text.strip() or 'Sem notas do avaliador.'}\n\n"
        f"Run: `{run_dir}`\n"
    )


def render_evaluation_markdown(evaluation: dict[str, Any]) -> str:
    gaps = evaluation.get("gaps", [])
    gap_text = "\n".join(f"- {gap}" for gap in gaps) if gaps else "- Nenhuma lacuna registrada."
    return (
        f"# Avaliacao - {evaluation['task_id']}\n\n"
        f"Status: {evaluation['status']}\n"
        f"Criada: {evaluation['created_at']}\n"
        f"Run: {evaluation['run_dir']}\n\n"
        "## Notas\n\n"
        f"{evaluation.get('notes') or 'Sem notas.'}\n\n"
        "## Lacunas\n\n"
        f"{gap_text}\n"
    )


def render_report(
    root: Path,
    task: dict[str, Any],
    contract: dict[str, Any],
    run_dir: Path,
    sensors: dict[str, Any],
    evaluation: dict[str, Any],
    plain_summary: str | None = None,
) -> str:
    sensor_lines = []
    for result in sensors.get("results", []):
        icon = "PASS" if result.get("exit_code") == 0 else "FAIL"
        sensor_lines.append(
            f"- {icon} `{result.get('command')}` exit={result.get('exit_code')} "
            f"duration_ms={result.get('duration_ms')}"
        )
    if not sensor_lines:
        sensor_lines.append("- Nenhum sensor registrado.")

    criteria = contract.get("acceptance_criteria", [])
    criteria_lines = [f"- {item}" for item in criteria] if criteria else ["- Nenhum criterio registrado."]
    preflight = check_context_preflight(root, task["task_id"])
    preflight_text = render_preflight_text(preflight)
    git_status = git_output(root, ["status", "--short"]) if is_git_repo(root) else "Nao e um repo git."
    plain_summary = plain_summary or render_plain_summary(task, contract, sensors, evaluation)
    plain_summary_body = re.sub(r"^# .+?\n\n", "", plain_summary, count=1)

    return (
        f"# Relatorio do Harness - {task['task_id']}\n\n"
        f"Titulo: {task['title']}\n"
        f"Status da task: {task['status']}\n"
        f"Run: {run_dir}\n"
        f"Gerado: {utc_now()}\n\n"
        "## Objetivo\n\n"
        f"{contract.get('goal', task['title'])}\n\n"
        "## Explicacao simples\n\n"
        f"{plain_summary_body}\n\n"
        "## Criterios de aceite\n\n"
        f"{chr(10).join(criteria_lines)}\n\n"
        "## Sensores\n\n"
        f"{chr(10).join(sensor_lines)}\n\n"
        "## Preflight de contexto\n\n"
        f"```text\n{preflight_text}\n```\n\n"
        "## Memoria do projeto\n\n"
        f"{render_memory_context(root, task['task_id'])}\n\n"
        "## Avaliacao\n\n"
        f"Status: {evaluation.get('status', 'nao-registrado')}\n\n"
        f"{evaluation.get('notes', 'Nenhuma nota de avaliacao registrada.')}\n\n"
        "## Status do Git\n\n"
        f"```text\n{git_status}\n```\n"
    )

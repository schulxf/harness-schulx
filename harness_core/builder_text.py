from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_preflight import check_context_preflight, render_preflight_text
from .git_helpers import git_output, is_git_repo
from .memory import render_memory_context
from .paths import context_manifest_path
from .storage import read_json, read_text

HARNESS_CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "harness.py"


def summarize_context(root: Path) -> str:
    manifest = read_json(context_manifest_path(root), [])
    if not manifest:
        return "- Nenhum arquivo de contexto ingerido ainda."
    lines = []
    for item in manifest:
        lines.append(f"- {item['kind']}: {item['stored_path']} (origem: {item['source']})")
    return "\n".join(lines)


def render_builder_brief(
    root: Path,
    task: dict[str, Any],
    contract: dict[str, Any],
    run_dir: Path,
) -> str:
    task_text = read_text(root / task["task_file"])
    contract_text = json.dumps(contract, indent=2, ensure_ascii=False)
    preflight_text = render_preflight_text(check_context_preflight(root, task["task_id"]))
    git_status = git_output(root, ["status", "--short"]) if is_git_repo(root) else "Nao e um repo git."
    return (
        f"# Brief do implementador - {task['task_id']}\n\n"
        "Voce esta implementando uma fatia vertical dentro do protocolo Harness.\n\n"
        "## Regras\n\n"
        "- Implemente apenas a task contratada.\n"
        "- Use TDD: um teste de comportamento, implementacao minima, repetir.\n"
        "- Nao adicione funcionalidades fora de escopo.\n"
        "- Nao declare concluido sem evidencia de sensores.\n"
        "- Atualize notas de progresso se comportamento ou escopo mudarem.\n\n"
        "## Arquivos de contexto\n\n"
        f"{summarize_context(root)}\n\n"
        "## Memoria do projeto\n\n"
        f"{render_memory_context(root, task['task_id'])}\n\n"
        "## Preflight de contexto\n\n"
        f"```text\n{preflight_text}\n```\n\n"
        "## Tarefa\n\n"
        f"{task_text}\n\n"
        "## Contrato\n\n"
        f"```json\n{contract_text}\n```\n\n"
        "## Status atual do Git\n\n"
        f"```text\n{git_status}\n```\n\n"
        "## Depois da implementacao\n\n"
        "Revise os comandos de sensores antes de executar. Depois rode:\n\n"
        f"`python {HARNESS_CLI_PATH} --repo {root} sensors {task['task_id']} --tier quick --reviewed`\n\n"
        "Para o fechamento final, rode:\n\n"
        f"`python {HARNESS_CLI_PATH} --repo {root} sensors {task['task_id']} --tier full --reviewed`\n\n"
        "Em seguida, peca avaliacao contratual e review Greptile-style usando os handoffs gerados por:\n\n"
        f"`python {HARNESS_CLI_PATH} --repo {root} evaluate {task['task_id']}`\n\n"
        f"Diretorio da run: `{run_dir}`\n"
    )

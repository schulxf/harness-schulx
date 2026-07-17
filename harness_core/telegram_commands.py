from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import collect_run_artifacts
from .budgeting import task_budget
from .checkpoints import latest_checkpoint_path, render_resume_brief
from .clock import utc_now
from .config import config_bool, telegram_config
from .context_preflight import load_config
from .dashboard import write_dashboard_html
from .evaluation_text import render_plain_summary, render_plain_summary_for_message
from .events import append_harness_event
from .git_helpers import current_git_branch
from .memory import render_memory_context
from .paths import contract_file_path, security_root
from .queue_state import active_queue_item, load_queue, queue_counts, sorted_queue_items
from .run_state import latest_run_dir
from .storage import read_json, read_text, write_text
from .task_intake import create_task_from_telegram_item
from .task_store import find_task, load_tasks
from .telegram import (
    analyze_telegram_media,
    build_telegram_prompt_text,
    save_telegram_inbox_item,
    telegram_download_file,
    telegram_message_media,
    telegram_reply,
    telegram_update_context,
)
from .telegram_policy import telegram_chat_allowed

HARNESS_CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "harness.py"


def telegram_tasks_summary(root: Path) -> str:
    tasks = load_tasks(root)
    if not tasks:
        return "Nenhuma task ainda."
    lines = ["Tasks:"]
    for task in tasks[-20:]:
        lines.append(f"- {task['task_id']} [{task['status']}] {task['title']}")
    return "\n".join(lines)


def telegram_status_summary(root: Path) -> str:
    config = load_config(root)
    lines = [f"Projeto: {config.get('project_name')}", f"Raiz: {root}"]
    branch = current_git_branch(root)
    if branch:
        lines.append(f"Branch atual: {branch}")
    counts = queue_counts(root)
    if counts:
        lines.append(f"Fila: {counts}")
    security = read_json(security_root(root) / "scan-latest.json", {})
    if security:
        lines.append(f"Security: {len(security.get('findings') or [])} finding(s)")
    lines.append("")
    lines.append(telegram_tasks_summary(root))
    return "\n".join(lines)


def telegram_latest_plain_summary(root: Path, task_id: str) -> str:
    run_dir = latest_run_dir(root, task_id)
    summary_path = run_dir / "plain-summary.md"
    if summary_path.exists():
        return read_text(summary_path)
    task = find_task(root, task_id)
    contract = read_json(contract_file_path(root, task_id), {})
    sensors = read_json(run_dir / "sensors.json", {})
    evaluation = read_json(run_dir / "evaluation.json", {})
    summary = render_plain_summary(task, contract, sensors, evaluation)
    write_text(summary_path, summary)
    return summary


def handle_telegram_command(
    root: Path,
    config: dict[str, Any],
    chat_id: str,
    text: str,
    item: dict[str, Any],
    create_tasks: bool,
    reply: bool = True,
) -> dict[str, Any]:
    stripped = text.strip()
    command, _, rest = stripped.partition(" ")
    command = command.split("@", 1)[0].lower()

    if command in {"/help", "/start"}:
        if reply:
            telegram_reply(
                config,
                chat_id,
                "Comandos:\n/status\n/tasks\n/queue\n/pick\n/report TASK-001\n"
                "/security\n/memory\n/dashboard\n/new texto da task\n\n"
                "Texto normal, audio e imagem tambem entram no inbox do Harness.",
            )
        item["action"] = "help_sent"
    elif command == "/status":
        if reply:
            telegram_reply(config, chat_id, telegram_status_summary(root))
        item["action"] = "status_sent"
    elif command == "/tasks":
        if reply:
            telegram_reply(config, chat_id, telegram_tasks_summary(root))
        item["action"] = "tasks_sent"
    elif command == "/queue":
        queue = sorted_queue_items(load_queue(root))
        lines = ["Fila:"]
        if not queue:
            lines.append("- vazia")
        for queue_item in queue[-20:]:
            lines.append(f"- {queue_item.get('id')} [{queue_item.get('status')}] {queue_item.get('title')}")
        if reply:
            telegram_reply(config, chat_id, "\n".join(lines))
        item["action"] = "queue_sent"
    elif command == "/active":
        active = active_queue_item(root)
        if active:
            message = f"{active.get('id')} [{active.get('status')}] {active.get('title')}"
            if active.get("task_id"):
                message += f"\nTask: {active.get('task_id')}"
        else:
            message = "Nenhum item ativo na fila."
        if reply:
            telegram_reply(config, chat_id, message)
        item["action"] = "active_sent"
    elif command == "/security":
        report = read_json(security_root(root) / "scan-latest.json", {})
        if not report:
            message = "Nenhum security scan registrado."
        else:
            message = f"Security scan: {len(report.get('findings') or [])} finding(s)."
        if reply:
            telegram_reply(config, chat_id, message)
        item["action"] = "security_sent"
    elif command == "/memory":
        if reply:
            telegram_reply(config, chat_id, render_memory_context(root, limit=12))
        item["action"] = "memory_sent"
    elif command == "/checkpoint":
        task_id = rest.strip().upper()
        if not task_id:
            active = active_queue_item(root)
            task_id = str(active.get("task_id") or "") if active else ""
        if not task_id:
            message = "Use: /checkpoint TASK-001"
        else:
            latest = latest_checkpoint_path(root, task_id)
            if latest:
                checkpoint = read_json(latest, {})
                message = render_resume_brief(
                    root,
                    task_id,
                    checkpoint,
                    harness_script=HARNESS_CLI_PATH,
                )
            else:
                message = f"Nenhum checkpoint encontrado para {task_id}."
        if reply:
            telegram_reply(config, chat_id, message)
        item["action"] = "checkpoint_sent"
    elif command == "/budget":
        active = active_queue_item(root)
        if active and active.get("task_id"):
            try:
                task = find_task(root, active["task_id"])
                budget = task_budget(task, config)
                message = (
                    f"Budget {active['task_id']}: profile={budget.get('name')} "
                    f"minutes={budget.get('time_budget_minutes')} fixes={budget.get('max_fix_attempts')}"
                )
            except Exception as exc:
                message = f"Nao consegui ler budget: {exc}"
        else:
            message = "Nenhuma task ativa na fila."
        if reply:
            telegram_reply(config, chat_id, message)
        item["action"] = "budget_sent"
    elif command == "/artifacts":
        task_id = rest.strip().upper() or None
        artifacts = collect_run_artifacts(root, task_id)
        lines = ["Artifacts:"]
        if not artifacts:
            lines.append("- nenhum")
        for artifact in artifacts[-12:]:
            lines.append(f"- {artifact.get('label')} ({artifact.get('task_id')}): {artifact.get('path')}")
        if reply:
            telegram_reply(config, chat_id, "\n".join(lines))
        item["action"] = "artifacts_sent"
    elif command == "/dashboard":
        path = write_dashboard_html(root)["path"]
        if reply:
            telegram_reply(config, chat_id, f"Dashboard atualizado: {path}")
        item["action"] = "dashboard_built"
    elif command == "/pick":
        pending = next((task for task in load_tasks(root) if task["status"] not in {"passed", "done"}), None)
        if reply:
            telegram_reply(
                config,
                chat_id,
                f"{pending['task_id']} [{pending['status']}] {pending['title']}"
                if pending
                else "Nenhuma task pendente.",
            )
        item["action"] = "pick_sent"
    elif command == "/report":
        task_id = rest.strip().upper()
        if not task_id:
            if reply:
                telegram_reply(config, chat_id, "Use: /report TASK-001")
        else:
            try:
                summary = telegram_latest_plain_summary(root, task_id)
                if reply:
                    telegram_reply(config, chat_id, render_plain_summary_for_message(summary) or summary)
                item["action"] = "report_sent"
            except Exception as exc:
                if reply:
                    telegram_reply(config, chat_id, f"Nao consegui ler o resumo de {task_id}: {exc}")
                item["action"] = "report_failed"
                item["error"] = str(exc)
    elif command in {"/new", "/task", "/prompt"}:
        if not rest.strip():
            if reply:
                telegram_reply(config, chat_id, "Use: /new descreva a tarefa")
            item["action"] = "new_missing_text"
        elif not config_bool(telegram_config(config).get("allow_task_creation"), True):
            if reply:
                telegram_reply(config, chat_id, "Criacao de tasks pelo Telegram esta desligada.")
            item["action"] = "task_creation_disabled"
        else:
            item["prompt_text"] = rest.strip()
            task = create_task_from_telegram_item(root, item)
            if reply:
                telegram_reply(config, chat_id, f"Task criada: {task['task_id']} - {task['title']}")
            item["action"] = "task_created"
            item["created_task_id"] = task["task_id"]
    elif create_tasks and config_bool(telegram_config(config).get("allow_task_creation"), True):
        task = create_task_from_telegram_item(root, item)
        if reply:
            telegram_reply(config, chat_id, f"Task criada: {task['task_id']} - {task['title']}")
        item["action"] = "task_created"
        item["created_task_id"] = task["task_id"]
    else:
        if reply:
            telegram_reply(config, chat_id, "Prompt recebido e salvo no inbox do Harness.")
        item["action"] = "inbox_saved"
    return item


def handle_telegram_update(
    root: Path,
    config: dict[str, Any],
    update: dict[str, Any],
    *,
    create_tasks: bool = False,
    download_media: bool | None = None,
    reply: bool = True,
) -> Path | None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None
    chat_id = str(message.get("chat", {}).get("id", ""))
    item_id = f"tg-{update.get('update_id')}-{message.get('message_id')}"
    if not telegram_chat_allowed(config, chat_id):
        item = {
            "id": item_id,
            "update_id": update.get("update_id"),
            "message_id": message.get("message_id"),
            "chat_id": chat_id,
            "received_at": utc_now(),
            "action": "rejected_chat",
        }
        path = save_telegram_inbox_item(root, item)
        append_harness_event(
            root,
            "telegram_update_rejected",
            {"telegram_item_id": item_id, "chat_id": chat_id},
            source="telegram",
        )
        return path

    text = str(message.get("text") or "")
    caption = str(message.get("caption") or "")
    media_kind, file_id, fallback_ext = telegram_message_media(message)
    media: dict[str, Any] = {}
    media_analysis = ""
    media_analysis_error = None
    should_download = telegram_config(config).get("download_media") if download_media is None else download_media

    if media_kind and file_id and config_bool(should_download, True):
        try:
            media = telegram_download_file(root, config, file_id, item_id, fallback_ext)
            media_analysis, media_analysis_error = analyze_telegram_media(
                Path(media["local_path"]),
                media_kind,
                config,
            )
        except Exception as exc:
            media_analysis_error = str(exc)
            media = {"file_id": file_id, "download_error": str(exc)}
    elif media_kind and file_id:
        media = {"file_id": file_id, "downloaded": False}

    kind = media_kind or "text"
    prompt_text = build_telegram_prompt_text(
        kind,
        text if not text.strip().startswith("/") else "",
        caption,
        str(media.get("local_path") or ""),
        media_analysis,
    )
    item = {
        "id": item_id,
        "update_id": update.get("update_id"),
        "message_id": message.get("message_id"),
        "chat_id": chat_id,
        "from": message.get("from", {}),
        "received_at": utc_now(),
        "kind": kind,
        "text": text,
        "caption": caption,
        "prompt_text": prompt_text,
        "media": media,
        "media_analysis": media_analysis,
        "media_analysis_error": media_analysis_error,
        "raw_update_metadata": {
            "update_id": update.get("update_id"),
            "message_id": message.get("message_id"),
            "date": message.get("date"),
            "has_media": bool(media_kind),
        },
    }

    if text.strip().startswith("/"):
        item = handle_telegram_command(root, config, chat_id, text, item, create_tasks, reply=reply)
    elif create_tasks and config_bool(telegram_config(config).get("allow_task_creation"), True):
        task = create_task_from_telegram_item(root, item)
        item["action"] = "task_created"
        item["created_task_id"] = task["task_id"]
        if reply:
            telegram_reply(config, chat_id, f"Task criada: {task['task_id']} - {task['title']}")
    else:
        item["action"] = "inbox_saved"
        if reply:
            telegram_reply(config, chat_id, "Prompt recebido e salvo no inbox do Harness.")

    path = save_telegram_inbox_item(root, item)
    append_harness_event(
        root,
        "telegram_update_received",
        {
            "telegram_item_id": item_id,
            "chat_id": chat_id,
            "kind": kind,
            "action": item.get("action"),
            "created_task_id": item.get("created_task_id"),
            "summary": f"Telegram recebeu {kind}: {item.get('action')}",
        },
        task_id=str(item.get("created_task_id") or ""),
        source="telegram",
    )
    return path


def prepare_telegram_exec_update(
    root: Path,
    config: dict[str, Any],
    update: dict[str, Any],
    *,
    command_prefixes: tuple[str, ...],
    download_media: bool,
    reply_to_harness_commands: bool,
) -> dict[str, Any]:
    context = telegram_update_context(update)
    stripped = context["stripped"]
    result: dict[str, Any] = {
        "update_id": context["update_id"],
        "chat_id": context["chat_id"],
        "stripped": stripped,
        "path": None,
        "item": None,
        "prompt_text": "",
        "ready": False,
        "processed": False,
        "harness_command": False,
    }

    if not telegram_chat_allowed(config, context["chat_id"]):
        result["path"] = handle_telegram_update(root, config, update, reply=False)
        return result

    if stripped.startswith("/") and not stripped.lower().startswith(command_prefixes):
        path = handle_telegram_update(
            root,
            config,
            update,
            create_tasks=False,
            download_media=download_media,
            reply=reply_to_harness_commands,
        )
        result["path"] = path
        result["processed"] = bool(path)
        result["harness_command"] = bool(path)
        return result

    path = handle_telegram_update(
        root,
        config,
        update,
        create_tasks=False,
        download_media=download_media,
        reply=False,
    )
    result["path"] = path
    if not path:
        return result

    item = read_json(path, {})
    if item.get("action") == "rejected_chat":
        return result

    prompt_text = item.get("prompt_text") or ""
    if stripped.lower().startswith(command_prefixes):
        prompt_text = stripped.partition(" ")[2].strip() or prompt_text

    result["item"] = item
    result["prompt_text"] = prompt_text
    result["ready"] = True
    return result

#!/usr/bin/env python3
"""
Harness Runner MVP.

A small deterministic CLI for turning PRDs/issues into executable agent work:
tasks, contracts, run briefs, sensor evidence, evaluations, and reports.
It has no external dependencies.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        f"harness requires Python >= 3.10 (got {sys.version.split()[0]}).\n"
    )
    raise SystemExit(2)

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness_core.agent_registry import (  # noqa: E402
    agent_status_from_state,
    load_agent_registry,
    save_agent_registry,
    upsert_agent,
)
from harness_core.artifacts import (  # noqa: E402
    artifact_id,
    collect_run_artifacts,
    load_artifacts,
    save_artifacts,
)
from harness_core.budgeting import task_budget  # noqa: E402
from harness_core.checkpoints import (  # noqa: E402
    create_checkpoint,
    latest_checkpoint_path,
    render_resume_brief,
)
from harness_core.clock import utc_now  # noqa: E402
from harness_core.codex_exec import (  # noqa: E402,F401
    build_codex_exec_argv,
    codex_executable,
    codex_image_args_from_item,
    codex_prompt_from_item,
)
from harness_core.codex_session import (  # noqa: E402
    latest_codex_session_file,
    mirror_message_from_codex_event,
    read_new_codex_session_events,
)
from harness_core.compat import compatibility_manifest  # noqa: E402
from harness_core.config import (  # noqa: E402
    active_profile_name,
    config_bool,
    evaluation_policy,
    failure_policy,
    github_config,
    operation_profiles,
    review_policy,
    telegram_config,
)
from harness_core.context_preflight import (  # noqa: E402
    check_context_preflight,
    context_requirements_for_task,
    load_config,
    render_preflight_text,
    require_context_preflight,
    require_init,
)
from harness_core.contracts import load_contract  # noqa: E402
from harness_core.dashboard import (  # noqa: E402,F401
    collect_dashboard_state,
    render_dashboard_html,
    write_dashboard_html,
)
from harness_core.dashboard_hub import (  # noqa: E402,F401
    render_dashboard_hub_html as render_dashboard_hub_html,
)
from harness_core.dashboard_hub import write_dashboard_hub_files  # noqa: E402
from harness_core.defaults import (  # noqa: E402
    CONTEXT_KINDS,
    DEFAULT_EVALUATION_POLICY,
    DEFAULT_FAILURE_POLICY,
    DEFAULT_GITHUB_CONFIG,
    DEFAULT_OPERATION_PROFILES,
    DEFAULT_PROTECTED_BRANCHES,
    DEFAULT_REVIEW_POLICY,
    DEFAULT_TELEGRAM_CONFIG,
)
from harness_core.errors import HarnessError  # noqa: E402
from harness_core.evaluation_text import (  # noqa: E402,F401
    blocking_findings_from_review,
    extract_review_findings,
    next_fix_brief_path,
    plain_clean,
    render_evaluation_markdown,
    render_evaluator_agent_handoff,
    render_evaluator_brief,
    render_fix_brief,
    render_greptile_reviewer_agent_handoff,
    render_parallel_dispatch,
    render_plain_summary,
    render_plain_summary_for_message,
    render_report,
    render_review_consolidation,
)
from harness_core.events import (  # noqa: E402
    append_harness_event,
    read_new_harness_events,
    read_recent_harness_events,
    telegram_message_from_harness_event,
)
from harness_core.file_hash import file_sha256  # noqa: E402
from harness_core.git_helpers import (  # noqa: E402
    current_git_branch,
    git_output,
    is_git_repo,
    protected_branches,
)
from harness_core.github_pr import render_github_pr_body  # noqa: E402,F401
from harness_core.hub_agents import (  # noqa: E402
    hub_agent_name_for_role,
)
from harness_core.hub_auth import hub_action_authorized, hub_local_request_allowed  # noqa: E402
from harness_core.hub_registry import load_hub_repo_registry, save_hub_repo_registry  # noqa: E402
from harness_core.hub_state import (  # noqa: E402
    collect_dashboard_hub_state,
    write_dashboard_hub,
)
from harness_core.memory import (  # noqa: E402
    load_memory,
    next_memory_id,
    render_memory_context,
    save_memory,
)
from harness_core.paths import (  # noqa: E402
    agent_registry_path,
    artifacts_index_path,
    artifacts_root,
    assert_inside_root,
    checkpoints_root,
    config_path,
    context_manifest_path,
    contract_file_path,
    dashboard_hub_root,
    dashboard_root,
    event_stream_path,
    github_root,
    harness_root,
    hub_repo_registry_path,
    memory_index_path,
    normalize_path_key,
    plugin_registry_path,
    queue_path,
    relative_to_root,
    resolve_repo_path,
    security_root,
    supervisor_state_path,
    tasks_index_path,
    telegram_root,
    telegram_state_path,
    to_posix,
)
from harness_core.paths import is_inside_root as is_inside_root  # noqa: E402
from harness_core.plugin_policy import (  # noqa: E402
    PluginPolicyError,
    render_plugin_command,
    require_plugin_run_allowed,
    runnable_plugins,
)
from harness_core.plugin_registry import load_plugins, save_plugins  # noqa: E402
from harness_core.queue_state import (  # noqa: E402
    active_queue_item,
    load_queue,
    next_queue_id,
    next_queued_item,
    queue_counts,
    save_queue,
    sorted_queue_items,
    update_queue_item,
)
from harness_core.records import TaskRecord  # noqa: E402
from harness_core.repo_guard import (  # noqa: E402
    prepared_repo,
    require_existing_root,
    require_safe_branch,
    root_from_args,
)
from harness_core.run_state import (  # noqa: E402
    find_unevaluated_runs,
    latest_run_dir,
    latest_run_dir_or_none,
    run_evaluation_status,
)
from harness_core.security_scan import (  # noqa: E402
    iter_security_inbox_files,
    iter_security_scan_files,
    scan_file_for_secrets,
)
from harness_core.sensors import (  # noqa: E402
    detect_default_sensors,
    fastest_available_sensor_tier,
    final_sensor_payload,
    make_sensor_result,
    resolve_sensor_argv,
    sensors_for_tier,
    split_sensor_command,
)
from harness_core.status import (  # noqa: E402
    TASK_STATUS_SENSORS_PASSED,
    TASK_STATUSES_COMPLETE,
    TASK_STATUSES_READY_TO_START,
    TASK_STATUSES_WORKING,
)
from harness_core.storage import (  # noqa: E402
    append_jsonl,
    read_json,
    read_text,
    write_json,
    write_text,
)
from harness_core.task_store import (  # noqa: E402
    find_task,
    load_tasks,
    next_task_id,
    save_tasks,
    update_task,
)
from harness_core.task_text import extract_checklist, extract_out_of_scope, slugify  # noqa: E402
from harness_core.telegram import (  # noqa: E402,F401
    advance_telegram_offset,
    analyze_telegram_media,
    build_telegram_prompt_text,
    openai_api_key,
    openai_describe_image,
    openai_extract_output_text,
    openai_media_config,
    openai_transcribe_audio,
    render_task_body_from_telegram,
    require_telegram_bot_token,
    save_telegram_inbox_item,
    split_telegram_text,
    telegram_api_call,
    telegram_download_file,
    telegram_file_extension,
    telegram_message_media,
    telegram_poll_updates,
    telegram_reply,
    telegram_send_message,
    telegram_token,
    telegram_update_context,
    write_telegram_bridge_state,
    write_telegram_offset_state,
)
from harness_core.telegram_codex import (  # noqa: E402,F401
    execute_telegram_codex_item,
    queue_operator_message,
    queued_operator_messages_path,
    read_mirror_state,
    run_codex_for_telegram,
    write_mirror_state,
)
from harness_core.telegram_policy import (  # noqa: E402
    telegram_chat_allowed,
    telegram_remote_execution_allowed,
)
from harness_core.wmux import (  # noqa: E402,F401
    collect_wmux_state,
    extract_wmux_surface_id,
    ps_single_quote,
    wmux_cli_path,
    wmux_command_hint,
    wmux_focus,
    wmux_new_terminal,
    wmux_pipe_exchange,
    wmux_pipe_path,
    wmux_read_screen,
    wmux_send_text,
    wmux_send_v1,
    wmux_send_v2,
)

VERSION = "0.3.0"


def sync_agent_from_event(root: Path, event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    task_id = str(event.get("task_id") or payload.get("task_id") or "")
    if not task_id:
        return
    task_title = ""
    try:
        task_title = str(find_task(root, task_id).get("title") or "")
    except SystemExit:
        pass
    role = {
        "run_started": "builder",
        "sensors_completed": "builder",
        "evaluation_brief_created": "reviewer",
        "evaluation_recorded": "reviewer",
        "fix_brief_created": "builder",
        "report_created": "reporter",
    }.get(event_type, "operator")
    state = {
        "evaluation_recorded": "idle",
        "report_created": "idle",
    }.get(event_type, "working")
    phase = {
        "run_started": "build",
        "sensors_completed": "review" if payload.get("passed") else "build",
        "evaluation_brief_created": "review",
        "evaluation_recorded": "report" if payload.get("status") == "pass" else "build",
        "fix_brief_created": "build",
        "report_created": "report",
    }.get(event_type, role)
    speech = payload.get("summary") or {
        "run_started": f"Comecei {task_id}.",
        "sensors_completed": f"Conferencias de {task_id} {'passaram' if payload.get('passed') else 'falharam'}.",
        "evaluation_brief_created": f"Revisao pronta para {task_id}.",
        "evaluation_recorded": f"Decisao de {task_id}: {payload.get('status')}.",
        "fix_brief_created": f"Preparando correcao de {task_id}.",
        "report_created": f"Relatorio de {task_id} fechado.",
    }.get(event_type, f"Atualizei {task_id}.")
    upsert_agent(
        root,
        str(event.get("agent_id") or f"{role}-{task_id}").lower(),
        name=hub_agent_name_for_role(role),
        role=role,
        state=state,
        task_id=task_id,
        task_title=task_title,
        phase=phase,
        speech=str(speech),
        run_dir=str(event.get("run_dir") or ""),
        event_id=str(event.get("id") or ""),
    )


def telegram_event_message(
    root: Path,
    run_dir: Path,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    task_id = str(payload.get("task_id") or run_dir.parent.name)
    project = load_config(root).get("project_name") if config_path(root).exists() else root.name
    if event_type == "run_started":
        return f"Harness: {project}\n{task_id} comecou.\nRun: {run_dir.name}"
    if event_type == "sensors_completed":
        status = "passaram" if payload.get("passed") else "falharam"
        return f"Harness: {project}\nConferencias de {task_id} {status}."
    if event_type == "evaluation_brief_created":
        return f"Harness: {project}\n{task_id} esta pronto para avaliacao e revisao."
    if event_type == "evaluation_recorded":
        return f"Harness: {project}\nDecisao registrada para {task_id}: {payload.get('status')}."
    if event_type == "fix_brief_created":
        count = len(payload.get("blocking_findings") or [])
        return f"Harness: {project}\nFix brief criado para {task_id} com {count} bloqueador(es)."
    if event_type == "report_created":
        summary = payload.get("plain_summary")
        message = f"Harness: {project}\nRelatorio final criado para {task_id}."
        if summary:
            message += f"\n\n{summary}"
        return message
    return f"Harness: {project}\nEvento {event_type} em {task_id}."


def append_and_maybe_notify_event(
    root: Path,
    run_dir: Path,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    event = append_harness_event(root, event_type, payload, run_dir=run_dir)
    sync_agent_from_event(root, event)
    try:
        config = load_config(root)
        tconfig = telegram_config(config)
        if not config_bool(tconfig.get("enabled"), False):
            return
        if event_type not in set(str(item) for item in tconfig.get("notify_events", [])):
            return
        telegram_send_message(config, telegram_event_message(root, run_dir, event_type, payload))
    except Exception as exc:
        append_jsonl(
            telegram_root(root) / "notify-errors.jsonl",
            {"ts": utc_now(), "event_type": event_type, "error": str(exc)},
        )


def maybe_warn_unevaluated_runs(root: Path, config: dict[str, Any], task_id: str | None = None) -> None:
    policy = config.get("policy", {})
    if not policy.get("warn_on_unevaluated_runs", False):
        return

    unevaluated = find_unevaluated_runs(root, task_id)
    if not unevaluated:
        return

    scope = f" para {task_id}" if task_id else ""
    print(
        f"Aviso: {len(unevaluated)} run(s){scope} ainda nao tem avaliacao registrada.",
        file=sys.stderr,
    )
    for item in unevaluated[:10]:
        sensors = "com sensores" if item["has_sensors"] else "sem sensores"
        run_path = to_posix(relative_to_root(root, Path(item["run_dir"])))
        print(
            f"- {item['task_id']} {item['run_id']} ({sensors}): {run_path}",
            file=sys.stderr,
        )
    if len(unevaluated) > 10:
        print(f"- ... mais {len(unevaluated) - 10} run(s)", file=sys.stderr)


def summarize_context(root: Path) -> str:
    manifest = read_json(context_manifest_path(root), [])
    if not manifest:
        return "- Nenhum arquivo de contexto ingerido ainda."
    lines = []
    for item in manifest:
        lines.append(f"- {item['kind']}: {item['stored_path']} (origem: {item['source']})")
    return "\n".join(lines)


def command_init(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    if not root.exists():
        if not args.create:
            raise SystemExit(
                f"Diretorio do repo nao existe: {root}\n"
                "O Harness nao cria o repo por padrao para evitar inicializar no caminho errado. "
                "Crie/clone o app primeiro ou use `init --create` explicitamente."
            )
        root.mkdir(parents=True, exist_ok=True)
    require_existing_root(root)
    require_safe_branch(root, args, "init")
    hroot = harness_root(root)
    for relative in [
        "context",
        "tasks",
        "contracts",
        "runs",
        "evaluations",
        "reports",
        "queue",
        "supervisor",
        "checkpoints",
        "artifacts",
        "dashboard",
        "dashboard/hub",
        "agents",
        "memory",
        "plugins",
        "security",
        "github",
        "telegram",
        "inbox/telegram/media",
    ]:
        (hroot / relative).mkdir(parents=True, exist_ok=True)

    sensors = args.sensor if args.sensor else detect_default_sensors(root)
    config = {
        "version": 1,
        "runner_version": VERSION,
        "project_name": args.name or root.name,
        "created_at": utc_now(),
        "default_sensors": sensors,
        "required_context": [],
        "evaluation_policy": DEFAULT_EVALUATION_POLICY,
        "review_policy": DEFAULT_REVIEW_POLICY,
        "failure_policy": DEFAULT_FAILURE_POLICY,
        "operation_profiles": DEFAULT_OPERATION_PROFILES,
        "active_profile": "balanced",
        "profiles": {},
        "budgets": {},
        "github": DEFAULT_GITHUB_CONFIG,
        "telegram": DEFAULT_TELEGRAM_CONFIG,
        "protected_branches": DEFAULT_PROTECTED_BRANCHES,
        "sensor_execution_requires_review": True,
        "policy": {
            "context_preflight_required_before_start": True,
            "record_evidence_before_done": True,
            "cache_context_preflight": True,
        },
    }

    if not config_path(root).exists() or args.force:
        write_json(config_path(root), config)

    if not tasks_index_path(root).exists():
        write_json(tasks_index_path(root), [])

    if not context_manifest_path(root).exists():
        write_json(context_manifest_path(root), [])

    if not queue_path(root).exists():
        write_json(queue_path(root), [])

    if not memory_index_path(root).exists():
        write_json(memory_index_path(root), [])

    if not plugin_registry_path(root).exists():
        save_plugins(root, [])

    if not artifacts_index_path(root).exists():
        write_json(artifacts_index_path(root), [])

    if not agent_registry_path(root).exists():
        write_json(agent_registry_path(root), {"agents": [], "updated_at": utc_now()})

    if not hub_repo_registry_path(root).exists():
        write_json(hub_repo_registry_path(root), {"repos": [str(root)], "updated_at": utc_now()})

    if not event_stream_path(root).exists():
        write_text(event_stream_path(root), "")

    progress = hroot / "progress.md"
    if not progress.exists():
        write_text(
            progress,
            "# Progresso do Harness\n\n"
            f"Inicializado: {utc_now()}\n\n"
            "## Atual\n\n"
            "- Nenhuma task ativa ainda.\n",
        )

    gitignore = hroot / ".gitignore"
    if not gitignore.exists():
        write_text(
            gitignore,
            "# Por padrao, versionar apenas o protocolo enxuto do Harness.\n"
            "# Execucoes, contexto copiado e outputs grandes ficam locais.\n"
            "*\n"
            "!.gitignore\n"
            "!config.json\n"
            "!progress.md\n"
            "!tasks/\n"
            "!tasks/**\n"
            "!contracts/\n"
            "!contracts/**\n"
            "!reports/\n"
            "!reports/**\n",
        )

    print(f"Harness inicializado em {hroot}")
    if sensors:
        print("Sensores padrao:")
        for sensor in sensors:
            print(f"- {sensor}")
        print("Observacao: sensores exigem revisao explicita antes de executar.")
    else:
        print("Nenhum sensor padrao detectado. Adicione sensores ao criar contratos.")


def command_ingest(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "ingest")
    source = Path(args.file).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Arquivo nao encontrado: {source}")
    assert_inside_root(root, source, label=f"ingest source `{args.file}`")

    stored_name = f"{args.kind}-{slugify(source.stem)}{source.suffix.lower()}"
    target = harness_root(root) / "context" / stored_name
    stored_path_rel = to_posix(target.relative_to(root))
    source_key = normalize_path_key(source)
    source_str = relative_to_root(root, source)

    manifest = read_json(context_manifest_path(root), [])

    for existing in manifest:
        existing_source = existing.get("source", "")
        existing_source_key = normalize_path_key(resolve_repo_path(root, existing_source))
        if (
            existing.get("stored_path") == stored_path_rel
            and existing_source_key != source_key
        ):
            raise SystemExit(
                f"stored_path '{stored_path_rel}' ja esta em uso por '{existing.get('source')}'. "
                f"Use --kind diferente ou renomeie o arquivo de origem para evitar colisao."
            )

    manifest = [
        entry
        for entry in manifest
        if not (
            entry.get("kind") == args.kind
            and normalize_path_key(resolve_repo_path(root, entry.get("source", ""))) == source_key
        )
    ]

    shutil.copyfile(source, target)
    source_stat = source.stat()
    source_hash = file_sha256(source)

    manifest.append(
        {
            "kind": args.kind,
            "source": source_str,
            "stored_path": stored_path_rel,
            "source_size": source_stat.st_size,
            "source_mtime": datetime.fromtimestamp(source_stat.st_mtime, timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "source_sha256": source_hash,
            "stored_sha256": file_sha256(target),
            "ingested_at": utc_now(),
        }
    )
    write_json(context_manifest_path(root), manifest)
    print(f"Ingerido {source.name} como {stored_path_rel}")
    print(f"sha256: {source_hash}")


def first_heading_or_filename(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def create_task(root: Path, title: str, body: str, source: str) -> TaskRecord:
    task_id = next_task_id(root)
    task_path = harness_root(root) / "tasks" / f"{task_id}-{slugify(title)}.md"
    content = (
        f"# {task_id} - {title}\n\n"
        f"Status: planejada\n"
        f"Origem: {source}\n"
        f"Criada: {utc_now()}\n\n"
        "## O que construir\n\n"
        f"{body.strip() if body.strip() else 'TODO: descrever a fatia vertical.'}\n\n"
        "## Criterios de aceite\n\n"
        "- [ ] TODO: definir comportamento observavel.\n\n"
        "## Fora de escopo\n\n"
        "- TODO: definir o que esta task nao deve alterar.\n"
    )
    write_text(task_path, content)

    task: TaskRecord = {
        "task_id": task_id,
        "title": title,
        "status": "planned",
        "source": to_posix(source) if source and source != "manual" else source,
        "task_file": to_posix(task_path.relative_to(root)),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    tasks = load_tasks(root)
    tasks.append(task)
    save_tasks(root, tasks)
    append_harness_event(root, "task_created", {"task_id": task_id, "title": title, "source": source})
    return task


def short_title(text: str, fallback: str = "Prompt do Telegram") -> str:
    for line in text.splitlines():
        cleaned = plain_clean(line)
        if cleaned:
            return cleaned[:90]
    return fallback


def create_task_from_telegram_item(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    title = short_title(item.get("prompt_text") or "", fallback=f"Telegram {item.get('id')}")
    body = render_task_body_from_telegram(item)
    return create_task(root, title, body, f"telegram:{item.get('id')}")


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
                    harness_script=Path(__file__).resolve(),
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
                message = f"Budget {active['task_id']}: profile={budget.get('name')} minutes={budget.get('time_budget_minutes')} fixes={budget.get('max_fix_attempts')}"
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
                f"{pending['task_id']} [{pending['status']}] {pending['title']}" if pending else "Nenhuma task pendente.",
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
        append_harness_event(root, "telegram_update_rejected", {"telegram_item_id": item_id, "chat_id": chat_id}, source="telegram")
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


def command_task_create(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="task create")
    body = args.body or ""
    if args.from_file:
        source_path = Path(args.from_file).expanduser().resolve()
        if not source_path.exists():
            raise SystemExit(f"Arquivo nao encontrado: {source_path}")
        body = read_text(source_path)
        source = str(source_path)
    else:
        source = "manual"
    task = create_task(root, args.title, body, source)
    print(f"Criada {task['task_id']}: {task['title']}")
    print(task["task_file"])


def command_task_import(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="task import")
    for raw in args.files:
        source = Path(raw).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"Arquivo nao encontrado: {source}")
        body = read_text(source)
        title = first_heading_or_filename(source, body)
        task = create_task(root, title, body, str(source))
        print(f"Importado {source.name} -> {task['task_id']}: {title}")


def command_task_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    tasks = load_tasks(root)
    if not tasks:
        print("Nenhuma task ainda.")
        return
    for task in tasks:
        print(f"{task['task_id']} [{task['status']}] {task['title']}")


def command_pick(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    for task in load_tasks(root):
        if task["status"] not in {"passed", "done"}:
            print(f"{task['task_id']} [{task['status']}] {task['title']}")
            print(task["task_file"])
            return
    print("Nenhuma task pendente.")


def command_queue_add(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="queue add")
    task_id = None
    title = args.title
    body = args.body or ""
    if re.match(r"^TASK-\d+$", args.title):
        task = find_task(root, args.title)
        task_id = task["task_id"]
        title = task["title"]
        body = read_text(root / task["task_file"])
    elif args.create_task:
        task = create_task(root, title, body, "queue")
        task_id = task["task_id"]
    queue = load_queue(root)
    if not args.force and task_id:
        for item in queue:
            if item.get("task_id") == task_id and item.get("status") in {"queued", "active"}:
                raise SystemExit(f"{task_id} ja esta na fila como {item.get('id')}. Use --force para duplicar.")
    item = {
        "id": next_queue_id(root),
        "task_id": task_id,
        "title": title,
        "body": body,
        "status": "queued",
        "priority": args.priority,
        "profile": args.profile,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    queue.append(item)
    save_queue(root, queue)
    append_harness_event(
        root,
        "queue_item_added",
        {"queue_id": item["id"], "task_id": task_id, "title": title, "priority": args.priority},
    )
    print(f"{item['id']} queued: {title}")
    if task_id:
        print(f"Task: {task_id}")


def command_queue_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    items = sorted_queue_items(load_queue(root))
    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return
    if not items:
        print("Fila vazia.")
        return
    for item in items:
        task = f" {item.get('task_id')}" if item.get("task_id") else ""
        print(f"{item['id']} [{item.get('status')}] p{item.get('priority')}{task} - {item.get('title')}")


def command_queue_next(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    item = active_queue_item(root) if args.include_active else None
    item = item or next_queued_item(root)
    if not item:
        print("Nenhum item pendente na fila.")
        return
    if args.activate and item.get("status") == "queued":
        require_safe_branch(root, args, "queue next --activate")
        item = update_queue_item(root, item["id"], status="active", activated_at=utc_now())
        append_harness_event(
            root,
            "queue_item_activated",
            {"queue_id": item["id"], "task_id": item.get("task_id"), "title": item.get("title")},
        )
    print(f"{item['id']} [{item.get('status')}] {item.get('title')}")
    if item.get("task_id"):
        print(f"Task: {item.get('task_id')}")
    if item.get("body"):
        print("\n" + str(item.get("body")).strip())


def command_queue_done(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="queue done")
    item = update_queue_item(
        root,
        args.queue_id,
        status=args.status,
        completed_at=utc_now() if args.status == "done" else None,
        note=args.note or "",
    )
    if item.get("task_id") and args.status == "done":
        try:
            update_task(root, item["task_id"], status="done")
        except SystemExit:
            pass
    append_harness_event(
        root,
        "queue_item_closed",
        {"queue_id": item["id"], "task_id": item.get("task_id"), "status": item.get("status"), "note": args.note or ""},
    )
    print(f"{item['id']} -> {item['status']}")


def command_profile_add(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="profile add")
    config = load_config(root)
    profiles = config.setdefault("profiles", {})
    profiles[args.name] = {
        "model": args.model,
        "sandbox": args.sandbox,
        "approval": args.approval,
        "description": args.description or "",
    }
    write_json(config_path(root), config)
    print(f"Profile salvo: {args.name}")


def command_profile_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    custom = config.get("profiles", {})
    if not custom and not operation_profiles(config):
        print("Nenhum profile configurado.")
        return
    for name, profile in operation_profiles(config).items():
        active = " *" if name == config.get("active_profile", "balanced") else ""
        print(f"{name}{active}: {profile.get('description', '')} [{profile.get('sensor_tier')}]")
    for name, profile in custom.items():
        print(
            f"{name}: model={profile.get('model') or '-'} "
            f"sandbox={profile.get('sandbox') or '-'} approval={profile.get('approval') or '-'}"
        )


def command_profile_set(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="profile set")
    config = load_config(root)
    active_profile_name(config, args.name)
    config["active_profile"] = args.name
    write_json(config_path(root), config)
    print(f"Profile ativo: {args.name}")


def command_budget_set(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="budget set")
    config = load_config(root)
    budgets = config.setdefault("budgets", {})
    budgets[args.name] = {
        "max_tokens": args.max_tokens,
        "timeout_minutes": args.timeout_minutes,
        "max_fix_attempts": args.max_fix_attempts,
    }
    write_json(config_path(root), config)
    print(f"Budget salvo: {args.name}")


def command_budget_task_set(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="budget task-set")
    budget = {
        "profile": args.profile,
        "time_budget_minutes": args.minutes,
        "max_fix_attempts": args.max_fix_attempts,
        "sensor_tier": args.sensor_tier,
    }
    update_task(root, args.task_id, budget={k: v for k, v in budget.items() if v is not None})
    print(f"Budget da task atualizado: {args.task_id}")


def command_budget_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    budgets = config.get("budgets", {})
    if not budgets:
        print("Nenhum budget customizado.")
        return
    for name, budget in budgets.items():
        print(
            f"{name}: max_tokens={budget.get('max_tokens')} "
            f"timeout_minutes={budget.get('timeout_minutes')} "
            f"max_fix_attempts={budget.get('max_fix_attempts')}"
        )


def command_memory_remember(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="memory remember")
    entries = load_memory(root)
    entry = {
        "id": next_memory_id(root),
        "text": args.text,
        "tags": args.tag or [],
        "task_id": args.task_id,
        "created_at": utc_now(),
    }
    entries.append(entry)
    save_memory(root, entries)
    print(f"{entry['id']} memorado.")


def command_memory_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    entries = load_memory(root)
    if args.tag:
        entries = [entry for entry in entries if args.tag in set(entry.get("tags") or [])]
    if args.search:
        needle = args.search.lower()
        entries = [entry for entry in entries if needle in str(entry.get("text", "")).lower()]
    if not entries:
        print("Nenhuma memoria encontrada.")
        return
    for entry in entries[-args.limit :]:
        tags = ", ".join(entry.get("tags") or [])
        suffix = f" [{tags}]" if tags else ""
        print(f"{entry['id']}: {entry.get('text')}{suffix}")


def command_contract(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_safe_branch(root, args, "contract")
    config = load_config(root)
    task = find_task(root, args.task_id)
    task_body = read_text(root / task["task_file"])
    goal = args.goal or task["title"]
    criteria = args.criteria or extract_checklist(task_body)
    sensors = args.sensor or config.get("default_sensors", [])
    if args.full_sensor and not args.sensor:
        sensors = args.full_sensor
    sensor_tiers = {
        "smoke": args.smoke_sensor or [],
        "affected": args.affected_sensor or [],
        "full": args.full_sensor or sensors,
    }
    out_of_scope = args.out or extract_out_of_scope(task_body)
    required_docs = args.required_doc or []

    contract = {
        "task_id": args.task_id,
        "goal": goal,
        "acceptance_criteria": criteria,
        "expected_files": args.expected or [],
        "required_docs": required_docs,
        "required_sensors": sensors,
        "sensor_tiers": sensor_tiers,
        "sensors_reviewed": bool(args.reviewed_sensors),
        "out_of_scope": out_of_scope,
        "source_task_file": to_posix(task["task_file"]),
        "created_at": utc_now(),
        "notes": args.notes or "",
    }
    write_json(contract_file_path(root, args.task_id), contract)
    update_task(root, args.task_id, status="contracted")
    print(f"Contrato escrito para {args.task_id}: {contract_file_path(root, args.task_id)}")
    if not criteria:
        print("Aviso: nenhum criterio de aceite encontrado. Adicione --criteria ou edite o contrato.")
    if not sensors:
        print("Aviso: nenhum sensor configurado. Adicione --sensor ou edite o contrato.")
    elif not args.reviewed_sensors:
        print("Aviso: sensores ainda nao estao marcados como revisados. Use --reviewed em `sensors` ou recrie o contrato com --reviewed-sensors.")
    if args.smoke_sensor or args.affected_sensor or args.full_sensor:
        print("Sensor tiers:")
        for tier, commands in sensor_tiers.items():
            print(f"- {tier}: {len(commands)} comando(s)")
    if required_docs:
        print("Documentos obrigatorios da task:")
        for doc in required_docs:
            print(f"- {doc}")


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
        f"`python {Path(__file__).resolve()} --repo {root} sensors {task['task_id']} --tier quick --reviewed`\n\n"
        "Para o fechamento final, rode:\n\n"
        f"`python {Path(__file__).resolve()} --repo {root} sensors {task['task_id']} --tier full --reviewed`\n\n"
        "Em seguida, peca avaliacao contratual e review Greptile-style usando os handoffs gerados por:\n\n"
        f"`python {Path(__file__).resolve()} --repo {root} evaluate {task['task_id']}`\n\n"
        f"Diretorio da run: `{run_dir}`\n"
    )


def command_start(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="start")
    config = load_config(root)
    maybe_warn_unevaluated_runs(root, config, args.task_id)
    task = find_task(root, args.task_id)
    contract = load_contract(root, args.task_id)
    require_context_preflight(
        root,
        args.task_id,
        skip_preflight=getattr(args, "skip_preflight", False),
    )
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    run_dir = harness_root(root) / "runs" / args.task_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "run.json",
        {
            "task_id": args.task_id,
            "run_id": run_id,
            "created_at": utc_now(),
            "status": "started",
            "root": str(root),
        },
    )
    write_text(run_dir / "builder-brief.md", render_builder_brief(root, task, contract, run_dir))
    create_checkpoint(root, args.task_id, "run_started", run_dir)
    append_and_maybe_notify_event(root, run_dir, "run_started", {"task_id": args.task_id, "run_id": run_id})
    update_task(root, args.task_id, status="in_progress")
    print(f"Run iniciada para {args.task_id} em {run_dir}")
    print(f"Brief do implementador: {run_dir / 'builder-brief.md'}")


def command_sensors(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="sensors")
    contract = load_contract(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)
    tier = args.tier
    if tier == "quick":
        tier = fastest_available_sensor_tier(contract)
    commands = args.command or sensors_for_tier(contract, tier)
    if commands and not (args.reviewed or contract.get("sensors_reviewed")):
        raise SystemExit(
            "Execucao bloqueada: sensores ainda nao foram revisados.\n"
            "Revise os comandos no contrato/brief da run e rode novamente com `sensors --reviewed`, "
            "ou marque o contrato com `--reviewed-sensors` ao cria-lo."
        )

    results = []
    for command in commands:
        started = time.time()
        print(f"Rodando sensor: {command}")
        argv = split_sensor_command(command)
        if not argv:
            results.append(
                make_sensor_result(
                    command=command,
                    argv=argv,
                    resolved_argv=argv,
                    shell=bool(args.allow_shell),
                    exit_code=2,
                    duration_ms=0,
                    stderr="Comando de sensor vazio.",
                )
            )
            continue
        resolved_argv = resolve_sensor_argv(argv) if not args.allow_shell else argv
        try:
            result = subprocess.run(
                command if args.allow_shell else resolved_argv,
                cwd=root,
                shell=args.allow_shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            duration_ms = int((time.time() - started) * 1000)
            results.append(
                make_sensor_result(
                    command=command,
                    argv=argv,
                    resolved_argv=resolved_argv,
                    shell=bool(args.allow_shell),
                    exit_code=result.returncode,
                    duration_ms=duration_ms,
                    stdout=result.stdout[-args.max_output_chars :],
                    stderr=result.stderr[-args.max_output_chars :],
                )
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - started) * 1000)
            results.append(
                make_sensor_result(
                    command=command,
                    argv=argv,
                    resolved_argv=resolved_argv,
                    shell=bool(args.allow_shell),
                    exit_code=124,
                    duration_ms=duration_ms,
                    stdout=(exc.stdout or "")[-args.max_output_chars :],
                    stderr=(exc.stderr or "")[-args.max_output_chars :],
                    timeout=True,
                )
            )
        except FileNotFoundError as exc:
            duration_ms = int((time.time() - started) * 1000)
            results.append(
                make_sensor_result(
                    command=command,
                    argv=argv,
                    resolved_argv=resolved_argv,
                    shell=bool(args.allow_shell),
                    exit_code=127,
                    duration_ms=duration_ms,
                    stderr=str(exc),
                )
            )

    passed = bool(commands) and all(item["exit_code"] == 0 for item in results)
    payload = {
        "task_id": args.task_id,
        "run_dir": str(run_dir),
        "created_at": utc_now(),
        "tier": tier,
        "reviewed": bool(args.reviewed or contract.get("sensors_reviewed")),
        "shell": bool(args.allow_shell),
        "passed": passed,
        "results": results,
    }
    write_json(run_dir / f"sensors-{tier}.json", payload)
    if tier in {"full", "all"} or not (run_dir / "sensors.json").exists():
        write_json(run_dir / "sensors.json", payload)
    create_checkpoint(root, args.task_id, f"sensors_{tier}", run_dir, {"sensors": payload})
    append_and_maybe_notify_event(
        root,
        run_dir,
        "sensors_completed",
        {"task_id": args.task_id, "tier": tier, "passed": passed, "commands": commands},
    )
    task_status = "sensors_passed" if passed else "sensors_failed"
    if passed and run_evaluation_status(root, args.task_id, run_dir) == "pass":
        task_status = "passed"
    update_task(root, args.task_id, status=task_status)

    if not commands:
        print(f"Nenhum sensor configurado para tier `{tier}`.")
    print(f"Sensores {tier} {'passaram' if passed else 'falharam'}: {run_dir / f'sensors-{tier}.json'}")


def command_fix_brief(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="fix-brief")
    config = load_config(root)
    task = find_task(root, args.task_id)
    contract = load_contract(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)
    review_parts: list[str] = []
    evaluator_parts: list[str] = []
    if args.review_file:
        for file in args.review_file:
            review_parts.append(read_text(Path(file).expanduser().resolve()))
    if args.review_note:
        review_parts.extend(args.review_note)
    if args.evaluator_file:
        for file in args.evaluator_file:
            evaluator_parts.append(read_text(Path(file).expanduser().resolve()))
    if args.evaluator_note:
        evaluator_parts.extend(args.evaluator_note)
    review_text = "\n\n".join(review_parts)
    evaluator_text = "\n\n".join(evaluator_parts)
    brief = render_fix_brief(root, task, contract, run_dir, review_text, evaluator_text, config)
    path = next_fix_brief_path(run_dir)
    write_text(path, brief)
    write_text(run_dir / "fix-brief-latest.md", brief)
    blockers = blocking_findings_from_review(review_text, config)
    update_task(root, args.task_id, status="needs_work" if blockers else "review_followup")
    append_and_maybe_notify_event(
        root,
        run_dir,
        "fix_brief_created",
        {"task_id": args.task_id, "path": str(path), "blocking_findings": blockers},
    )
    print(f"Fix brief escrito: {path}")
    if blockers:
        print(f"Bloqueadores detectados: {len(blockers)}")
    else:
        print("Nenhum bloqueador P0/P1 detectado automaticamente.")


def command_speed_pass(args: argparse.Namespace) -> None:
    tier = "quick" if args.command == "quick-pass" else "full"
    sensor_args = argparse.Namespace(
        repo=args.repo,
        allow_main=args.allow_main,
        task_id=args.task_id,
        command=args.command_override,
        tier=tier,
        reviewed=args.reviewed,
        allow_shell=args.allow_shell,
        timeout=args.timeout,
        max_output_chars=args.max_output_chars,
    )
    command_sensors(sensor_args)
    root = root_from_args(args)
    run_dir = latest_run_dir(root, args.task_id)
    resolved_tier = fastest_available_sensor_tier(load_contract(root, args.task_id)) if tier == "quick" else tier
    payload = read_json(run_dir / f"sensors-{resolved_tier}.json", {})
    if not payload.get("passed"):
        raise SystemExit(f"{args.command} interrompido: sensores {resolved_tier} falharam.")
    evaluate_args = argparse.Namespace(
        repo=args.repo,
        allow_main=args.allow_main,
        task_id=args.task_id,
        status=None,
        notes=None,
        notes_file=None,
        gap=None,
    )
    command_evaluate(evaluate_args)


def next_run_checkpoint_path(run_dir: Path) -> Path:
    checkpoints = run_dir / "checkpoints"
    existing = sorted(checkpoints.glob("checkpoint-*.json"))
    numbers = []
    for path in existing:
        match = re.match(r"checkpoint-(\d+)\.json$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return checkpoints / f"checkpoint-{(max(numbers) + 1) if numbers else 1:03d}.json"


def command_checkpoint_create(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="checkpoint create")
    find_task(root, args.task_id)
    run_dir = latest_run_dir_or_none(root, args.task_id)
    payload = {
        "task_id": args.task_id,
        "summary": args.summary or "",
        "next_steps": args.next or [],
        "created_at": utc_now(),
        "run_dir": str(run_dir) if run_dir else None,
        "git_status": git_output(root, ["status", "--short"]) if is_git_repo(root) else "",
    }
    if run_dir:
        path = next_run_checkpoint_path(run_dir)
        write_json(path, payload)
        write_json(run_dir / "checkpoints" / "latest.json", payload)
    else:
        path = create_checkpoint(root, args.task_id, args.summary or "manual", extra=payload)
    create_checkpoint(root, args.task_id, args.summary or "manual", run_dir=run_dir, extra=payload)
    append_harness_event(
        root,
        "checkpoint_created",
        {"task_id": args.task_id, "summary": args.summary or "", "next_steps": args.next or []},
        run_dir=run_dir,
    )
    print(f"Checkpoint escrito: {path}")


def command_checkpoint_resume_plan(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    find_task(root, args.task_id)
    run_dir = latest_run_dir_or_none(root, args.task_id)
    checkpoint: dict[str, Any] = {}
    if run_dir and (run_dir / "checkpoints" / "latest.json").exists():
        checkpoint = read_json(run_dir / "checkpoints" / "latest.json", {})
    else:
        latest = latest_checkpoint_path(root, args.task_id)
        if latest:
            checkpoint = read_json(latest, {})
    if not checkpoint:
        checkpoint = {"task_id": args.task_id, "summary": "Sem checkpoint anterior.", "next_steps": []}
    plan = render_resume_brief(
        root,
        args.task_id,
        checkpoint,
        harness_script=Path(__file__).resolve(),
    )
    if checkpoint.get("summary"):
        plan += f"\n## Ultimo resumo\n\n{checkpoint.get('summary')}\n"
    if checkpoint.get("next_steps"):
        plan += "\n## Proximos passos salvos\n\n" + "\n".join(
            f"- {step}" for step in checkpoint.get("next_steps", [])
        ) + "\n"
    target_dir = run_dir if run_dir else checkpoints_root(root, args.task_id)
    path = target_dir / "resume-plan.md"
    write_text(path, plan)
    print(plan)
    print(f"\nResume plan escrito: {path}")


def command_artifacts_add(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="artifacts add")
    source = resolve_repo_path(root, args.path)
    if not source.exists():
        raise SystemExit(f"Artifact nao encontrado: {source}")
    assert_inside_root(root, source, label="artifact")
    task_id = args.task_id
    run_id = None
    target_path = source
    if args.copy:
        run_dir = latest_run_dir_or_none(root, task_id)
        run_id = run_dir.name if run_dir else "manual"
        target_dir = artifacts_root(root) / task_id / run_id
        target_path = target_dir / source.name
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target_path)
    entry = {
        "id": artifact_id(task_id, target_path),
        "task_id": task_id,
        "run_id": run_id,
        "path": to_posix(target_path.relative_to(root)),
        "kind": args.kind or target_path.suffix.lstrip(".") or "file",
        "label": args.label or target_path.name,
        "size": target_path.stat().st_size,
        "sha256": file_sha256(target_path),
        "created_at": utc_now(),
    }
    artifacts = [item for item in load_artifacts(root) if item.get("id") != entry["id"]]
    artifacts.append(entry)
    save_artifacts(root, artifacts)
    print(f"Artifact registrado: {entry['id']} {entry['path']}")


def command_artifacts_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    artifacts = collect_run_artifacts(root, args.task_id)
    if args.json:
        print(json.dumps(artifacts, indent=2, ensure_ascii=False))
        return
    if not artifacts:
        print("Nenhum artifact encontrado.")
        return
    for item in artifacts:
        print(f"{item['id']} {item.get('task_id')} {item.get('label')} - {item.get('path')}")


def command_plugin_add(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="plugin add")
    plugins = [plugin for plugin in load_plugins(root) if plugin.get("name") != args.name]
    plugins.append(
        {
            "name": args.name,
            "path": args.path,
            "command": args.command,
            "events": args.event or [],
            "description": args.description or "",
            "enabled": not args.disabled,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
    )
    save_plugins(root, plugins)
    print(f"Plugin registrado: {args.name}")


def command_plugin_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    plugins = load_plugins(root)
    if not plugins:
        print("Nenhum plugin registrado.")
        return
    for plugin in plugins:
        enabled = "on" if config_bool(plugin.get("enabled"), True) else "off"
        location = plugin.get("path") or plugin.get("command") or "-"
        print(f"{plugin.get('name')} [{enabled}] {location} - {plugin.get('description', '')}")


def command_plugin_set_enabled(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation=f"plugin {args.plugin_command}")
    plugins = load_plugins(root)
    for plugin in plugins:
        if plugin.get("name") == args.name:
            plugin["enabled"] = args.plugin_command == "enable"
            plugin["updated_at"] = utc_now()
            save_plugins(root, plugins)
            print(f"Plugin {args.name}: {'on' if plugin['enabled'] else 'off'}")
            return
    raise SystemExit(f"Plugin nao encontrado: {args.name}")


def command_plugin_run(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="plugin run")
    plugins = runnable_plugins(load_plugins(root), args.event)
    if not plugins:
        print("Nenhum plugin habilitado para este evento.")
        return
    try:
        require_plugin_run_allowed(dry_run=args.dry_run, reviewed=args.reviewed)
    except PluginPolicyError as exc:
        raise SystemExit(str(exc)) from exc
    results = []
    for plugin in plugins:
        try:
            command = render_plugin_command(str(plugin["command"]), root, args.task_id or "", args.event)
        except PluginPolicyError as exc:
            raise SystemExit(str(exc)) from exc
        argv = split_sensor_command(command)
        print(f"Plugin {plugin.get('name')}: {command}")
        if args.dry_run:
            results.append({"plugin": plugin.get("name"), "command": command, "dry_run": True})
            continue
        result = subprocess.run(
            resolve_sensor_argv(argv),
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout,
        )
        results.append(
            {
                "plugin": plugin.get("name"),
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
    append_jsonl(harness_root(root) / "plugins" / "runs.jsonl", {"ts": utc_now(), "event": args.event, "results": results})


def command_security_scan(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    files = iter_security_scan_files(root, tracked_only=not args.include_untracked)
    inbox_files = iter_security_inbox_files(root)
    findings: list[dict[str, Any]] = []
    for file in files:
        if file.exists():
            findings.extend(scan_file_for_secrets(root, file))
    for file in inbox_files:
        if file.exists():
            findings.extend(scan_file_for_secrets(root, file, allow_harness=True))
    report = {
        "created_at": utc_now(),
        "tracked_only": not args.include_untracked,
        "files_scanned": len(files),
        "inbox_files_scanned": len(inbox_files),
        "findings": findings,
    }
    path = security_root(root) / "scan-latest.json"
    write_json(path, report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(
            f"Security scan: {len(findings)} finding(s), "
            f"{len(files)} arquivo(s), {len(inbox_files)} inbox Telegram."
        )
        for finding in findings:
            print(f"- {finding['kind']} {finding['path']}:{finding['line']}")
        print(f"Relatorio: {path}")
    if findings:
        raise SystemExit(1)


def command_security_status(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    path = security_root(root) / "scan-latest.json"
    if not path.exists():
        print("Nenhum security scan registrado.")
        return
    report = read_json(path, {})
    print(f"Ultimo scan: {report.get('created_at')}")
    print(f"Findings: {len(report.get('findings') or [])}")


def hub_repo_paths(args: argparse.Namespace) -> list[Path]:
    raw_paths = list(getattr(args, "watch_repo", None) or [])
    if not raw_paths:
        root = root_from_args(args)
        raw_paths = load_hub_repo_registry(root) or [args.repo]
    paths: list[Path] = []
    seen: set[str] = set()
    for raw in raw_paths:
        path = Path(raw).expanduser().resolve()
        key = normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def command_dashboard_html(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    result = write_dashboard_html(root)
    print(f"Dashboard HTML: {result['path']}")


def command_dashboard_hub(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    paths = hub_repo_paths(args)
    result = write_dashboard_hub(root, paths, args.refresh_seconds)
    print(f"Harness Hub: {result['path']}")
    print(f"Repos monitorados: {len(result['state']['repos'])}")
    for repo in result["state"]["repos"]:
        suffix = f" ({repo.get('error')})" if repo.get("error") else ""
        print(f"- {repo.get('project')} [{repo.get('phase')}]{suffix}: {repo.get('root')}")


def command_dashboard_hub_add_repo(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    repos = load_hub_repo_registry(root)
    added: list[str] = []
    for raw in args.path:
        repo = Path(raw).expanduser().resolve()
        require_existing_root(repo)
        key = normalize_path_key(repo)
        if key not in {normalize_path_key(Path(item)) for item in repos}:
            repos.append(str(repo))
            added.append(str(repo))
    save_hub_repo_registry(root, repos)
    append_harness_event(root, "hub_repo_registry_updated", {"added": added, "repos": repos}, source="hub")
    print(f"Repos no hub: {len(load_hub_repo_registry(root))}")
    for repo in added:
        print(f"- adicionado: {repo}")


def command_dashboard_hub_remove_repo(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    remove = {normalize_path_key(Path(raw).expanduser().resolve()) for raw in args.path}
    repos = [repo for repo in load_hub_repo_registry(root) if normalize_path_key(Path(repo)) not in remove]
    save_hub_repo_registry(root, repos)
    append_harness_event(root, "hub_repo_registry_updated", {"removed": list(remove), "repos": repos}, source="hub")
    print(f"Repos no hub: {len(repos)}")


def command_dashboard_hub_list_repos(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    repos = load_hub_repo_registry(root)
    if args.json:
        print(json.dumps({"repos": repos}, indent=2, ensure_ascii=False))
        return
    if not repos:
        print("Nenhum repo registrado no hub.")
        return
    for repo in repos:
        print(f"- {repo}")


def command_dashboard_hub_state(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    paths = hub_repo_paths(args)
    state = collect_dashboard_hub_state(paths)
    path = dashboard_hub_root(root) / "hub-state.json"
    write_json(path, state)
    print(json.dumps(state, indent=2, ensure_ascii=False) if args.json else f"Hub state: {path}")


def command_agent_register(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    task_title = ""
    if args.task_id:
        try:
            task_title = str(find_task(root, args.task_id).get("title") or "")
        except SystemExit:
            task_title = ""
    agent = upsert_agent(
        root,
        args.agent_id,
        name=args.name or hub_agent_name_for_role(args.role),
        role=args.role,
        state=args.state,
        task_id=args.task_id or "",
        task_title=task_title,
        phase=args.phase or args.role,
        speech=args.speech or "",
        run_dir=args.run_dir or "",
        surface_id=args.surface_id or "",
    )
    append_harness_event(
        root,
        "agent_registered",
        {"agent_id": args.agent_id, "task_id": args.task_id or "", "summary": agent.get("speech") or "Agent registrado."},
        task_id=args.task_id,
        agent_id=args.agent_id,
        source="agent",
    )
    print(f"Agent registrado: {agent['id']} [{agent['state']}]")


def command_agent_heartbeat(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    registry = load_agent_registry(root)
    agents = [agent for agent in registry.get("agents", []) if isinstance(agent, dict)]
    agent = next((item for item in agents if item.get("id") == args.agent_id), None)
    if not agent:
        raise SystemExit(f"Agent nao registrado: {args.agent_id}")
    agent["heartbeat_at"] = utc_now()
    agent["updated_at"] = agent["heartbeat_at"]
    if args.state:
        agent["state"] = args.state
        agent["status"] = agent_status_from_state(args.state)
    if args.speech:
        agent["speech"] = args.speech
    if args.surface_id:
        agent["surface_id"] = args.surface_id
    save_agent_registry(root, {"agents": agents, "updated_at": utc_now()})
    append_harness_event(
        root,
        "agent_heartbeat",
        {"agent_id": args.agent_id, "summary": args.speech or "Heartbeat recebido."},
        task_id=str(agent.get("task_id") or ""),
        agent_id=args.agent_id,
        source="agent",
    )
    print(f"Heartbeat: {args.agent_id}")


def command_agent_done(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    registry = load_agent_registry(root)
    agents = [agent for agent in registry.get("agents", []) if isinstance(agent, dict)]
    agent = next((item for item in agents if item.get("id") == args.agent_id), None)
    if not agent:
        raise SystemExit(f"Agent nao registrado: {args.agent_id}")
    agent["state"] = args.state
    agent["status"] = args.state
    agent["speech"] = args.speech or agent.get("speech") or ""
    agent["updated_at"] = utc_now()
    agent["heartbeat_at"] = agent["updated_at"]
    save_agent_registry(root, {"agents": agents, "updated_at": utc_now()})
    append_harness_event(
        root,
        "agent_done",
        {"agent_id": args.agent_id, "state": args.state, "summary": agent.get("speech") or "Agent finalizado."},
        task_id=str(agent.get("task_id") or ""),
        agent_id=args.agent_id,
        source="agent",
    )
    print(f"Agent {args.agent_id} -> {args.state}")


def command_agent_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    agents = load_agent_registry(root).get("agents", [])
    if args.json:
        print(json.dumps(agents, indent=2, ensure_ascii=False))
        return
    if not agents:
        print("Nenhum agent registrado.")
        return
    for agent in agents:
        print(f"- {agent.get('id')} [{agent.get('state')}] {agent.get('task_id') or '-'} - {agent.get('speech') or agent.get('name')}")


def command_events_list(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    events = read_recent_harness_events(root, limit=args.limit, task_id=args.task_id)
    if args.json:
        print(json.dumps(events, indent=2, ensure_ascii=False))
        return
    if not events:
        print("Nenhum evento registrado.")
        return
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        summary = payload.get("summary") or payload.get("message") or event.get("type")
        print(f"- {event.get('ts')} {event.get('type')} {event.get('task_id') or '-'}: {summary}")


def command_dashboard_hub_serve(args: argparse.Namespace) -> None:
    import functools
    import http.server

    root = prepared_repo(args)
    paths = hub_repo_paths(args)
    action_token = uuid.uuid4().hex
    cache_ttl_seconds = max(1.0, float(args.refresh_seconds) + 0.5)
    initial_state = collect_dashboard_hub_state(
        paths,
        action_token=action_token,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    directory = dashboard_hub_root(root)
    write_dashboard_hub_files(directory, initial_state, args.refresh_seconds)

    class HubHandler(http.server.SimpleHTTPRequestHandler):
        def send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def authorized(self, payload: dict[str, Any]) -> bool:
            supplied = self.headers.get("X-Harness-Hub-Token") or str(payload.get("action_token") or "")
            return hub_action_authorized(self.client_address[0], supplied, action_token)

        def local_request(self) -> bool:
            return hub_local_request_allowed(self.client_address[0])

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook
            if not self.local_request():
                self.send_json(403, {"ok": False, "error": "Hub local: acesso remoto bloqueado."})
                return
            request_path = urllib.parse.urlparse(self.path).path
            if request_path in {"/hub-state.json", "/state.json"}:
                if not self.authorized({}):
                    self.send_json(403, {"ok": False, "error": "Estado local nao autorizado."})
                    return
                state = collect_dashboard_hub_state(
                    paths,
                    action_token=action_token,
                    cache_ttl_seconds=cache_ttl_seconds,
                )
                write_json(directory / "hub-state.json", state)
                self.send_json(200, state)
                return
            if request_path == "/wmux-state.json":
                if not self.authorized({}):
                    self.send_json(403, {"ok": False, "error": "Estado local nao autorizado."})
                    return
                self.send_json(200, collect_wmux_state())
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            if not self.local_request():
                self.send_json(403, {"ok": False, "error": "Hub local: acesso remoto bloqueado."})
                return
            request_path = urllib.parse.urlparse(self.path).path
            if not request_path.startswith("/wmux/"):
                self.send_error(404)
                return
            try:
                payload = self.read_json_body()
            except json.JSONDecodeError as exc:
                self.send_json(400, {"ok": False, "error": f"JSON invalido: {exc}"})
                return
            if not self.authorized(payload):
                self.send_json(403, {"ok": False, "error": "Acao local nao autorizada."})
                return

            if request_path == "/wmux/focus":
                result = wmux_focus(payload)
            elif request_path == "/wmux/send":
                result = wmux_send_text(payload)
            elif request_path == "/wmux/new-terminal":
                result = wmux_new_terminal(payload)
            elif request_path == "/wmux/read-screen":
                result = wmux_read_screen(payload)
            else:
                result = {"ok": False, "error": "Acao wmux desconhecida."}
            append_harness_event(
                root,
                "hub_wmux_action",
                {
                    "path": request_path,
                    "ok": bool(result.get("ok")),
                    "surface_id": payload.get("surface_id") or result.get("surface_id"),
                    "summary": f"Hub executou {request_path}: {'ok' if result.get('ok') else 'falha'}",
                },
                source="hub",
            )
            self.send_json(200 if result.get("ok") else 400, result)

        def log_message(self, format: str, *values: Any) -> None:  # noqa: A002
            if args.quiet:
                return
            super().log_message(format, *values)

    handler = functools.partial(HubHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Harness Hub em http://{args.host}:{args.port}/")
    print("Repos:")
    for path in paths:
        print(f"- {path}")
    try:
        if args.once:
            server.handle_request()
        else:
            server.serve_forever()
    finally:
        server.server_close()


def command_dashboard_serve(args: argparse.Namespace) -> None:
    import functools
    import http.server

    root = prepared_repo(args)
    command_dashboard_html(argparse.Namespace(repo=args.repo))
    directory = dashboard_root(root)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard em http://{args.host}:{args.port}/")
    try:
        if args.once:
            server.handle_request()
        else:
            server.serve_forever()
    finally:
        server.server_close()


def supervisor_recommendation(root: Path, item: dict[str, Any]) -> str:
    task_id = item.get("task_id")
    if not task_id:
        return "Item de fila sem task. Use `queue add --create-task` ou crie uma task a partir do corpo."
    task = find_task(root, task_id)
    status = task.get("status")
    if not contract_file_path(root, task_id).exists():
        return f"Criar contrato: python {Path(__file__).resolve()} --repo {root} contract {task_id}"
    if status in TASK_STATUSES_READY_TO_START:
        return f"Iniciar: python {Path(__file__).resolve()} --repo {root} start {task_id}"
    if status in TASK_STATUSES_WORKING:
        contract = load_contract(root, task_id)
        tier = fastest_available_sensor_tier(contract)
        return f"Rodar sensores: python {Path(__file__).resolve()} --repo {root} sensors {task_id} --tier {tier} --reviewed"
    if status == TASK_STATUS_SENSORS_PASSED:
        return f"Avaliar: python {Path(__file__).resolve()} --repo {root} evaluate {task_id}"
    if status in TASK_STATUSES_COMPLETE:
        return f"Fechar fila: python {Path(__file__).resolve()} --repo {root} queue done {item.get('id')}"
    return "Revisar status manualmente."


def supervisor_tick(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    item = active_queue_item(root)
    activated = False
    if not item:
        item = next_queued_item(root)
        if item and args.activate:
            item = update_queue_item(root, item["id"], status="active", activated_at=utc_now())
            activated = True
    recommendation = supervisor_recommendation(root, item) if item else "Fila vazia."
    if item and args.auto_start and item.get("task_id"):
        task = find_task(root, item["task_id"])
        if task.get("status") in {"planned", "contracted"} and contract_file_path(root, item["task_id"]).exists():
            command_start(
                argparse.Namespace(
                    repo=args.repo,
                    allow_main=args.allow_main,
                    task_id=item["task_id"],
                    skip_preflight=args.skip_preflight,
                )
            )
            recommendation = "Run iniciada automaticamente."
    payload = {
        "updated_at": utc_now(),
        "counts": queue_counts(root),
        "active_item": item,
        "activated": activated,
        "recommendation": recommendation,
    }
    write_json(supervisor_state_path(root), payload)
    if item and item.get("task_id"):
        create_checkpoint(root, item["task_id"], "supervisor_tick", latest_run_dir_or_none(root, item["task_id"]), payload)
    return payload


def command_supervisor_status(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    state = read_json(supervisor_state_path(root), {})
    counts = queue_counts(root)
    print("Supervisor:")
    print(f"- ultimo tick: {state.get('updated_at') or 'nenhum'}")
    print(f"- fila: {counts}")
    if state.get("recommendation"):
        print(f"- recomendacao: {state['recommendation']}")


def command_supervisor_tick(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="supervisor tick")
    payload = supervisor_tick(root, args)
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else payload["recommendation"])


def command_supervisor_run(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="supervisor run")
    ticks = 0
    while True:
        payload = supervisor_tick(root, args)
        ticks += 1
        print(f"[{ticks}] {payload['recommendation']}")
        if args.max_ticks and ticks >= args.max_ticks:
            break
        if args.once or not payload.get("active_item"):
            break
        time.sleep(args.interval)


def command_github_configure(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="github configure")
    config = load_config(root)
    gconfig = github_config(config)
    if args.repo:
        gconfig["repo"] = args.repo
    if args.remote:
        gconfig["remote"] = args.remote
    if args.base:
        gconfig["default_base"] = args.base
    config["github"] = gconfig
    write_json(config_path(root), config)
    print(f"GitHub repo: {gconfig.get('repo') or 'nao configurado'}")


def command_github_status(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    gconfig = github_config(load_config(root))
    print(f"repo: {gconfig.get('repo') or 'nao configurado'}")
    print(f"remote: {gconfig.get('remote')}")
    print(f"base: {gconfig.get('default_base')}")
    print(f"gh CLI: {shutil.which('gh') or 'nao encontrado'}")


def command_github_pr_body(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    body = render_github_pr_body(root, args.task_id)
    path = Path(args.out).expanduser().resolve() if args.out else github_root(root) / f"{args.task_id}-pr-body.md"
    assert_inside_root(root, path, label="github pr-body out")
    write_text(path, body)
    print(body if args.print else f"PR body escrito: {path}")


def command_github_pr_create(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="github pr-create")
    config = load_config(root)
    gconfig = github_config(config)
    task = find_task(root, args.task_id)
    body_path = github_root(root) / f"{args.task_id}-pr-body.md"
    write_text(body_path, render_github_pr_body(root, args.task_id))
    title = args.title or f"{args.task_id}: {task.get('title')}"
    base = args.base or gconfig.get("default_base") or "main"
    argv = ["gh", "pr", "create", "--title", title, "--body-file", str(body_path), "--base", base]
    if args.head:
        argv.extend(["--head", args.head])
    if args.dry_run or not shutil.which("gh"):
        print("Dry-run gh command:")
        print(" ".join(shlex.quote(part) for part in argv))
        return
    result = subprocess.run(argv, cwd=root, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "gh pr create falhou")
    print(result.stdout.strip())


def command_github_issue_import(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="github issue-import")
    if not shutil.which("gh"):
        raise SystemExit("gh CLI nao encontrado. Instale/configure `gh` ou crie a task manualmente.")
    result = subprocess.run(
        ["gh", "issue", "view", args.issue, "--json", "title,body,url"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "gh issue view falhou")
    payload = json.loads(result.stdout)
    task = create_task(root, payload.get("title") or f"Issue {args.issue}", payload.get("body") or "", payload.get("url") or args.issue)
    print(f"Importado GitHub issue -> {task['task_id']}: {task['title']}")


def command_policy_show(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    print(json.dumps({"failure_policy": failure_policy(config), "review_policy": review_policy(config)}, indent=2, ensure_ascii=False))


def command_policy_set(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="policy set")
    config = load_config(root)
    policy = failure_policy(config)
    if args.max_fix_attempts is not None:
        policy["max_fix_attempts"] = args.max_fix_attempts
    if args.auto_fix_brief is not None:
        policy["auto_fix_brief"] = args.auto_fix_brief
    if args.p2_blocks is not None:
        policy["p2_blocks"] = args.p2_blocks
        config.setdefault("review_policy", {}).setdefault("blocking_findings", {})["p2"] = args.p2_blocks
    if args.warn_unevaluated is not None:
        config.setdefault("policy", {})["warn_on_unevaluated_runs"] = args.warn_unevaluated
    config["failure_policy"] = policy
    write_json(config_path(root), config)
    print("Policy atualizada.")


def command_failure_apply(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="failure apply")
    config = load_config(root)
    task = find_task(root, args.task_id)
    contract = load_contract(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)
    review_text = "\n\n".join(read_text(Path(file).expanduser().resolve()) for file in args.review_file or [])
    review_text += "\n\n" + "\n\n".join(args.review_note or [])
    evaluator_text = "\n\n".join(read_text(Path(file).expanduser().resolve()) for file in args.evaluator_file or [])
    evaluator_text += "\n\n" + "\n\n".join(args.evaluator_note or [])
    blockers = blocking_findings_from_review(review_text, config)
    evaluator_failed = bool(re.search(r"\bFAIL\b", evaluator_text, re.IGNORECASE))
    decision = {
        "task_id": args.task_id,
        "created_at": utc_now(),
        "blockers": blockers,
        "evaluator_failed": evaluator_failed,
        "status": "blocked" if blockers or evaluator_failed else "clear",
    }
    write_json(run_dir / "failure-decision.json", decision)
    if decision["status"] == "blocked":
        update_task(root, args.task_id, status="needs_work")
        if config_bool(failure_policy(config).get("auto_fix_brief"), True):
            brief = render_fix_brief(root, task, contract, run_dir, review_text, evaluator_text, config)
            path = next_fix_brief_path(run_dir)
            write_text(path, brief)
            write_text(run_dir / "fix-brief-latest.md", brief)
            print(f"Bloqueado. Fix brief: {path}")
        else:
            print("Bloqueado. Auto fix brief desligado.")
    else:
        print("Nenhum bloqueador detectado.")


def command_evaluate(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="evaluate")
    config = load_config(root)
    task = find_task(root, args.task_id)
    contract = load_contract(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)

    if not args.status:
        brief_path = run_dir / "evaluator-brief.md"
        handoff_path = run_dir / "evaluator-agent-handoff.md"
        reviewer_policy = review_policy(config)
        reviewer_enabled = config_bool(reviewer_policy.get("enabled"), True)
        reviewer_handoff_path = run_dir / "greptile-reviewer-agent-handoff.md"
        if reviewer_enabled:
            write_text(reviewer_handoff_path, render_greptile_reviewer_agent_handoff(root, task, run_dir, config))
        else:
            reviewer_handoff_path = None
        consolidation_path = run_dir / "review-consolidation.md"
        dispatch_path = run_dir / "parallel-dispatch.md"
        write_text(brief_path, render_evaluator_brief(root, task, contract, run_dir))
        write_text(handoff_path, render_evaluator_agent_handoff(root, task, run_dir, brief_path, config))
        write_text(consolidation_path, render_review_consolidation(task, handoff_path, reviewer_handoff_path, config))
        write_text(dispatch_path, render_parallel_dispatch(task, handoff_path, reviewer_handoff_path))
        append_and_maybe_notify_event(
            root,
            run_dir,
            "evaluation_brief_created",
            {
                "path": str(brief_path),
                "agent_handoff_path": str(handoff_path),
                "evaluation_policy": evaluation_policy(config),
                "reviewer_handoff_path": str(reviewer_handoff_path) if reviewer_handoff_path else None,
                "review_policy": reviewer_policy,
                "consolidation_path": str(consolidation_path),
                "parallel_dispatch_path": str(dispatch_path),
            },
        )
        print(f"Brief do avaliador: {brief_path}")
        print(f"Handoff do agente avaliador: {handoff_path}")
        if reviewer_handoff_path:
            print(f"Handoff do code reviewer Greptile-style: {reviewer_handoff_path}")
        print(f"Guia de consolidacao: {consolidation_path}")
        print(f"Dispatch paralelo: {dispatch_path}")
        return

    notes = args.notes or ""
    if args.notes_file:
        notes = read_text(Path(args.notes_file).expanduser().resolve())

    if args.status == "pass":
        policy = config.get("policy", {})
        if config_bool(policy.get("record_evidence_before_done"), True):
            sensors_payload = final_sensor_payload(run_dir, contract)
            if not sensors_payload:
                raise SystemExit(
                    "Avaliacao `pass` bloqueada: nao ha evidencia de sensores finais na run.\n"
                    f"Rode `harness sensors {args.task_id} --tier full --reviewed` antes, ou desabilite "
                    "`policy.record_evidence_before_done` em `.harness/config.json` para uma "
                    "excecao consciente."
                )
            if not sensors_payload.get("passed"):
                raise SystemExit(
                    "Avaliacao `pass` bloqueada: sensores registrados nao passaram.\n"
                    "Corrija a implementacao e rode os sensores novamente, ou registre "
                    "`--status fail` / `--status needs-work` com lacunas concretas."
                )

    evaluation = {
        "task_id": args.task_id,
        "run_dir": str(run_dir),
        "created_at": utc_now(),
        "status": args.status,
        "notes": notes,
        "gaps": args.gap or [],
    }
    write_json(run_dir / "evaluation.json", evaluation)
    write_text(
        harness_root(root) / "evaluations" / f"{args.task_id}.md",
        render_evaluation_markdown(evaluation),
    )
    sensors = read_json(run_dir / "sensors.json", {})
    plain_summary = render_plain_summary(task, contract, sensors, evaluation)
    plain_summary_path = run_dir / "plain-summary.md"
    write_text(plain_summary_path, plain_summary)
    create_checkpoint(root, args.task_id, f"evaluation_{args.status}", run_dir, {"evaluation": evaluation})
    append_and_maybe_notify_event(
        root,
        run_dir,
        "evaluation_recorded",
        {
            "task_id": args.task_id,
            "status": args.status,
            "plain_summary_path": str(plain_summary_path),
        },
    )
    task_status_map = {"pass": "passed", "fail": "failed", "needs-work": "needs_work"}
    update_task(root, args.task_id, status=task_status_map.get(args.status, "needs_work"))
    print(f"Avaliacao registrada para {args.task_id}: {args.status}")
    print(f"Explicacao simples: {plain_summary_path}")


def command_report(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="report")
    task = find_task(root, args.task_id)
    contract = read_json(contract_file_path(root, args.task_id), {})
    run_dir = latest_run_dir(root, args.task_id)
    sensors = read_json(run_dir / "sensors.json", {})
    evaluation = read_json(run_dir / "evaluation.json", {})
    plain_summary = render_plain_summary(task, contract, sensors, evaluation)
    plain_summary_path = run_dir / "plain-summary.md"
    write_text(plain_summary_path, plain_summary)
    report = render_report(root, task, contract, run_dir, sensors, evaluation, plain_summary)
    report_path = harness_root(root) / "reports" / f"{args.task_id}.md"
    write_text(report_path, report)
    create_checkpoint(root, args.task_id, "report_created", run_dir, {"report_path": str(report_path)})
    append_and_maybe_notify_event(
        root,
        run_dir,
        "report_created",
        {
            "task_id": args.task_id,
            "path": str(report_path),
            "plain_summary_path": str(plain_summary_path),
            "plain_summary": render_plain_summary_for_message(plain_summary),
        },
    )
    print(report)
    print(f"\nRelatorio escrito: {report_path}")
    print(f"Explicacao simples escrita: {plain_summary_path}")


def command_preflight(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    if args.task_id:
        find_task(root, args.task_id)
    result = check_context_preflight(root, args.task_id)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_preflight_text(result))
    if not result["passed"]:
        raise SystemExit(1)


def command_telegram_configure(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="telegram configure")
    config = load_config(root)
    tconfig = telegram_config(config)
    if args.enable:
        tconfig["enabled"] = True
    if args.disable:
        tconfig["enabled"] = False
    if args.token_env:
        tconfig["token_env"] = args.token_env
    if args.chat_id:
        tconfig["chat_ids"] = [str(item) for item in args.chat_id]
    if args.allowed_chat_id:
        tconfig["allowed_chat_ids"] = [str(item) for item in args.allowed_chat_id]
    if args.event:
        tconfig["notify_events"] = [str(item) for item in args.event]
    if args.allow_task_creation:
        tconfig["allow_task_creation"] = True
    if args.block_task_creation:
        tconfig["allow_task_creation"] = False
    if args.allow_remote_execution:
        tconfig["allow_remote_execution"] = True
    if args.block_remote_execution:
        tconfig["allow_remote_execution"] = False
    if args.download_media:
        tconfig["download_media"] = True
    if args.no_download_media:
        tconfig["download_media"] = False
    if args.openai_media:
        tconfig["openai_media"]["enabled"] = True
    if args.no_openai_media:
        tconfig["openai_media"]["enabled"] = False
    config["telegram"] = tconfig
    write_json(config_path(root), config)
    print("Telegram configurado.")
    print(f"- habilitado: {str(config_bool(tconfig.get('enabled'), False)).lower()}")
    print(f"- chats de notificacao: {', '.join(tconfig.get('chat_ids', [])) or 'nenhum'}")
    print(f"- chats autorizados: {', '.join(tconfig.get('allowed_chat_ids', [])) or 'mesmos chats de notificacao'}")
    print(f"- token env: {tconfig.get('token_env')}")
    print(f"- execucao remota: {str(config_bool(tconfig.get('allow_remote_execution'), False)).lower()}")
    print(f"- midia via OpenAI: {str(config_bool(tconfig.get('openai_media', {}).get('enabled'), False)).lower()}")


def command_telegram_send(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    text = args.text or ""
    if args.text_file:
        text = read_text(Path(args.text_file).expanduser().resolve())
    if not text:
        raise SystemExit("Informe texto ou --text-file.")
    targets = [str(item) for item in args.chat_id] if args.chat_id else None
    sent = telegram_send_message(config, text, targets)
    print(f"Mensagens enviadas: {len(sent)}")


def command_telegram_status(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    tconfig = telegram_config(config)
    print("Telegram:")
    print(f"- habilitado: {str(config_bool(tconfig.get('enabled'), False)).lower()}")
    print(f"- token env: {tconfig.get('token_env')}")
    print(f"- token presente: {str(bool(telegram_token(config))).lower()}")
    print(f"- chats de notificacao: {', '.join(str(item) for item in tconfig.get('chat_ids', [])) or 'nenhum'}")
    print(f"- chats autorizados: {', '.join(str(item) for item in tconfig.get('allowed_chat_ids', [])) or 'mesmos chats de notificacao'}")
    print(f"- eventos: {', '.join(str(item) for item in tconfig.get('notify_events', []))}")
    print(f"- criacao de task: {str(config_bool(tconfig.get('allow_task_creation'), True)).lower()}")
    print(f"- execucao remota: {str(config_bool(tconfig.get('allow_remote_execution'), False)).lower()}")
    print(f"- download de midia: {str(config_bool(tconfig.get('download_media'), True)).lower()}")
    print(f"- midia via OpenAI: {str(config_bool(tconfig.get('openai_media', {}).get('enabled'), False)).lower()}")


def command_telegram_listen(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="telegram listen")
    config = load_config(root)
    token = require_telegram_bot_token(config)
    state = read_json(telegram_state_path(root), {})
    offset = state.get("offset")
    print("Ouvindo Telegram. Ctrl+C para parar.")
    while True:
        updates = telegram_poll_updates(token, timeout=args.timeout, limit=args.limit, offset=offset)
        processed = 0
        for update in updates:
            update_id = telegram_update_context(update)["update_id"]
            path = handle_telegram_update(
                root,
                config,
                update,
                create_tasks=bool(args.create_tasks),
                download_media=not args.no_download_media,
                reply=not args.no_reply,
            )
            if path:
                processed += 1
                print(f"Telegram update salvo: {path}")
            offset = advance_telegram_offset(offset, update_id)
            write_telegram_offset_state(telegram_state_path(root), offset)
        if args.once:
            if not processed:
                print("Nenhuma mensagem nova.")
            return


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


def command_telegram_codex(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="telegram codex")
    config = load_config(root)
    token = require_telegram_bot_token(config)
    if not telegram_remote_execution_allowed(config):
        raise SystemExit(
            "Execucao remota via Telegram esta desligada ou sem allowlist.\n"
            "Configure `telegram.allow_remote_execution=true` e ao menos um `allowed_chat_id` "
            "antes de usar `telegram codex`."
        )
    codex_executable()
    state_path = telegram_root(root) / "codex-state.json"
    state = read_json(state_path, {})
    offset = state.get("offset")
    print("Gateway Telegram -> Codex ativo. Ctrl+C para parar.")
    while True:
        updates = telegram_poll_updates(
            token,
            timeout=args.poll_timeout,
            limit=args.limit,
            offset=offset,
        )
        processed = 0
        for update in updates:
            prepared = prepare_telegram_exec_update(
                root,
                config,
                update,
                download_media=not args.no_download_media,
                reply_to_harness_commands=not args.no_reply,
                command_prefixes=("/codex",),
            )
            update_id = prepared["update_id"]
            if prepared["harness_command"]:
                processed += 1
                print(f"Comando Harness via Telegram: {prepared['path']}")
            if not prepared["ready"]:
                offset = advance_telegram_offset(offset, update_id)
                write_telegram_offset_state(state_path, offset)
                continue
            path = prepared["path"]
            item = prepared["item"]
            result = execute_telegram_codex_item(
                root,
                config,
                path,
                item,
                prepared["chat_id"],
                prepared["prompt_text"],
                resume_last=bool(args.resume_last),
                session_id=args.session_id,
                model=args.model,
                sandbox=args.sandbox,
                approval=args.approval,
                bypass=bool(args.bypass),
                timeout=args.codex_timeout,
                reply=not args.no_reply,
                start_message="Recebido. Vou mandar isso para o Codex agora.",
                completed_action="codex_completed",
                failed_action="codex_failed",
                timeout_action="codex_timeout",
                include_stderr_path_on_error=True,
            )
            if result:
                print(f"Codex respondeu para {path}: {result['run_id']}")
            processed += 1
            offset = advance_telegram_offset(offset, update_id)
            write_telegram_offset_state(state_path, offset)
        if args.once:
            if not processed:
                print("Nenhuma mensagem nova.")
            return


def command_telegram_mirror(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    require_telegram_bot_token(config)
    session_path = Path(args.session_file).expanduser().resolve() if args.session_file else latest_codex_session_file()
    if args.chat_id:
        targets = [str(item) for item in args.chat_id]
    else:
        targets = [str(item) for item in telegram_config(config).get("chat_ids", [])]
    if not targets:
        raise SystemExit("Nenhum chat configurado. Use telegram configure --chat-id ou telegram mirror --chat-id.")

    offset = read_mirror_state(root, session_path, from_end=not args.from_start)
    print(f"Espelhando sessao Codex: {session_path}")
    print(f"Destino Telegram: {', '.join(targets)}")
    while True:
        events, offset = read_new_codex_session_events(session_path, offset)
        sent = 0
        for event in events:
            message = mirror_message_from_codex_event(event, include_tools=bool(args.include_tools))
            if not message:
                continue
            telegram_send_message(config, message, targets)
            sent += 1
        write_mirror_state(root, session_path, offset)
        if sent:
            print(f"Enviados {sent} updates.")
        if args.once:
            if not sent:
                print("Nenhum update novo.")
            return
        time.sleep(args.interval)


def command_telegram_bridge(args: argparse.Namespace) -> None:
    root = prepared_repo(args, safe_operation="telegram bridge")
    config = load_config(root)
    token = require_telegram_bot_token(config)
    if args.send_mode == "codex-exec":
        if not telegram_remote_execution_allowed(config):
            raise SystemExit(
                "Modo codex-exec bloqueado: configure `telegram.allow_remote_execution=true` "
                "e ao menos um `allowed_chat_id`."
            )
        codex_executable()

    session_path = Path(args.session_file).expanduser().resolve() if args.session_file else latest_codex_session_file()
    mirror_offset = read_mirror_state(root, session_path, from_end=not args.from_start)
    bridge_state_path = telegram_root(root) / "bridge-state.json"
    bridge_state = read_json(bridge_state_path, {})
    update_offset = bridge_state.get("telegram_offset")
    event_offset = bridge_state.get("event_offset")
    if event_offset is None and not args.from_start and event_stream_path(root).exists():
        event_offset = event_stream_path(root).stat().st_size
    targets = [str(item) for item in args.chat_id] if args.chat_id else [str(item) for item in telegram_config(config).get("chat_ids", [])]
    if not targets:
        raise SystemExit("Nenhum chat configurado. Use telegram configure --chat-id ou telegram bridge --chat-id.")

    print(f"Bridge ativo. Espelhando: {session_path}")
    print(f"Destino Telegram: {', '.join(targets)}")
    print(f"Modo de envio: {args.send_mode}")
    while True:
        if not args.no_harness_events:
            harness_events, event_offset = read_new_harness_events(root, event_offset)
            forwarded = 0
            for event in harness_events:
                if event.get("source") == "telegram":
                    continue
                telegram_send_message(config, telegram_message_from_harness_event(event), targets)
                forwarded += 1
            if forwarded:
                print(f"Bridge enviou {forwarded} eventos Harness.")
            write_telegram_bridge_state(bridge_state_path, update_offset, event_offset)

        if not args.session_file and args.follow_latest:
            latest = latest_codex_session_file()
            if latest != session_path:
                session_path = latest
                mirror_offset = read_mirror_state(root, session_path, from_end=True)
                if not args.no_reply:
                    telegram_send_message(config, f"Espelhando nova sessao Codex:\n{session_path}", targets)

        events, mirror_offset = read_new_codex_session_events(session_path, mirror_offset)
        mirrored = 0
        for event in events:
            message = mirror_message_from_codex_event(event, include_tools=bool(args.include_tools))
            if not message:
                continue
            telegram_send_message(config, message, targets)
            mirrored += 1
        write_mirror_state(root, session_path, mirror_offset)
        if mirrored:
            print(f"Mirror enviou {mirrored} updates.")

        updates = telegram_poll_updates(
            token,
            timeout=args.poll_timeout,
            limit=args.limit,
            offset=update_offset,
        )
        processed = 0
        for update in updates:
            prepared = prepare_telegram_exec_update(
                root,
                config,
                update,
                download_media=not args.no_download_media,
                reply_to_harness_commands=not args.no_reply,
                command_prefixes=("/codex", "/queue", "/note", "/msg"),
            )
            update_id = prepared["update_id"]
            if prepared["harness_command"]:
                print(f"Comando Harness via Telegram: {prepared['path']}")
                processed += 1
            if not prepared["ready"]:
                update_offset = advance_telegram_offset(update_offset, update_id)
                write_telegram_bridge_state(bridge_state_path, update_offset, event_offset)
                continue

            path = prepared["path"]
            item = prepared["item"]
            prompt_text = prepared["prompt_text"]
            chat_id = prepared["chat_id"]
            stripped = prepared["stripped"]
            force_codex = stripped.lower().startswith("/codex")
            if args.send_mode == "codex-exec" or force_codex:
                if not telegram_remote_execution_allowed(config):
                    item["action"] = "bridge_remote_execution_blocked"
                    item["error"] = "allow_remote_execution disabled or allowlist empty"
                    write_json(path, item)
                    if not args.no_reply:
                        telegram_reply(
                            config,
                            chat_id,
                            "Execucao remota via Telegram esta desligada. Ative allow_remote_execution e allowed_chat_id.",
                        )
                    processed += 1
                    update_offset = advance_telegram_offset(update_offset, update_id)
                    write_telegram_bridge_state(bridge_state_path, update_offset, event_offset)
                    continue
                execute_telegram_codex_item(
                    root,
                    config,
                    path,
                    item,
                    chat_id,
                    prompt_text,
                    resume_last=bool(args.resume_last or not args.session_id),
                    session_id=args.session_id,
                    model=args.model,
                    sandbox=args.sandbox,
                    approval=args.approval,
                    bypass=bool(args.bypass),
                    timeout=args.codex_timeout,
                    reply=not args.no_reply,
                    start_message="Recebido. Vou chamar o Codex em paralelo.",
                    completed_action="bridge_codex_completed",
                    failed_action="bridge_codex_failed",
                )
            else:
                queue_path = queue_operator_message(root, item, prompt_text)
                item["action"] = "bridge_queued"
                item["queued_path"] = str(queue_path)
                write_json(path, item)
                if not args.no_reply:
                    telegram_reply(
                        config,
                        chat_id,
                        f"Mensagem guardada para a sessao ativa:\n{queue_path}\n\n"
                        "Use /codex <mensagem> se quiser chamar Codex em paralelo agora.",
                    )
            processed += 1
            update_offset = advance_telegram_offset(update_offset, update_id)
            write_telegram_bridge_state(bridge_state_path, update_offset, event_offset)

        if processed:
            print(f"Bridge processou {processed} mensagens Telegram.")
        if args.once:
            if not mirrored and not processed:
                print("Nenhum update novo.")
            return
        time.sleep(args.interval)


def command_status(args: argparse.Namespace) -> None:
    root = prepared_repo(args)
    config = load_config(root)
    print(f"Projeto: {config.get('project_name')}")
    print(f"Raiz: {root}")
    branch = current_git_branch(root)
    if branch:
        print(f"Branch atual: {branch}")
        print(f"Branches protegidas: {', '.join(protected_branches(root))}")
    print("Sensores:")
    for sensor in config.get("default_sensors", []):
        print(f"- {sensor}")
    if not config.get("default_sensors"):
        print("- nenhum")

    evaluator = evaluation_policy(config)
    print("\nAvaliador:")
    print(f"- modo: {evaluator.get('mode')}")
    print(f"- fork_context: {str(config_bool(evaluator.get('fork_context'), False)).lower()}")
    print(f"- escopo de entrada: {evaluator.get('input_scope')}")

    reviewer = review_policy(config)
    print("\nCode reviewer:")
    print(f"- habilitado: {str(config_bool(reviewer.get('enabled'), True)).lower()}")
    print(f"- skill: {reviewer.get('skill')}")
    print(f"- modo: {reviewer.get('mode')}")
    print(f"- fork_context: {str(config_bool(reviewer.get('fork_context'), False)).lower()}")
    print(f"- escopo de entrada: {reviewer.get('input_scope')}")

    tconfig = telegram_config(config)
    print("\nTelegram:")
    print(f"- habilitado: {str(config_bool(tconfig.get('enabled'), False)).lower()}")
    print(f"- chats de notificacao: {', '.join(str(item) for item in tconfig.get('chat_ids', [])) or 'nenhum'}")
    print(f"- criacao de task: {str(config_bool(tconfig.get('allow_task_creation'), True)).lower()}")
    print(f"- execucao remota: {str(config_bool(tconfig.get('allow_remote_execution'), False)).lower()}")

    print("\nOperacao:")
    print(f"- profile ativo: {config.get('active_profile', 'balanced')}")
    counts = queue_counts(root)
    print(f"- fila: {counts if counts else 'vazia'}")
    security = read_json(security_root(root) / "scan-latest.json", {})
    if security:
        print(f"- security findings: {len(security.get('findings') or [])}")

    print("\nContexto obrigatorio:")
    requirements = context_requirements_for_task(root, config)
    if not requirements:
        print("- nenhum")
    for requirement in requirements:
        suffix = f" ({requirement.get('kind')})" if requirement.get("kind") else ""
        print(f"- {requirement['display_path']}{suffix}")
    print("\nTasks:")
    tasks = load_tasks(root)
    if not tasks:
        print("- nenhuma")
    for task in tasks:
        print(f"- {task['task_id']} [{task['status']}] {task['title']}")
    maybe_warn_unevaluated_runs(root, config)


def run_compat_command(repo: Path, args: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), "--repo", str(repo), *args]
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=repo.parent if repo.parent.exists() else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return {
        "command": " ".join(args),
        "exit_code": result.returncode,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "stdout": result.stdout[-1200:],
        "stderr": result.stderr[-1200:],
    }


def command_compat_manifest(args: argparse.Namespace) -> None:
    manifest = compatibility_manifest()
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return
    print(f"Compatibilidade: {manifest['compat_version']}")
    print("Entrypoints publicos:")
    for entrypoint in manifest["entrypoints"]:
        print(f"- {entrypoint}")
    print("Comandos protegidos:")
    for command in manifest["required_commands"]:
        print(f"- {command}")


def command_compat_skill_smoke(args: argparse.Namespace) -> None:
    base = Path(args.workdir).expanduser().resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="harness-compat-"))
    repo = base / "skill-compat-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text("# Agents\n\nContexto de compatibilidade.\n", encoding="utf-8")
    (repo / "issue.md").write_text(
        "# Compat task\n\n## Criterios de aceite\n\n- [ ] fluxo da skill funciona\n",
        encoding="utf-8",
    )

    commands = [
        ["init", "--name", "skill-compat", "--force"],
        ["ingest", str(repo / "AGENTS.md"), "--kind", "context"],
        ["preflight"],
        ["task", "import", str(repo / "issue.md")],
        ["queue", "add", "TASK-001"],
        ["queue", "next"],
        ["contract", "TASK-001", "--criteria", "fluxo da skill funciona", "--sensor", "python -c pass", "--reviewed-sensors"],
        ["start", "TASK-001"],
        ["sensors", "TASK-001", "--reviewed"],
        ["evaluate", "TASK-001"],
        ["evaluate", "TASK-001", "--status", "pass", "--notes", "compat smoke ok"],
        ["report", "TASK-001"],
        ["checkpoint", "create", "TASK-001", "--summary", "compat smoke checkpoint"],
        ["checkpoint", "resume-plan", "TASK-001"],
        ["dashboard", "hub"],
        ["events", "list", "--json"],
        ["agent", "list", "--json"],
        ["telegram", "configure", "--chat-id", "123", "--allowed-chat-id", "123"],
        ["telegram", "status"],
        ["status"],
    ]
    results = []
    failed = False
    for command in commands:
        result = run_compat_command(repo, command)
        results.append(result)
        if result["exit_code"] != 0:
            failed = True
            break

    payload = {
        "ok": not failed,
        "compat": compatibility_manifest(),
        "repo": str(repo),
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Skill smoke: {'ok' if payload['ok'] else 'falhou'}")
        print(f"Repo temporario: {repo}")
        for result in results:
            status = "ok" if result["exit_code"] == 0 else f"erro {result['exit_code']}"
            print(f"- {result['command']}: {status}")
            if result["exit_code"] != 0:
                if result["stderr"]:
                    print(result["stderr"])
                if result["stdout"]:
                    print(result["stdout"])
    if failed:
        raise SystemExit(1)


def add_telegram_codex_exec_args(
    parser: argparse.ArgumentParser,
    *,
    timeout_first: bool = False,
    bridge: bool = False,
) -> None:
    def add_timeout() -> None:
        parser.add_argument("--codex-timeout", type=int, default=1800, help="Timeout por chamada Codex em segundos")

    if timeout_first:
        add_timeout()
    resume_help = "Usa `codex exec resume --last` para envios ao Codex" if bridge else "Usa `codex exec resume --last`"
    session_help = (
        "Usa `codex exec resume <session-id>` para envios ao Codex"
        if bridge
        else "Usa `codex exec resume <session-id>`"
    )
    model_help = "Modelo Codex para envios ao Codex" if bridge else "Modelo Codex"
    parser.add_argument("--resume-last", action="store_true", help=resume_help)
    parser.add_argument("--session-id", help=session_help)
    parser.add_argument("--model", help=model_help)
    parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="Sandbox para sessoes novas",
    )
    parser.add_argument(
        "--approval",
        choices=["untrusted", "on-failure", "on-request", "never"],
        help="Politica de aprovacao para sessoes novas",
    )
    parser.add_argument("--bypass", action="store_true", help="Passa --dangerously-bypass-approvals-and-sandbox ao Codex")
    if not timeout_first:
        add_timeout()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="Harness Runner MVP")
    parser.add_argument("--repo", default=".", help="Diretorio alvo do repo/app")
    parser.add_argument(
        "--allow-main",
        action="store_true",
        help="Permite operar em branches protegidas como main/master/production",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Inicializa .harness em um repo existente")
    init.add_argument("--name", help="Nome do projeto")
    init.add_argument("--sensor", action="append", help="Comando de sensor padrao; repetivel")
    init.add_argument("--force", action="store_true", help="Sobrescreve config.json")
    init.add_argument("--create", action="store_true", help="Cria explicitamente o diretorio do repo se ele nao existir")
    init.set_defaults(func=command_init)

    ingest = sub.add_parser("ingest", help="Copia docs de contexto/PRD/issue para .harness/context")
    ingest.add_argument("file")
    ingest.add_argument(
        "--kind",
        default="context",
        choices=CONTEXT_KINDS,
    )
    ingest.set_defaults(func=command_ingest)

    task = sub.add_parser("task", help="Gerencia tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_create = task_sub.add_parser("create", help="Cria uma task")
    task_create.add_argument("title")
    task_create.add_argument("--body", help="Corpo da task")
    task_create.add_argument("--from-file", help="Usa um arquivo como corpo da task")
    task_create.set_defaults(func=command_task_create)

    task_import = task_sub.add_parser("import", help="Importa arquivos de issue como tasks")
    task_import.add_argument("files", nargs="+")
    task_import.set_defaults(func=command_task_import)

    task_list = task_sub.add_parser("list", help="Lista tasks")
    task_list.set_defaults(func=command_task_list)

    pick = sub.add_parser("pick", help="Mostra a proxima task pendente")
    pick.set_defaults(func=command_pick)

    queue = sub.add_parser("queue", help="Gerencia fila de trabalho")
    queue_sub = queue.add_subparsers(dest="queue_command", required=True)
    queue_add = queue_sub.add_parser("add", help="Adiciona item ou task na fila")
    queue_add.add_argument("title", help="Titulo do item ou TASK-001 existente")
    queue_add.add_argument("--body", help="Corpo/prompt do item")
    queue_add.add_argument("--priority", type=int, default=100, help="Prioridade menor roda antes")
    queue_add.add_argument("--profile", help="Profile sugerido para o item")
    queue_add.add_argument("--create-task", action="store_true", help="Cria tambem uma task Harness")
    queue_add.add_argument("--force", action="store_true", help="Permite duplicar task na fila")
    queue_add.set_defaults(func=command_queue_add)

    queue_list = queue_sub.add_parser("list", help="Lista a fila")
    queue_list.add_argument("--json", action="store_true", help="Imprime JSON")
    queue_list.set_defaults(func=command_queue_list)

    queue_next = queue_sub.add_parser("next", help="Mostra o proximo item")
    queue_next.add_argument("--activate", action="store_true", help="Marca o item como ativo")
    queue_next.add_argument("--include-active", action="store_true", help="Prefere item ativo se existir")
    queue_next.set_defaults(func=command_queue_next)

    queue_done = queue_sub.add_parser("done", help="Marca item como concluido")
    queue_done.add_argument("queue_id")
    queue_done.add_argument("--status", choices=["done", "skipped", "blocked"], default="done")
    queue_done.add_argument("--note", help="Nota de fechamento")
    queue_done.set_defaults(func=command_queue_done)

    profile = sub.add_parser("profile", help="Gerencia profiles de operacao/agentes")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_add = profile_sub.add_parser("add", help="Adiciona profile customizado")
    profile_add.add_argument("name")
    profile_add.add_argument("--model")
    profile_add.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"])
    profile_add.add_argument("--approval", choices=["untrusted", "on-failure", "on-request", "never"])
    profile_add.add_argument("--description")
    profile_add.set_defaults(func=command_profile_add)
    profile_list = profile_sub.add_parser("list", help="Lista profiles")
    profile_list.set_defaults(func=command_profile_list)
    profile_set = profile_sub.add_parser("set", help="Define profile operacional ativo")
    profile_set.add_argument("name", choices=list(DEFAULT_OPERATION_PROFILES.keys()))
    profile_set.set_defaults(func=command_profile_set)

    budget = sub.add_parser("budget", help="Gerencia budgets")
    budget_sub = budget.add_subparsers(dest="budget_command", required=True)
    budget_set = budget_sub.add_parser("set", help="Salva budget por profile/agente")
    budget_set.add_argument("name")
    budget_set.add_argument("--max-tokens", type=int)
    budget_set.add_argument("--timeout-minutes", type=int)
    budget_set.add_argument("--max-fix-attempts", type=int)
    budget_set.set_defaults(func=command_budget_set)
    budget_task = budget_sub.add_parser("task-set", help="Salva budget em uma task")
    budget_task.add_argument("task_id")
    budget_task.add_argument("--profile")
    budget_task.add_argument("--minutes", type=int)
    budget_task.add_argument("--max-fix-attempts", type=int)
    budget_task.add_argument("--sensor-tier", choices=["quick", "smoke", "affected", "full", "all"])
    budget_task.set_defaults(func=command_budget_task_set)
    budget_list = budget_sub.add_parser("list", help="Lista budgets customizados")
    budget_list.set_defaults(func=command_budget_list)

    memory = sub.add_parser("memory", help="Memoria operacional do projeto")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_remember = memory_sub.add_parser("remember", help="Registra memoria")
    memory_remember.add_argument("text")
    memory_remember.add_argument("--tag", action="append")
    memory_remember.add_argument("--task-id")
    memory_remember.set_defaults(func=command_memory_remember)
    memory_list = memory_sub.add_parser("list", help="Lista memoria")
    memory_list.add_argument("--tag")
    memory_list.add_argument("--search")
    memory_list.add_argument("--limit", type=int, default=50)
    memory_list.set_defaults(func=command_memory_list)

    contract = sub.add_parser("contract", help="Cria/atualiza contrato de uma task")
    contract.add_argument("task_id")
    contract.add_argument("--goal", help="Objetivo")
    contract.add_argument("--criteria", action="append", help="Criterio de aceite; repetivel")
    contract.add_argument("--sensor", action="append", help="Comando de sensor obrigatorio; repetivel")
    contract.add_argument("--smoke-sensor", action="append", help="Sensor rapido para loop curto; repetivel")
    contract.add_argument("--affected-sensor", action="append", help="Sensor de area afetada; repetivel")
    contract.add_argument("--full-sensor", action="append", help="Sensor completo/final; repetivel")
    contract.add_argument("--reviewed-sensors", action="store_true", help="Marca sensores do contrato como revisados")
    contract.add_argument("--out", action="append", help="Item fora de escopo; repetivel")
    contract.add_argument("--expected", action="append", help="Padrao de arquivo/caminho esperado; repetivel")
    contract.add_argument("--required-doc", action="append", help="Documento obrigatorio para esta task; repetivel")
    contract.add_argument("--notes", help="Notas extras do contrato")
    contract.set_defaults(func=command_contract)

    start = sub.add_parser("start", help="Inicia uma run e cria brief do implementador")
    start.add_argument("task_id")
    start.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Pula o preflight de contexto para excecoes conscientes",
    )
    start.set_defaults(func=command_start)

    checkpoint = sub.add_parser("checkpoint", help="Cria e usa checkpoints de retomada")
    checkpoint_sub = checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    checkpoint_create = checkpoint_sub.add_parser("create", help="Cria checkpoint manual")
    checkpoint_create.add_argument("task_id")
    checkpoint_create.add_argument("--summary", help="Resumo simples do ponto atual")
    checkpoint_create.add_argument("--next", action="append", help="Proximo passo salvo; repetivel")
    checkpoint_create.set_defaults(func=command_checkpoint_create)
    checkpoint_resume = checkpoint_sub.add_parser("resume-plan", help="Gera plano de retomada")
    checkpoint_resume.add_argument("task_id")
    checkpoint_resume.set_defaults(func=command_checkpoint_resume_plan)

    resume = sub.add_parser("resume", help="Alias para checkpoint resume-plan")
    resume.add_argument("task_id")
    resume.set_defaults(func=command_checkpoint_resume_plan)

    sensors = sub.add_parser("sensors", help="Roda sensores deterministicos da ultima run")
    sensors.add_argument("task_id")
    sensors.add_argument("--command", action="append", help="Sobrescreve/adiciona comando de sensor; repetivel")
    sensors.add_argument(
        "--tier",
        choices=["quick", "smoke", "affected", "full", "all"],
        default="full",
        help="Camada de sensores a executar",
    )
    sensors.add_argument("--reviewed", action="store_true", help="Confirma que os comandos de sensores foram revisados")
    sensors.add_argument("--allow-shell", action="store_true", help="Executa sensores via shell; por padrao usa argv sem shell")
    sensors.add_argument("--timeout", type=int, default=600, help="Timeout por comando em segundos")
    sensors.add_argument(
        "--max-output-chars",
        type=int,
        default=12000,
        help="Maximo de caracteres de stdout/stderr armazenados por comando",
    )
    sensors.set_defaults(func=command_sensors)

    security = sub.add_parser("security", help="Scanner local de segredos")
    security_sub = security.add_subparsers(dest="security_command", required=True)
    security_scan = security_sub.add_parser("scan", help="Procura secrets em arquivos versionados")
    security_scan.add_argument("--include-untracked", action="store_true", help="Inclui arquivos nao rastreados")
    security_scan.add_argument("--fail-on-findings", action="store_true", help="Falha quando houver achados")
    security_scan.add_argument("--json", action="store_true", help="Imprime JSON")
    security_scan.set_defaults(func=command_security_scan)
    security_status = security_sub.add_parser("status", help="Mostra ultimo scan")
    security_status.set_defaults(func=command_security_status)

    evaluate = sub.add_parser("evaluate", help="Cria brief/handoff do avaliador ou registra avaliacao")
    evaluate.add_argument("task_id")
    evaluate.add_argument("--status", choices=["pass", "fail", "needs-work"])
    evaluate.add_argument("--notes", help="Notas da avaliacao")
    evaluate.add_argument("--notes-file", help="Le notas de avaliacao de um arquivo")
    evaluate.add_argument("--gap", action="append", help="Lacuna/item de correcao; repetivel")
    evaluate.set_defaults(func=command_evaluate)

    fix_brief = sub.add_parser("fix-brief", help="Cria brief rapido para corrigir P0/P1 na mesma task")
    fix_brief.add_argument("task_id")
    fix_brief.add_argument("--review-file", action="append", help="Arquivo com saida do Greptile/reviewer; repetivel")
    fix_brief.add_argument("--review-note", action="append", help="Nota do reviewer em texto; repetivel")
    fix_brief.add_argument("--evaluator-file", action="append", help="Arquivo com saida do avaliador; repetivel")
    fix_brief.add_argument("--evaluator-note", action="append", help="Nota do avaliador em texto; repetivel")
    fix_brief.set_defaults(func=command_fix_brief)

    for speed_name, speed_help in [
        ("quick-pass", "Roda sensores rapidos e gera handoffs paralelos"),
        ("full-pass", "Roda sensores finais e gera handoffs paralelos"),
    ]:
        speed = sub.add_parser(speed_name, help=speed_help)
        speed.add_argument("task_id")
        speed.add_argument("--command", dest="command_override", action="append", help="Sobrescreve comandos de sensor; repetivel")
        speed.add_argument("--reviewed", action="store_true", help="Confirma que os comandos de sensores foram revisados")
        speed.add_argument("--allow-shell", action="store_true", help="Executa sensores via shell")
        speed.add_argument("--timeout", type=int, default=600, help="Timeout por comando em segundos")
        speed.add_argument("--max-output-chars", type=int, default=12000, help="Maximo de caracteres armazenados")
        speed.set_defaults(func=command_speed_pass)

    artifacts = sub.add_parser("artifacts", help="Lista/registra artifacts da run")
    artifacts_sub = artifacts.add_subparsers(dest="artifacts_command", required=True)
    artifacts_add = artifacts_sub.add_parser("add", help="Registra artifact manual")
    artifacts_add.add_argument("task_id")
    artifacts_add.add_argument("path")
    artifacts_add.add_argument("--label")
    artifacts_add.add_argument("--kind")
    artifacts_add.add_argument("--copy", action="store_true", help="Copia arquivo para .harness/artifacts")
    artifacts_add.set_defaults(func=command_artifacts_add)
    artifacts_list = artifacts_sub.add_parser("list", help="Lista artifacts")
    artifacts_list.add_argument("task_id", nargs="?")
    artifacts_list.add_argument("--json", action="store_true")
    artifacts_list.set_defaults(func=command_artifacts_list)

    supervisor = sub.add_parser("supervisor", help="Loop supervisor da fila")
    supervisor_sub = supervisor.add_subparsers(dest="supervisor_command", required=True)
    supervisor_status = supervisor_sub.add_parser("status", help="Mostra estado do supervisor")
    supervisor_status.set_defaults(func=command_supervisor_status)
    supervisor_tick_p = supervisor_sub.add_parser("tick", help="Executa um tick do supervisor")
    supervisor_tick_p.add_argument("--activate", action="store_true", help="Ativa proximo item da fila")
    supervisor_tick_p.add_argument("--auto-start", action="store_true", help="Inicia run automaticamente quando seguro")
    supervisor_tick_p.add_argument("--skip-preflight", action="store_true")
    supervisor_tick_p.add_argument("--json", action="store_true")
    supervisor_tick_p.set_defaults(func=command_supervisor_tick)
    supervisor_run = supervisor_sub.add_parser("run", help="Roda supervisor em loop")
    supervisor_run.add_argument("--activate", action="store_true")
    supervisor_run.add_argument("--auto-start", action="store_true")
    supervisor_run.add_argument("--skip-preflight", action="store_true")
    supervisor_run.add_argument("--interval", type=float, default=10.0)
    supervisor_run.add_argument("--max-ticks", type=int, default=0)
    supervisor_run.add_argument("--once", action="store_true")
    supervisor_run.set_defaults(func=command_supervisor_run)

    policy = sub.add_parser("policy", help="Politicas de falha/revisao")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_show = policy_sub.add_parser("show", help="Mostra politicas")
    policy_show.set_defaults(func=command_policy_show)
    policy_set = policy_sub.add_parser("set", help="Atualiza politica")
    policy_set.add_argument("--max-fix-attempts", type=int)
    policy_set.add_argument("--auto-fix-brief", dest="auto_fix_brief", action="store_true", default=None)
    policy_set.add_argument("--no-auto-fix-brief", dest="auto_fix_brief", action="store_false")
    policy_set.add_argument("--p2-blocks", dest="p2_blocks", action="store_true", default=None)
    policy_set.add_argument("--p2-does-not-block", dest="p2_blocks", action="store_false")
    policy_set.add_argument("--warn-unevaluated", dest="warn_unevaluated", action="store_true", default=None)
    policy_set.add_argument("--no-warn-unevaluated", dest="warn_unevaluated", action="store_false")
    policy_set.set_defaults(func=command_policy_set)

    failure = sub.add_parser("failure", help="Aplica politica de P0/P1/falhas")
    failure_sub = failure.add_subparsers(dest="failure_command", required=True)
    failure_apply = failure_sub.add_parser("apply", help="Analisa saidas de avaliador/reviewer")
    failure_apply.add_argument("task_id")
    failure_apply.add_argument("--review-file", action="append")
    failure_apply.add_argument("--review-note", action="append")
    failure_apply.add_argument("--evaluator-file", action="append")
    failure_apply.add_argument("--evaluator-note", action="append")
    failure_apply.set_defaults(func=command_failure_apply)

    github = sub.add_parser("github", help="Helpers GitHub Issues/PR")
    github_sub = github.add_subparsers(dest="github_command", required=True)
    github_configure = github_sub.add_parser("configure", help="Configura repo GitHub")
    github_configure.add_argument("--repo", help="owner/repo")
    github_configure.add_argument("--remote")
    github_configure.add_argument("--base")
    github_configure.set_defaults(func=command_github_configure)
    github_status = github_sub.add_parser("status", help="Mostra config GitHub")
    github_status.set_defaults(func=command_github_status)
    github_body = github_sub.add_parser("pr-body", help="Gera body de PR a partir de task")
    github_body.add_argument("task_id")
    github_body.add_argument("--out")
    github_body.add_argument("--print", action="store_true")
    github_body.set_defaults(func=command_github_pr_body)
    github_pr = github_sub.add_parser("pr-create", help="Cria PR via gh CLI ou mostra dry-run")
    github_pr.add_argument("task_id")
    github_pr.add_argument("--base")
    github_pr.add_argument("--head")
    github_pr.add_argument("--title")
    github_pr.add_argument("--dry-run", action="store_true")
    github_pr.set_defaults(func=command_github_pr_create)
    github_issue = github_sub.add_parser("issue-import", help="Importa issue via gh CLI")
    github_issue.add_argument("issue")
    github_issue.set_defaults(func=command_github_issue_import)

    report = sub.add_parser("report", help="Gera relatorio da task")
    report.add_argument("task_id")
    report.set_defaults(func=command_report)

    preflight = sub.add_parser("preflight", help="Valida contexto obrigatorio ingerido e atualizado")
    preflight.add_argument("task_id", nargs="?", help="Task opcional para incluir required_docs do contrato")
    preflight.add_argument("--json", action="store_true", help="Tambem imprime resultado estruturado em JSON")
    preflight.set_defaults(func=command_preflight)

    dashboard = sub.add_parser("dashboard", help="Dashboard local do Harness")
    dashboard_sub = dashboard.add_subparsers(dest="dashboard_command", required=True)
    dashboard_html = dashboard_sub.add_parser("html", help="Gera HTML estatico")
    dashboard_html.set_defaults(func=command_dashboard_html)
    dashboard_build = dashboard_sub.add_parser("build", help="Alias de html")
    dashboard_build.set_defaults(func=command_dashboard_html)
    dashboard_hub = dashboard_sub.add_parser("hub", help="Gera hub pixel-art multi-repo")
    dashboard_hub.add_argument("--watch-repo", action="append", help="Repo Harness a monitorar; repetivel")
    dashboard_hub.add_argument("--refresh-seconds", type=int, default=3, help="Intervalo de refresh da UI")
    dashboard_hub.set_defaults(func=command_dashboard_hub)
    dashboard_hub_add = dashboard_sub.add_parser("hub-add-repo", help="Registra repos fixos no hub")
    dashboard_hub_add.add_argument("path", nargs="+")
    dashboard_hub_add.set_defaults(func=command_dashboard_hub_add_repo)
    dashboard_hub_remove = dashboard_sub.add_parser("hub-remove-repo", help="Remove repos fixos do hub")
    dashboard_hub_remove.add_argument("path", nargs="+")
    dashboard_hub_remove.set_defaults(func=command_dashboard_hub_remove_repo)
    dashboard_hub_list = dashboard_sub.add_parser("hub-list-repos", help="Lista repos fixos do hub")
    dashboard_hub_list.add_argument("--json", action="store_true")
    dashboard_hub_list.set_defaults(func=command_dashboard_hub_list_repos)
    dashboard_hub_state = dashboard_sub.add_parser("hub-state", help="Atualiza JSON do hub multi-repo")
    dashboard_hub_state.add_argument("--watch-repo", action="append", help="Repo Harness a monitorar; repetivel")
    dashboard_hub_state.add_argument("--json", action="store_true", help="Imprime JSON")
    dashboard_hub_state.set_defaults(func=command_dashboard_hub_state)
    dashboard_hub_serve = dashboard_sub.add_parser("hub-serve", help="Serve hub pixel-art multi-repo")
    dashboard_hub_serve.add_argument("--watch-repo", action="append", help="Repo Harness a monitorar; repetivel")
    dashboard_hub_serve.add_argument("--host", default="127.0.0.1")
    dashboard_hub_serve.add_argument("--port", type=int, default=8899)
    dashboard_hub_serve.add_argument("--refresh-seconds", type=int, default=3, help="Intervalo de refresh da UI")
    dashboard_hub_serve.add_argument("--once", action="store_true", help="Atende uma requisicao e encerra")
    dashboard_hub_serve.add_argument("--quiet", action="store_true", help="Reduz log HTTP")
    dashboard_hub_serve.set_defaults(func=command_dashboard_hub_serve)
    dashboard_serve = dashboard_sub.add_parser("serve", help="Serve dashboard local")
    dashboard_serve.add_argument("--host", default="127.0.0.1")
    dashboard_serve.add_argument("--port", type=int, default=8765)
    dashboard_serve.add_argument("--once", action="store_true", help="Atende uma requisicao e encerra")
    dashboard_serve.set_defaults(func=command_dashboard_serve)

    agent = sub.add_parser("agent", help="Registra agents reais para o hub")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_register = agent_sub.add_parser("register", help="Registra ou atualiza um agent")
    agent_register.add_argument("agent_id")
    agent_register.add_argument("--name")
    agent_register.add_argument("--role", default="operator", choices=["builder", "reviewer", "security", "reporter", "operator"])
    agent_register.add_argument("--state", default="working", choices=["working", "idle", "blocked", "done"])
    agent_register.add_argument("--task-id")
    agent_register.add_argument("--phase")
    agent_register.add_argument("--speech")
    agent_register.add_argument("--run-dir")
    agent_register.add_argument("--surface-id")
    agent_register.set_defaults(func=command_agent_register)
    agent_heartbeat = agent_sub.add_parser("heartbeat", help="Atualiza heartbeat e fala de um agent")
    agent_heartbeat.add_argument("agent_id")
    agent_heartbeat.add_argument("--state", choices=["working", "idle", "blocked", "done"])
    agent_heartbeat.add_argument("--speech")
    agent_heartbeat.add_argument("--surface-id")
    agent_heartbeat.set_defaults(func=command_agent_heartbeat)
    agent_done = agent_sub.add_parser("done", help="Marca agent como finalizado")
    agent_done.add_argument("agent_id")
    agent_done.add_argument("--state", default="done", choices=["done", "idle", "blocked"])
    agent_done.add_argument("--speech")
    agent_done.set_defaults(func=command_agent_done)
    agent_list = agent_sub.add_parser("list", help="Lista agents registrados")
    agent_list.add_argument("--json", action="store_true")
    agent_list.set_defaults(func=command_agent_list)

    events = sub.add_parser("events", help="Lista o stream local de eventos")
    events_sub = events.add_subparsers(dest="events_command", required=True)
    events_list = events_sub.add_parser("list", help="Lista eventos recentes")
    events_list.add_argument("--task-id")
    events_list.add_argument("--limit", type=int, default=40)
    events_list.add_argument("--json", action="store_true")
    events_list.set_defaults(func=command_events_list)

    status = sub.add_parser("status", help="Mostra estado do Harness")
    status.set_defaults(func=command_status)

    compat = sub.add_parser("compat", help="Contrato de compatibilidade da skill")
    compat_sub = compat.add_subparsers(dest="compat_command", required=True)
    compat_manifest = compat_sub.add_parser("manifest", help="Mostra comandos publicos protegidos")
    compat_manifest.add_argument("--json", action="store_true")
    compat_manifest.set_defaults(func=command_compat_manifest)
    compat_smoke = compat_sub.add_parser("skill-smoke", help="Roda smoke test local do fluxo usado pela skill")
    compat_smoke.add_argument("--workdir", help="Diretorio onde criar repo falso; padrao usa temp")
    compat_smoke.add_argument("--json", action="store_true")
    compat_smoke.set_defaults(func=command_compat_skill_smoke)

    plugin = sub.add_parser("plugin", help="Registry local de plugins")
    plugin_sub = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_add = plugin_sub.add_parser("add", help="Registra plugin")
    plugin_add.add_argument("name")
    plugin_add.add_argument("--path")
    plugin_add.add_argument("--command")
    plugin_add.add_argument("--event", action="append")
    plugin_add.add_argument("--description")
    plugin_add.add_argument("--disabled", action="store_true")
    plugin_add.set_defaults(func=command_plugin_add)
    plugin_list = plugin_sub.add_parser("list", help="Lista plugins")
    plugin_list.set_defaults(func=command_plugin_list)
    plugin_enable = plugin_sub.add_parser("enable", help="Habilita plugin")
    plugin_enable.add_argument("name")
    plugin_enable.set_defaults(func=command_plugin_set_enabled)
    plugin_disable = plugin_sub.add_parser("disable", help="Desabilita plugin")
    plugin_disable.add_argument("name")
    plugin_disable.set_defaults(func=command_plugin_set_enabled)
    plugin_run = plugin_sub.add_parser("run", help="Executa plugins de um evento")
    plugin_run.add_argument("event")
    plugin_run.add_argument("--task-id")
    plugin_run.add_argument("--dry-run", action="store_true")
    plugin_run.add_argument("--reviewed", action="store_true", help="Confirma que os comandos dos plugins foram revisados")
    plugin_run.add_argument("--timeout", type=int, default=300)
    plugin_run.set_defaults(func=command_plugin_run)

    telegram = sub.add_parser("telegram", help="Integra o Harness com Telegram")
    telegram_sub = telegram.add_subparsers(dest="telegram_command", required=True)

    telegram_configure = telegram_sub.add_parser("configure", help="Configura notificacoes e inbox do Telegram")
    telegram_configure.add_argument("--enable", action="store_true", help="Habilita notificacoes Telegram")
    telegram_configure.add_argument("--disable", action="store_true", help="Desabilita notificacoes Telegram")
    telegram_configure.add_argument("--token-env", help="Nome da variavel de ambiente com o token do bot")
    telegram_configure.add_argument("--chat-id", action="append", help="Chat que recebe notificacoes; repetivel")
    telegram_configure.add_argument("--allowed-chat-id", action="append", help="Chat autorizado a mandar prompts; repetivel")
    telegram_configure.add_argument("--event", action="append", help="Evento que deve notificar; repetivel")
    telegram_configure.add_argument("--allow-task-creation", action="store_true", help="Permite /new criar tasks")
    telegram_configure.add_argument("--block-task-creation", action="store_true", help="Bloqueia /new criar tasks")
    telegram_configure.add_argument("--allow-remote-execution", action="store_true", help="Permite Telegram chamar Codex exec")
    telegram_configure.add_argument("--block-remote-execution", action="store_true", help="Bloqueia Telegram chamar Codex exec")
    telegram_configure.add_argument("--download-media", action="store_true", help="Baixa imagens/audios recebidos")
    telegram_configure.add_argument("--no-download-media", action="store_true", help="Nao baixa imagens/audios recebidos")
    telegram_configure.add_argument("--openai-media", action="store_true", help="Usa OpenAI opcional para transcrever/descrever midia")
    telegram_configure.add_argument("--no-openai-media", action="store_true", help="Desliga leitura opcional de midia via OpenAI")
    telegram_configure.set_defaults(func=command_telegram_configure)

    telegram_send = telegram_sub.add_parser("send", help="Envia uma mensagem manual de teste")
    telegram_send.add_argument("text", nargs="?", help="Texto a enviar")
    telegram_send.add_argument("--text-file", help="Arquivo de texto a enviar")
    telegram_send.add_argument("--chat-id", action="append", help="Chat alvo; por padrao usa telegram.chat_ids")
    telegram_send.set_defaults(func=command_telegram_send)

    telegram_listen = telegram_sub.add_parser("listen", help="Recebe prompts via long polling")
    telegram_listen.add_argument("--once", action="store_true", help="Busca uma vez e encerra")
    telegram_listen.add_argument("--timeout", type=int, default=25, help="Tempo de long polling em segundos")
    telegram_listen.add_argument("--limit", type=int, default=20, help="Maximo de updates por chamada")
    telegram_listen.add_argument("--create-tasks", action="store_true", help="Cria task automaticamente para mensagens recebidas")
    telegram_listen.add_argument("--no-download-media", action="store_true", help="Nao baixa midia nesta execucao")
    telegram_listen.add_argument("--no-reply", action="store_true", help="Nao responde no Telegram")
    telegram_listen.set_defaults(func=command_telegram_listen)

    telegram_codex = telegram_sub.add_parser("codex", help="Gateway Telegram -> Codex exec")
    telegram_codex.add_argument("--once", action="store_true", help="Busca uma vez e encerra")
    telegram_codex.add_argument("--poll-timeout", type=int, default=25, help="Tempo de long polling em segundos")
    telegram_codex.add_argument("--limit", type=int, default=10, help="Maximo de updates por chamada")
    add_telegram_codex_exec_args(telegram_codex, timeout_first=True)
    telegram_codex.add_argument("--no-download-media", action="store_true", help="Nao baixa midia nesta execucao")
    telegram_codex.add_argument("--no-reply", action="store_true", help="Nao responde no Telegram")
    telegram_codex.set_defaults(func=command_telegram_codex)

    telegram_mirror = telegram_sub.add_parser("mirror", help="Espelha uma sessao Codex ativa para Telegram")
    telegram_mirror.add_argument("--once", action="store_true", help="Lê uma vez e encerra")
    telegram_mirror.add_argument("--session-file", help="Arquivo rollout .jsonl especifico; por padrao usa a sessao mais recente")
    telegram_mirror.add_argument("--from-start", action="store_true", help="Envia desde o inicio do arquivo; por padrao comeca do fim")
    telegram_mirror.add_argument("--include-tools", action="store_true", help="Tambem envia chamadas/saidas de ferramentas")
    telegram_mirror.add_argument("--interval", type=float, default=2.0, help="Intervalo de leitura em segundos")
    telegram_mirror.add_argument("--chat-id", action="append", help="Chat alvo; por padrao usa telegram.chat_ids")
    telegram_mirror.set_defaults(func=command_telegram_mirror)

    telegram_bridge = telegram_sub.add_parser("bridge", help="Espelha Codex e recebe mensagens Telegram")
    telegram_bridge.add_argument("--once", action="store_true", help="Lê/processa uma vez e encerra")
    telegram_bridge.add_argument("--session-file", help="Arquivo rollout .jsonl especifico; por padrao usa a sessao mais recente")
    telegram_bridge.add_argument("--from-start", action="store_true", help="Envia desde o inicio do arquivo; por padrao comeca do fim")
    telegram_bridge.add_argument("--include-tools", action="store_true", help="Tambem envia chamadas/saidas de ferramentas")
    telegram_bridge.add_argument("--interval", type=float, default=2.0, help="Intervalo de leitura em segundos")
    telegram_bridge.add_argument("--poll-timeout", type=int, default=2, help="Tempo de long polling do Telegram")
    telegram_bridge.add_argument("--limit", type=int, default=10, help="Maximo de updates por chamada")
    telegram_bridge.add_argument("--chat-id", action="append", help="Chat alvo; por padrao usa telegram.chat_ids")
    telegram_bridge.add_argument("--no-harness-events", action="store_true", help="Nao encaminha o stream .harness/events.jsonl")
    telegram_bridge.add_argument("--follow-latest", action="store_true", default=True, help="Segue a sessao Codex mais recente")
    telegram_bridge.add_argument("--send-mode", choices=["queue", "codex-exec"], default="queue", help="Como tratar mensagens comuns do Telegram")
    add_telegram_codex_exec_args(telegram_bridge, bridge=True)
    telegram_bridge.add_argument("--no-download-media", action="store_true", help="Nao baixa midia nesta execucao")
    telegram_bridge.add_argument("--no-reply", action="store_true", help="Nao responde no Telegram")
    telegram_bridge.set_defaults(func=command_telegram_bridge)

    telegram_status = telegram_sub.add_parser("status", help="Mostra configuracao Telegram")
    telegram_status.set_defaults(func=command_telegram_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except HarnessError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        if os.environ.get("HARNESS_DEBUG"):
            raise
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

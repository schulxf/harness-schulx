from __future__ import annotations

from pathlib import Path

from .agent_registry import agent_registry_path
from .artifacts import artifacts_index_path
from .clock import utc_now
from .defaults import (
    DEFAULT_EVALUATION_POLICY,
    DEFAULT_FAILURE_POLICY,
    DEFAULT_GITHUB_CONFIG,
    DEFAULT_OPERATION_PROFILES,
    DEFAULT_PROTECTED_BRANCHES,
    DEFAULT_REVIEW_POLICY,
    DEFAULT_TELEGRAM_CONFIG,
)
from .hub_registry import hub_repo_registry_path
from .paths import (
    config_path,
    context_manifest_path,
    event_stream_path,
    harness_root,
    memory_index_path,
    plugin_registry_path,
    queue_path,
    tasks_index_path,
)
from .plugin_registry import save_plugins
from .sensors import detect_default_sensors
from .storage import write_json, write_text

HARNESS_DIRECTORIES = [
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
]


def default_config(root: Path, *, project_name: str, sensors: list[str], runner_version: str) -> dict[str, object]:
    return {
        "version": 1,
        "runner_version": runner_version,
        "project_name": project_name,
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


def initialize_harness_project(
    root: Path,
    *,
    name: str | None,
    sensors: list[str] | None,
    force: bool,
    runner_version: str,
) -> list[str]:
    hroot = harness_root(root)
    for relative in HARNESS_DIRECTORIES:
        (hroot / relative).mkdir(parents=True, exist_ok=True)

    resolved_sensors = sensors if sensors is not None else detect_default_sensors(root)
    config = default_config(
        root,
        project_name=name or root.name,
        sensors=resolved_sensors,
        runner_version=runner_version,
    )

    if not config_path(root).exists() or force:
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
    return resolved_sensors

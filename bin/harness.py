#!/usr/bin/env python3
"""
Harness Runner MVP.

A small deterministic CLI for turning PRDs/issues into executable agent work:
tasks, contracts, run briefs, sensor evidence, evaluations, and reports.
It has no external dependencies.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.3.0"
HARNESS_DIR = ".harness"
DEFAULT_PROTECTED_BRANCHES = ["main", "master", "production"]
DEFAULT_OPERATION_PROFILES = {
    "fast": {
        "description": "Loop curto para feedback rapido.",
        "sensor_tier": "quick",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 1,
        "time_budget_minutes": 30,
    },
    "balanced": {
        "description": "Padrao para trabalho diario.",
        "sensor_tier": "affected",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 2,
        "time_budget_minutes": 90,
    },
    "standard": {
        "description": "Alias documentado para trabalho diario equilibrado.",
        "sensor_tier": "full",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 2,
        "time_budget_minutes": 90,
    },
    "strict": {
        "description": "Mais rigor para areas sensiveis.",
        "sensor_tier": "full",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 3,
        "time_budget_minutes": 180,
    },
    "deep": {
        "description": "Alias documentado para revisao profunda.",
        "sensor_tier": "full",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 3,
        "time_budget_minutes": 180,
    },
    "release": {
        "description": "Fechamento antes de publicar.",
        "sensor_tier": "all",
        "review": "parallel",
        "security_scan_required": True,
        "ptbr_review_required": True,
        "max_fix_attempts": 3,
        "time_budget_minutes": 240,
    },
}
DEFAULT_FAILURE_POLICY = {
    "max_fix_attempts": 3,
    "auto_fix_brief": True,
    "p0_blocks": True,
    "p1_blocks": True,
    "p2_blocks": False,
}
DEFAULT_GITHUB_CONFIG = {
    "repo": "",
    "remote": "origin",
    "default_base": "main",
}
SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE" r" KEY-----")),
    ("telegram_bot_token", re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "secret_assignment",
        re.compile(
            r"\b(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)\b\s*[:=]\s*['\"]?"
            r"(?!<|example|changeme|your-|novo-token|telegram-bot-token|openai-api-key)"
            r"[A-Za-z0-9_./:+-]{16,}",
            re.IGNORECASE,
        ),
    ),
]
SECURITY_EXCLUDED_DIRS = {
    ".git",
    ".harness",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
}
CONTEXT_KINDS = [
    "context",
    "domain-context",
    "prd",
    "issue",
    "architecture",
    "infrastructure",
    "security",
    "testing",
    "refactor-plan",
    "decision",
    "adr",
    "guardrail",
    "other",
]
DEFAULT_EVALUATION_POLICY = {
    "mode": "spawned_agent",
    "fork_context": False,
    "input_scope": "evaluator_agent_handoff",
}
DEFAULT_REVIEW_POLICY = {
    "enabled": True,
    "mode": "spawned_agent",
    "fork_context": False,
    "skill": "greptile-review",
    "input_scope": "greptile_reviewer_handoff",
    "blocking_findings": {
        "p0": True,
        "p1_in_changed_surface": True,
        "p2": False,
    },
}
DEFAULT_TELEGRAM_CONFIG = {
    "enabled": False,
    "token_env": "HARNESS_TELEGRAM_BOT_TOKEN",
    "chat_ids": [],
    "allowed_chat_ids": [],
    "notify_events": [
        "run_started",
        "sensors_completed",
        "evaluation_brief_created",
        "evaluation_recorded",
        "fix_brief_created",
        "report_created",
    ],
    "allow_task_creation": True,
    "allow_remote_execution": False,
    "download_media": True,
    "max_download_bytes": 20 * 1024 * 1024,
    "openai_media": {
        "enabled": False,
        "api_key_env": "OPENAI_API_KEY",
        "audio_model": "gpt-4o-mini-transcribe",
        "vision_model": "gpt-4.1-mini",
        "transcribe_audio": True,
        "describe_images": True,
    },
}


class HarnessError(Exception):
    """User-facing CLI error without a Python traceback."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] or "untitled"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@contextmanager
def exclusive_lock(lock_path: Path, timeout_seconds: float = 30.0) -> Iterator[None]:
    """Acquire a small cross-process lock represented by an atomic directory."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock_path.mkdir()
            break
        except FileExistsError:
            try:
                age_seconds = time.time() - lock_path.stat().st_mtime
                if age_seconds > max(120.0, timeout_seconds * 4):
                    lock_path.rmdir()
                    continue
            except (FileNotFoundError, OSError):
                pass
            if time.monotonic() >= deadline:
                raise HarnessError(
                    f"Timeout aguardando trava de estado: {lock_path}"
                ) from None
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            lock_path.rmdir()
        except FileNotFoundError:
            pass


def state_lock(root: Path, name: str) -> Any:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-") or "state"
    return exclusive_lock(harness_root(root) / "locks" / f"{safe_name}.lock")


def root_from_args(args: argparse.Namespace) -> Path:
    return Path(args.repo).expanduser().resolve()


def require_existing_root(root: Path) -> None:
    if not root.exists():
        raise SystemExit(
            f"Diretorio do repo nao existe: {root}\n"
            "Use um caminho real ja existente ou rode `init --create` de forma explicita."
        )
    if not root.is_dir():
        raise SystemExit(f"O caminho do repo nao e um diretorio: {root}")


def harness_root(root: Path) -> Path:
    return root / HARNESS_DIR


def require_init(root: Path) -> None:
    if not (harness_root(root) / "config.json").exists():
        raise SystemExit(
            f"Harness nao inicializado em {root}. Rode: harness --repo {root} init"
        )


def config_path(root: Path) -> Path:
    return harness_root(root) / "config.json"


def load_config(root: Path) -> dict[str, Any]:
    require_init(root)
    return read_json(config_path(root), {})


def evaluation_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_EVALUATION_POLICY)
    policy.update(config.get("evaluation_policy", {}))
    return policy


def review_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_REVIEW_POLICY)
    configured = config.get("review_policy", {})
    if isinstance(configured, dict):
        blocking = dict(DEFAULT_REVIEW_POLICY["blocking_findings"])
        blocking.update(configured.get("blocking_findings", {}))
        policy.update(configured)
        policy["blocking_findings"] = blocking
    return policy


def failure_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_FAILURE_POLICY)
    configured = config.get("failure_policy", {})
    if isinstance(configured, dict):
        policy.update(configured)
    return policy


def github_config(config: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("github", {})
    return deep_merge(DEFAULT_GITHUB_CONFIG, configured if isinstance(configured, dict) else {})


def operation_profiles(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = {name: dict(value) for name, value in DEFAULT_OPERATION_PROFILES.items()}
    configured = config.get("operation_profiles", {})
    if isinstance(configured, dict):
        for name, value in configured.items():
            if isinstance(value, dict):
                base = dict(profiles.get(str(name), {}))
                base.update(value)
                profiles[str(name)] = base
    return profiles


def active_profile_name(config: dict[str, Any], requested: str | None = None) -> str:
    profiles = operation_profiles(config)
    name = requested or str(config.get("active_profile") or "balanced")
    if name not in profiles:
        raise SystemExit(f"Profile desconhecido: {name}. Use `profile list`.")
    return name


def active_profile(config: dict[str, Any], requested: str | None = None) -> dict[str, Any]:
    name = active_profile_name(config, requested)
    profile = dict(operation_profiles(config)[name])
    profile["name"] = name
    return profile


def config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def deep_merge(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    overrides = overrides or {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            configured = overrides.get(key, {})
            result[key] = deep_merge(value, configured if isinstance(configured, dict) else {})
        elif isinstance(value, list):
            configured = overrides.get(key, value)
            result[key] = list(configured) if isinstance(configured, list) else list(value)
        else:
            result[key] = overrides.get(key, value)
    for key, value in overrides.items():
        if key not in result:
            result[key] = value
    return result


def telegram_config(config: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("telegram", {})
    return deep_merge(DEFAULT_TELEGRAM_CONFIG, configured if isinstance(configured, dict) else {})


def tasks_index_path(root: Path) -> Path:
    return harness_root(root) / "tasks" / "index.json"


def queue_path(root: Path) -> Path:
    return harness_root(root) / "queue" / "index.json"


def supervisor_state_path(root: Path) -> Path:
    return harness_root(root) / "supervisor" / "state.json"


def checkpoints_root(root: Path, task_id: str | None = None) -> Path:
    base = harness_root(root) / "checkpoints"
    return base / task_id if task_id else base


def artifacts_root(root: Path) -> Path:
    return harness_root(root) / "artifacts"


def artifacts_index_path(root: Path) -> Path:
    return artifacts_root(root) / "index.json"


def dashboard_root(root: Path) -> Path:
    return harness_root(root) / "dashboard"


def dashboard_hub_root(root: Path) -> Path:
    return dashboard_root(root) / "hub"


def memory_index_path(root: Path) -> Path:
    return harness_root(root) / "memory" / "index.json"


def plugin_registry_path(root: Path) -> Path:
    return harness_root(root) / "plugins" / "registry.json"


def security_root(root: Path) -> Path:
    return harness_root(root) / "security"


def github_root(root: Path) -> Path:
    return harness_root(root) / "github"


def load_tasks(root: Path) -> list[dict[str, Any]]:
    return read_json(tasks_index_path(root), [])


def find_task(root: Path, task_id: str) -> dict[str, Any]:
    for task in load_tasks(root):
        if task["task_id"] == task_id:
            return task
    raise SystemExit(f"Task nao encontrada: {task_id}")


def update_task(root: Path, task_id: str, **updates: Any) -> None:
    with state_lock(root, "tasks"):
        tasks = load_tasks(root)
        for task in tasks:
            if task["task_id"] == task_id:
                task.update(updates)
                task["updated_at"] = utc_now()
                write_json(tasks_index_path(root), tasks)
                return
    raise SystemExit(f"Task nao encontrada: {task_id}")


def next_task_id_from(tasks: list[dict[str, Any]]) -> str:
    numbers = []
    for task in tasks:
        match = re.match(r"TASK-(\d+)$", task["task_id"])
        if match:
            numbers.append(int(match.group(1)))
    return f"TASK-{(max(numbers) + 1) if numbers else 1:03d}"


def load_queue(root: Path) -> list[dict[str, Any]]:
    return read_json(queue_path(root), [])


def queue_item_id(task_id: str) -> str:
    return f"Q-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{task_id.lower()}"


def queue_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in load_queue(root):
        status = str(item.get("status") or "queued")
        counts[status] = counts.get(status, 0) + 1
    return counts


def sorted_queue_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def next_queued_item(root: Path) -> dict[str, Any] | None:
    for item in sorted_queue_items(load_queue(root)):
        if item.get("status") == "queued":
            return item
    return None


def active_queue_item(root: Path) -> dict[str, Any] | None:
    for item in sorted_queue_items(load_queue(root)):
        if item.get("status") == "active":
            return item
    return None


def update_queue_item(root: Path, item_id: str, **updates: Any) -> dict[str, Any]:
    with state_lock(root, "queue"):
        items = load_queue(root)
        for item in items:
            if item.get("id") == item_id:
                item.update(updates)
                item["updated_at"] = utc_now()
                write_json(queue_path(root), items)
                return item
    raise SystemExit(f"Item de fila nao encontrado: {item_id}")


def task_budget(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    requested = task.get("budget", {}).get("profile")
    if requested and requested not in operation_profiles(config):
        profile = {"name": requested}
        if isinstance(config.get("profiles"), dict):
            profile.update(config["profiles"].get(requested, {}))
        if isinstance(config.get("budgets"), dict):
            profile.update(config["budgets"].get(requested, {}))
    else:
        profile = active_profile(config, requested)
    budget = dict(profile)
    if isinstance(task.get("budget"), dict):
        budget.update(task["budget"])
    return budget


def context_manifest_path(root: Path) -> Path:
    return harness_root(root) / "context" / "manifest.json"


def telegram_root(root: Path) -> Path:
    return harness_root(root) / "telegram"


def telegram_state_path(root: Path) -> Path:
    return telegram_root(root) / "state.json"


def telegram_inbox_root(root: Path) -> Path:
    return harness_root(root) / "inbox" / "telegram"


def telegram_media_root(root: Path) -> Path:
    return telegram_inbox_root(root) / "media"


def telegram_codex_root(root: Path) -> Path:
    return telegram_root(root) / "codex"


def resolve_repo_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve(strict=False)


def is_inside_root(root: Path, path: Path) -> bool:
    resolved_root = root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_root:
        return True
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def assert_inside_root(root: Path, path: Path, label: str = "path") -> Path:
    if not is_inside_root(root, path):
        resolved_root = root.resolve(strict=False)
        resolved_path = path.resolve(strict=False)
        raise SystemExit(
            f"{label} fora do repo bloqueado: {resolved_path}\n"
            f"Caminhos devem ficar dentro de {resolved_root}."
        )
    return path.resolve(strict=False)


def relative_to_root(root: Path, path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path.resolve(strict=False)).replace("\\", "/")


def normalize_path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def to_posix(path: str | Path) -> str:
    return str(path).replace("\\", "/") if path else ""


def load_memory(root: Path) -> list[dict[str, Any]]:
    return read_json(memory_index_path(root), [])


def save_memory(root: Path, entries: list[dict[str, Any]]) -> None:
    write_json(memory_index_path(root), entries)


def render_memory_context(root: Path, task_id: str | None = None, limit: int = 8) -> str:
    entries = load_memory(root)
    relevant = []
    for entry in reversed(entries):
        if task_id and entry.get("task_id") not in {None, "", task_id}:
            continue
        relevant.append(entry)
        if len(relevant) >= limit:
            break
    if not relevant:
        return "- Nenhuma memoria registrada ainda."
    lines = []
    for entry in relevant:
        tags = ", ".join(entry.get("tags") or [])
        suffix = f" [{tags}]" if tags else ""
        task_suffix = f" ({entry.get('task_id')})" if entry.get("task_id") else ""
        lines.append(f"- {entry.get('text', '').strip()}{task_suffix}{suffix}")
    return "\n".join(lines)


def load_plugins(root: Path) -> list[dict[str, Any]]:
    payload = read_json(plugin_registry_path(root), {"plugins": []})
    if isinstance(payload, dict):
        return payload.get("plugins", [])
    if isinstance(payload, list):
        return payload
    return []


def save_plugins(root: Path, plugins: list[dict[str, Any]]) -> None:
    write_json(plugin_registry_path(root), {"plugins": plugins})


def plugin_by_name(root: Path, name: str) -> dict[str, Any]:
    for plugin in load_plugins(root):
        if plugin.get("name") == name:
            return plugin
    raise SystemExit(f"Plugin nao encontrado: {name}")


def load_artifacts(root: Path) -> list[dict[str, Any]]:
    return read_json(artifacts_index_path(root), [])


def save_artifacts(root: Path, artifacts: list[dict[str, Any]]) -> None:
    write_json(artifacts_index_path(root), artifacts)


def artifact_id(task_id: str, path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"ART-{task_id}-{digest}"


def normalize_context_requirement(root: Path, item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"path": item}
    if isinstance(item, dict):
        path = item.get("path") or item.get("source")
        if not path:
            raise SystemExit(f"Entrada de contexto obrigatorio sem `path`: {item}")
        normalized = dict(item)
        normalized["path"] = path
        return normalized
    raise SystemExit(f"Entrada de contexto obrigatorio invalida: {item}")


def context_requirements_for_task(
    root: Path,
    config: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = config if config is not None else load_config(root)
    raw_items: list[Any] = []
    raw_items.extend(config.get("required_context", []))
    if contract:
        raw_items.extend(contract.get("required_docs", []))

    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = normalize_context_requirement(root, raw_item)
        path = resolve_repo_path(root, item["path"])
        assert_inside_root(root, path, label=f"required_context `{item['path']}`")
        key = normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["absolute_path"] = str(path)
        normalized["display_path"] = relative_to_root(root, path)
        requirements.append(normalized)
    return requirements


def latest_manifest_items_by_source(root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(context_manifest_path(root), [])
    latest: dict[str, dict[str, Any]] = {}
    for item in manifest:
        source = item.get("source")
        if not source:
            continue
        source_path = resolve_repo_path(root, source)
        latest[normalize_path_key(source_path)] = item
    return latest


def preflight_cache_path(root: Path, task_id: str | None = None) -> Path:
    name = task_id or "global"
    return harness_root(root) / "context" / "preflight-cache" / f"{name}.json"


def context_preflight_fingerprint(
    root: Path,
    task_id: str | None,
    config: dict[str, Any],
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    latest = latest_manifest_items_by_source(root)
    items: list[dict[str, Any]] = []
    for requirement in context_requirements_for_task(root, config, contract):
        path = Path(requirement["absolute_path"])
        manifest_item = latest.get(normalize_path_key(path), {})
        stat_payload: dict[str, Any] = {"exists": path.exists()}
        if path.exists():
            stat = path.stat()
            stat_payload.update(
                {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        items.append(
            {
                "path": requirement["display_path"],
                "kind": requirement.get("kind"),
                "required_by": requirement.get("required_by"),
                "source": manifest_item.get("source"),
                "stored_path": manifest_item.get("stored_path"),
                "source_sha256": manifest_item.get("source_sha256"),
                "stored_sha256": manifest_item.get("stored_sha256"),
                "source_size": manifest_item.get("source_size"),
                "source_mtime": manifest_item.get("source_mtime"),
                "stat": stat_payload,
            }
        )
    return {"task_id": task_id, "items": items}


def context_preflight_cache_enabled(config: dict[str, Any]) -> bool:
    policy = config.get("policy", {})
    return config_bool(policy.get("cache_context_preflight"), True)


def check_context_preflight(root: Path, task_id: str | None = None) -> dict[str, Any]:
    config = load_config(root)
    contract = None
    if task_id and contract_file_path(root, task_id).exists():
        contract = read_json(contract_file_path(root, task_id), {})
    fingerprint = context_preflight_fingerprint(root, task_id, config, contract)
    cache_path = preflight_cache_path(root, task_id)
    if context_preflight_cache_enabled(config):
        cached = read_json(cache_path, {})
        if cached.get("fingerprint") == fingerprint and cached.get("result"):
            result = dict(cached["result"])
            result["cache"] = "hit"
            return result
    requirements = context_requirements_for_task(root, config, contract)
    latest = latest_manifest_items_by_source(root)
    checked: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for requirement in requirements:
        path = Path(requirement["absolute_path"])
        key = normalize_path_key(path)
        entry = {
            "path": requirement["display_path"],
            "kind": requirement.get("kind"),
            "required_by": requirement.get("required_by"),
        }
        if not path.exists():
            issue = {**entry, "reason": "source_missing"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        manifest_item = latest.get(key)
        if not manifest_item:
            issue = {**entry, "reason": "not_ingested"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        stored_path = root / manifest_item["stored_path"]
        if not stored_path.exists():
            issue = {**entry, "reason": "stored_copy_missing"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        expected_kind = requirement.get("kind")
        if expected_kind and manifest_item.get("kind") != expected_kind:
            issue = {
                **entry,
                "reason": "kind_mismatch",
                "actual_kind": manifest_item.get("kind"),
            }
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        current_hash = file_sha256(path)
        stored_hash = manifest_item.get("source_sha256")
        if not stored_hash:
            issue = {**entry, "reason": "missing_hash_metadata"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue
        if stored_hash != current_hash:
            issue = {
                **entry,
                "reason": "source_changed_since_ingest",
                "ingested_sha256": stored_hash,
                "current_sha256": current_hash,
            }
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        checked.append(
            {
                **entry,
                "status": "pass",
                "stored_path": manifest_item["stored_path"],
                "ingested_at": manifest_item.get("ingested_at"),
                "source_sha256": stored_hash,
            }
        )

    result = {
        "task_id": task_id,
        "created_at": utc_now(),
        "passed": not issues,
        "requirements": checked,
        "issues": issues,
        "cache": "miss",
    }
    if context_preflight_cache_enabled(config):
        write_json(
            cache_path,
            {
                "created_at": utc_now(),
                "fingerprint": fingerprint,
                "result": result,
            },
        )
    return result


def render_preflight_text(result: dict[str, Any]) -> str:
    lines = []
    task_id = result.get("task_id") or "global"
    lines.append(f"Preflight de contexto: {task_id}")
    if not result.get("requirements"):
        lines.append("- Nenhum contexto obrigatorio configurado.")
        return "\n".join(lines)
    for item in result.get("requirements", []):
        marker = "PASS" if item.get("status") == "pass" else "FAIL"
        suffix = f" ({item.get('kind')})" if item.get("kind") else ""
        reason = f" - {item.get('reason')}" if item.get("reason") else ""
        lines.append(f"- {marker} {item.get('path')}{suffix}{reason}")
    return "\n".join(lines)


def require_context_preflight(root: Path, task_id: str, args: argparse.Namespace) -> None:
    if getattr(args, "skip_preflight", False):
        return
    config = load_config(root)
    policy = config.get("policy", {})
    if policy.get("context_preflight_required_before_start", True) is False:
        return
    result = check_context_preflight(root, task_id)
    if result["passed"]:
        return
    text = render_preflight_text(result)
    raise SystemExit(
        f"{text}\n\n"
        "Start bloqueado: reingira os documentos obrigatorios com `harness ingest` "
        "ou ajuste `required_context`/`required_docs` se a exigencia estiver incorreta."
    )


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    event = {
        "ts": utc_now(),
        "type": event_type,
        "payload": payload,
    }
    append_jsonl(run_dir / "events.jsonl", event)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with exclusive_lock(lock_path):
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def http_json_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            detail = parsed.get("description") or parsed.get("error", {}).get("message") or body
        except Exception:
            detail = body or exc.reason
        raise HarnessError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HarnessError(f"Erro de rede: {exc.reason}") from exc


def http_multipart_post(
    url: str,
    fields: dict[str, str],
    files: list[tuple[str, Path, str]],
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    boundary = f"----HarnessBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, path, content_type in files:
        chunks.append(f"--{boundary}\r\n".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\n'
        )
        chunks.append(disposition.encode("utf-8"))
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            detail = parsed.get("description") or parsed.get("error", {}).get("message") or body
        except Exception:
            detail = body or exc.reason
        raise HarnessError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HarnessError(f"Erro de rede: {exc.reason}") from exc


def telegram_token(config: dict[str, Any]) -> str:
    tconfig = telegram_config(config)
    return os.environ.get(str(tconfig.get("token_env") or "HARNESS_TELEGRAM_BOT_TOKEN"), "")


def telegram_api_call(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/{method}"
    response = http_json_post(url, payload or {}, timeout=timeout)
    if not response.get("ok"):
        raise HarnessError(response.get("description") or f"Telegram API error in {method}")
    return response.get("result")


def split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def telegram_send_message(
    config: dict[str, Any],
    text: str,
    chat_ids: list[str] | None = None,
) -> list[Any]:
    tconfig = telegram_config(config)
    token = telegram_token(config)
    targets = chat_ids if chat_ids is not None else [str(item) for item in tconfig.get("chat_ids", [])]
    if not token or not targets:
        return []
    sent = []
    for chat_id in targets:
        for chunk in split_telegram_text(text):
            sent.append(
                telegram_api_call(
                    token,
                    "sendMessage",
                    {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                )
            )
    return sent


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
    append_event(run_dir, event_type, payload)
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


def openai_media_config(config: dict[str, Any]) -> dict[str, Any]:
    return telegram_config(config).get("openai_media", {})


def openai_api_key(config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    return os.environ.get(str(media.get("api_key_env") or "OPENAI_API_KEY"), "")


def openai_extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    texts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts).strip()


def openai_transcribe_audio(path: Path, config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    api_key = openai_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key not found.")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = http_multipart_post(
        "https://api.openai.com/v1/audio/transcriptions",
        {
            "model": str(media.get("audio_model") or "gpt-4o-mini-transcribe"),
            "response_format": "json",
        },
        [("file", path, content_type)],
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    text = response.get("text") or response.get("transcript")
    return str(text).strip() if text else ""


def openai_describe_image(path: Path, config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    api_key = openai_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key not found.")
    content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    image_data = base64.b64encode(path.read_bytes()).decode("ascii")
    response = http_json_post(
        "https://api.openai.com/v1/responses",
        {
            "model": str(media.get("vision_model") or "gpt-4.1-mini"),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Descreva esta imagem em portugues de forma objetiva, "
                                "focando no pedido que ela provavelmente representa para uma task."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{content_type};base64,{image_data}",
                        },
                    ],
                }
            ],
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    return openai_extract_output_text(response)


def detect_default_sensors(root: Path) -> list[str]:
    sensors: list[str] = []
    package_json = root / "package.json"
    if package_json.exists():
        try:
            package = read_json(package_json, {})
            scripts = package.get("scripts", {})
            for script_name in ["lint", "typecheck", "test", "build"]:
                if script_name in scripts:
                    if script_name == "test":
                        sensors.append("npm test")
                    else:
                        sensors.append(f"npm run {script_name}")
        except Exception:
            pass

    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
        sensors.append("python -m pytest")

    return sensors


def is_git_repo(root: Path) -> bool:
    resolved = root.resolve(strict=False)
    if not any((path / ".git").exists() for path in [resolved, *resolved.parents]):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def current_git_branch(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    branch = git_output(root, ["branch", "--show-current"]).strip()
    return branch or None


def git_output(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "git nao esta instalado ou nao esta no PATH."
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip()


def source_surface_digest(root: Path) -> str:
    """Hash source state while excluding Harness' own mutable evidence files."""
    digest = hashlib.sha256(b"harness-source-surface-v1\n")
    if is_git_repo(root):
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
        )
        untracked = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
        )
        if tracked.returncode == 0 and untracked.returncode == 0:
            raw_paths = set(filter(None, tracked.stdout.split(b"\0")))
            raw_paths.update(filter(None, untracked.stdout.split(b"\0")))
            for raw_path in sorted(raw_paths):
                relative = Path(raw_path.decode("utf-8", errors="surrogateescape"))
                if HARNESS_DIR in relative.parts:
                    continue
                path = root / relative
                digest.update(b"FILE\0" + raw_path + b"\0")
                if path.is_file():
                    digest.update(file_sha256(path).encode())
                else:
                    digest.update(b"MISSING")
            return digest.hexdigest()

    for path in sorted(iter_security_scan_files(root, tracked_only=False)):
        relative = relative_to_root(root, path)
        digest.update(f"FILE\0{relative}\0".encode())
        digest.update(file_sha256(path).encode())
    return digest.hexdigest()


def protected_branches(root: Path) -> list[str]:
    config = read_json(config_path(root), {}) if config_path(root).exists() else {}
    return config.get("protected_branches", DEFAULT_PROTECTED_BRANCHES)


def require_safe_branch(root: Path, args: argparse.Namespace, operation: str) -> None:
    branch = current_git_branch(root)
    if not branch:
        return
    protected = protected_branches(root)
    if branch in protected and not getattr(args, "allow_main", False):
        raise SystemExit(
            f"Operacao bloqueada: `{operation}` esta na branch protegida `{branch}`.\n"
            "Crie uma branch de trabalho, por exemplo: "
            "`git switch -c harness/TASK-001`, ou rode com `--allow-main` antes do comando "
            "se voce realmente quiser operar nessa branch."
        )


def split_sensor_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def resolve_sensor_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    executable = shutil.which(argv[0])
    if not executable:
        return argv
    return [executable, *argv[1:]]


def make_sensor_result(
    command: str,
    argv: list[str],
    resolved_argv: list[str],
    shell: bool,
    exit_code: int,
    duration_ms: int,
    stdout: str = "",
    stderr: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": command,
        "argv": argv,
        "resolved_argv": resolved_argv,
        "shell": shell,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
    }
    payload.update(extra)
    return payload


def latest_run_dir(root: Path, task_id: str) -> Path:
    runs_root = harness_root(root) / "runs" / task_id
    if not runs_root.exists():
        raise SystemExit(f"Nenhuma run encontrada para {task_id}. Rode: harness start {task_id}")
    runs = sorted([path for path in runs_root.iterdir() if path.is_dir()])
    if not runs:
        raise SystemExit(f"Nenhuma run encontrada para {task_id}. Rode: harness start {task_id}")
    return runs[-1]


def latest_run_dir_or_none(root: Path, task_id: str) -> Path | None:
    runs_root = harness_root(root) / "runs" / task_id
    if not runs_root.exists():
        return None
    runs = sorted([path for path in runs_root.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def create_checkpoint(
    root: Path,
    task_id: str,
    reason: str,
    run_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    task = find_task(root, task_id)
    run_dir = run_dir or latest_run_dir_or_none(root, task_id)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "title": task.get("title"),
        "task_status": task.get("status"),
        "reason": reason,
        "created_at": utc_now(),
        "run_dir": str(run_dir) if run_dir else None,
        "contract_exists": contract_file_path(root, task_id).exists(),
        "git_status": git_output(root, ["status", "--short"]) if is_git_repo(root) else "",
        "queue": active_queue_item(root),
        "budget": task.get("budget", {}),
    }
    if run_dir:
        for name in ["sensors.json", "evaluation.json"]:
            path = run_dir / name
            if path.exists():
                payload[name.removesuffix(".json")] = read_json(path, {})
    if extra:
        payload.update(extra)
    root_dir = checkpoints_root(root, task_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root_dir / f"checkpoint-{stamp}.json"
    write_json(path, payload)
    write_json(root_dir / "latest.json", payload)
    return path


def latest_checkpoint_path(root: Path, task_id: str) -> Path | None:
    latest = checkpoints_root(root, task_id) / "latest.json"
    if latest.exists():
        return latest
    paths = sorted(checkpoints_root(root, task_id).glob("checkpoint-*.json"))
    return paths[-1] if paths else None


def render_resume_brief(root: Path, task_id: str, checkpoint: dict[str, Any]) -> str:
    task = find_task(root, task_id)
    contract = read_json(contract_file_path(root, task_id), {}) if contract_file_path(root, task_id).exists() else {}
    run_dir = checkpoint.get("run_dir") or "sem run ainda"
    next_steps = []
    status = task.get("status")
    if not contract:
        next_steps.append(f"1. Criar contrato: python {Path(__file__).resolve()} --repo {root} contract {task_id}")
    elif status in {"contracted", "planned"}:
        next_steps.append(f"1. Iniciar run: python {Path(__file__).resolve()} --repo {root} start {task_id}")
    elif status in {"in_progress", "sensors_failed", "needs_work"}:
        tier = fastest_available_sensor_tier(contract)
        next_steps.append(f"1. Rodar sensores rapidos: python {Path(__file__).resolve()} --repo {root} sensors {task_id} --tier {tier} --reviewed")
        next_steps.append(f"2. Gerar avaliacao/review: python {Path(__file__).resolve()} --repo {root} evaluate {task_id}")
    elif status in {"sensors_passed"}:
        next_steps.append(f"1. Registrar avaliacao ou gerar handoffs: python {Path(__file__).resolve()} --repo {root} evaluate {task_id}")
    elif status in {"passed", "done"}:
        next_steps.append(f"1. Gerar relatorio: python {Path(__file__).resolve()} --repo {root} report {task_id}")
    else:
        next_steps.append("1. Rodar `status` e decidir a proxima etapa.")
    return (
        f"# Resume brief - {task_id}\n\n"
        f"Task: {task.get('title')}\n"
        f"Status atual: {status}\n"
        f"Checkpoint: {checkpoint.get('created_at')}\n"
        f"Motivo: {checkpoint.get('reason')}\n"
        f"Run: {run_dir}\n\n"
        "## Proximo passo recomendado\n\n"
        f"{chr(10).join(next_steps)}\n\n"
        "## Status do Git no checkpoint\n\n"
        f"```text\n{checkpoint.get('git_status') or 'sem status registrado'}\n```\n"
    )


def iter_run_dirs(root: Path, task_id: str | None = None) -> list[Path]:
    runs_root = harness_root(root) / "runs"
    if task_id:
        runs_root = runs_root / task_id
    if not runs_root.exists():
        return []

    if task_id:
        return sorted([path for path in runs_root.iterdir() if path.is_dir()])

    run_dirs: list[Path] = []
    for task_runs_root in sorted([path for path in runs_root.iterdir() if path.is_dir()]):
        run_dirs.extend(sorted([path for path in task_runs_root.iterdir() if path.is_dir()]))
    return run_dirs


def collect_run_artifacts(root: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    interesting = {
        "builder-brief.md",
        "evaluator-brief.md",
        "evaluator-agent-handoff.md",
        "greptile-reviewer-agent-handoff.md",
        "review-consolidation.md",
        "parallel-dispatch.md",
        "events.jsonl",
        "evaluation.json",
        "plain-summary.md",
        "run.json",
    }
    for run_dir in iter_run_dirs(root, task_id):
        task = run_dir.parent.name
        for path in sorted(run_dir.iterdir()):
            if not path.is_file():
                continue
            if path.name in interesting or path.name.startswith("sensors") or path.name.startswith("fix-brief"):
                artifacts.append(
                    {
                        "id": artifact_id(task, path),
                        "task_id": task,
                        "run_id": run_dir.name,
                        "path": to_posix(path.relative_to(root)),
                        "kind": path.suffix.lstrip(".") or "file",
                        "label": path.name,
                        "size": path.stat().st_size,
                        "created_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                        .replace(microsecond=0)
                        .isoformat(),
                    }
                )
    artifacts.extend(load_artifacts(root))
    return artifacts


def find_unevaluated_runs(root: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    unevaluated: list[dict[str, Any]] = []
    for run_dir in iter_run_dirs(root, task_id):
        if not (run_dir / "run.json").exists():
            continue
        run = read_json(run_dir / "run.json", {})
        task = run.get("task_id") or run_dir.parent.name
        if run_has_evaluation_record(root, task, run_dir):
            continue
        unevaluated.append(
            {
                "task_id": task,
                "run_id": run.get("run_id") or run_dir.name,
                "run_dir": str(run_dir),
                "has_sensors": (run_dir / "sensors.json").exists(),
            }
        )
    return unevaluated


def evaluation_markdown_path(root: Path, task_id: str) -> Path:
    return harness_root(root) / "evaluations" / f"{task_id}.md"


def run_evaluation_status(root: Path, task_id: str, run_dir: Path) -> str | None:
    evaluation_path = run_dir / "evaluation.json"
    if evaluation_path.exists():
        evaluation = read_json(evaluation_path, {})
        status = evaluation.get("status")
        return str(status) if status else "recorded"

    markdown_path = evaluation_markdown_path(root, task_id)
    if not markdown_path.exists():
        return None

    markdown = read_text(markdown_path)
    run_path = str(run_dir)
    if run_path not in markdown and to_posix(run_path) not in markdown:
        return None

    match = re.search(r"(?m)^Status:\s*([^\s]+)\s*$", markdown)
    if match:
        return match.group(1)
    return "recorded"


def run_has_evaluation_record(root: Path, task_id: str, run_dir: Path) -> bool:
    return run_evaluation_status(root, task_id, run_dir) is not None


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


def task_file_path(root: Path, task_id: str) -> Path:
    task = find_task(root, task_id)
    return root / task["task_file"]


def contract_file_path(root: Path, task_id: str) -> Path:
    return harness_root(root) / "contracts" / f"{task_id}.json"


def load_contract(root: Path, task_id: str) -> dict[str, Any]:
    path = contract_file_path(root, task_id)
    if not path.exists():
        raise SystemExit(f"Contrato nao encontrado para {task_id}. Rode: harness contract {task_id}")
    return read_json(path, {})


SENSOR_TIERS = ["smoke", "affected", "full"]


def normalize_sensor_tiers(contract: dict[str, Any]) -> dict[str, list[str]]:
    configured = contract.get("sensor_tiers")
    tiers = {tier: [] for tier in SENSOR_TIERS}
    if isinstance(configured, dict):
        for tier in SENSOR_TIERS:
            values = configured.get(tier, [])
            if isinstance(values, list):
                tiers[tier] = [str(item) for item in values if str(item).strip()]

    legacy = [str(item) for item in contract.get("required_sensors", []) if str(item).strip()]
    if legacy:
        for command in legacy:
            if command not in tiers["full"]:
                tiers["full"].append(command)
    return tiers


def sensors_for_tier(contract: dict[str, Any], tier: str) -> list[str]:
    tiers = normalize_sensor_tiers(contract)
    if tier == "all":
        commands: list[str] = []
        for name in SENSOR_TIERS:
            for command in tiers[name]:
                if command not in commands:
                    commands.append(command)
        return commands
    if tier not in tiers:
        raise SystemExit(f"Tier de sensor invalido: {tier}")
    return tiers[tier]


def sensor_plan_digest(tier: str, commands: list[str], allow_shell: bool = False) -> str:
    plan = {
        "tier": tier,
        "commands": [str(command).strip() for command in commands],
        "allow_shell": bool(allow_shell),
    }
    encoded = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def make_sensor_review(sensor_tiers: dict[str, list[str]]) -> dict[str, Any]:
    all_commands: list[str] = []
    for tier in SENSOR_TIERS:
        for command in sensor_tiers.get(tier, []):
            if command not in all_commands:
                all_commands.append(command)
    tier_digests = {
        tier: sensor_plan_digest(tier, sensor_tiers.get(tier, [])) for tier in SENSOR_TIERS
    }
    tier_digests["all"] = sensor_plan_digest("all", all_commands)
    configuration = json.dumps(
        {tier: sensor_tiers.get(tier, []) for tier in SENSOR_TIERS},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "digest": hashlib.sha256(configuration.encode()).hexdigest(),
        "tier_digests": tier_digests,
        "reviewed_at": utc_now(),
    }


def fastest_available_sensor_tier(contract: dict[str, Any]) -> str:
    tiers = normalize_sensor_tiers(contract)
    for tier in SENSOR_TIERS:
        if tiers[tier]:
            return tier
    return "full"


def final_sensor_payload(run_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    tiers = normalize_sensor_tiers(contract)
    if tiers["full"]:
        for filename in ["sensors-full.json", "sensors-all.json", "sensors.json"]:
            path = run_dir / filename
            if not path.exists():
                continue
            payload = read_json(path, {})
            if payload.get("tier") in {"full", "all"}:
                return payload
        return {}
    return read_json(run_dir / "sensors.json", {})


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
            "security_scan_required_before_done": True,
            "ptbr_review_required_before_done": True,
            "review_evidence_required_before_done": True,
            "budget_required_before_done": True,
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


def create_task(root: Path, title: str, body: str, source: str) -> dict[str, Any]:
    with state_lock(root, "tasks"):
        tasks = load_tasks(root)
        task_id = next_task_id_from(tasks)
        task_path = harness_root(root) / "tasks" / f"{task_id}-{slugify(title)}.md"
        created_at = utc_now()
        content = (
            f"# {task_id} - {title}\n\n"
            "Status: planejada\n"
            f"Origem: {source}\n"
            f"Criada: {created_at}\n\n"
            "## O que construir\n\n"
            f"{body.strip() if body.strip() else 'TODO: descrever a fatia vertical.'}\n\n"
            "## Critérios de aceite\n\n"
            "- [ ] TODO: definir comportamento observável.\n\n"
            "## Fora de escopo\n\n"
            "- TODO: definir o que esta task não deve alterar.\n"
        )
        write_text(task_path, content)

        task = {
            "task_id": task_id,
            "title": title,
            "status": "planned",
            "source": to_posix(source) if source and source != "manual" else source,
            "task_file": to_posix(task_path.relative_to(root)),
            "created_at": created_at,
            "updated_at": created_at,
        }
        tasks.append(task)
        write_json(tasks_index_path(root), tasks)
        return task


def short_title(text: str, fallback: str = "Prompt do Telegram") -> str:
    for line in text.splitlines():
        cleaned = plain_clean(line)
        if cleaned:
            return cleaned[:90]
    return fallback


def save_telegram_inbox_item(root: Path, item: dict[str, Any]) -> Path:
    inbox = telegram_inbox_root(root)
    inbox.mkdir(parents=True, exist_ok=True)
    item_id = str(item["id"])
    path = inbox / f"{item_id}.json"
    write_json(path, item)
    append_jsonl(inbox / "index.jsonl", {"ts": utc_now(), "id": item_id, "path": str(path)})
    return path


def telegram_chat_allowed(config: dict[str, Any], chat_id: str) -> bool:
    tconfig = telegram_config(config)
    allowed = [str(item) for item in tconfig.get("allowed_chat_ids", [])]
    if not allowed:
        allowed = [str(item) for item in tconfig.get("chat_ids", [])]
    return not allowed or str(chat_id) in set(allowed)


def telegram_file_extension(file_path: str, fallback: str) -> str:
    suffix = Path(file_path).suffix
    if suffix:
        return suffix
    return fallback


def telegram_download_file(
    root: Path,
    config: dict[str, Any],
    file_id: str,
    item_id: str,
    fallback_ext: str,
) -> dict[str, Any]:
    token = telegram_token(config)
    if not token:
        raise RuntimeError("Telegram token not found.")
    file_info = telegram_api_call(token, "getFile", {"file_id": file_id})
    file_path = str(file_info.get("file_path") or "")
    if not file_path:
        raise RuntimeError("Telegram did not return file_path.")
    max_bytes = int(telegram_config(config).get("max_download_bytes") or 20 * 1024 * 1024)
    url = f"https://api.telegram.org/file/bot{urllib.parse.quote(token, safe=':')}/{file_path}"
    extension = telegram_file_extension(file_path, fallback_ext)
    target = telegram_media_root(root) / f"{item_id}{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, method="GET")
    total = 0
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"Arquivo do Telegram excede limite de {max_bytes} bytes.")
            handle.write(chunk)
    return {
        "file_id": file_id,
        "telegram_file_path": file_path,
        "local_path": str(target),
        "size": total,
    }


def telegram_message_media(message: dict[str, Any]) -> tuple[str | None, str | None, str]:
    if message.get("photo"):
        photo = sorted(message["photo"], key=lambda item: item.get("file_size", 0))[-1]
        return "image", photo.get("file_id"), ".jpg"
    if message.get("voice"):
        return "voice", message["voice"].get("file_id"), ".ogg"
    if message.get("audio"):
        audio = message["audio"]
        suffix = Path(audio.get("file_name") or "").suffix or ".mp3"
        return "audio", audio.get("file_id"), suffix
    document = message.get("document")
    if document:
        mime = str(document.get("mime_type") or "")
        filename = str(document.get("file_name") or "")
        if mime.startswith("image/"):
            return "image", document.get("file_id"), Path(filename).suffix or ".jpg"
        if mime.startswith("audio/"):
            return "audio", document.get("file_id"), Path(filename).suffix or ".mp3"
    return None, None, ""


def analyze_telegram_media(
    path: Path,
    media_kind: str,
    config: dict[str, Any],
) -> tuple[str, str | None]:
    media_config = openai_media_config(config)
    if not config_bool(media_config.get("enabled"), False):
        return "", None
    try:
        if media_kind in {"voice", "audio"} and config_bool(media_config.get("transcribe_audio"), True):
            return openai_transcribe_audio(path, config), None
        if media_kind == "image" and config_bool(media_config.get("describe_images"), True):
            return openai_describe_image(path, config), None
    except Exception as exc:
        return "", str(exc)
    return "", None


def build_telegram_prompt_text(
    kind: str,
    text: str,
    caption: str,
    media_path: str,
    media_analysis: str,
) -> str:
    if text:
        return text.strip()
    parts = []
    if caption:
        parts.append(caption.strip())
    if media_analysis:
        label = "Transcricao" if kind in {"voice", "audio"} else "Descricao da imagem"
        parts.append(f"{label}: {media_analysis.strip()}")
    if media_path:
        parts.append(f"Arquivo recebido: {media_path}")
    if not parts:
        parts.append(f"Mensagem de {kind or 'Telegram'} recebida.")
    return "\n\n".join(parts).strip()


def render_task_body_from_telegram(item: dict[str, Any]) -> str:
    media = item.get("media") or {}
    lines = [
        item.get("prompt_text") or "",
        "",
        "## Origem Telegram",
        "",
        f"- Chat: {item.get('chat_id')}",
        f"- Message ID: {item.get('message_id')}",
        f"- Update ID: {item.get('update_id')}",
    ]
    if media.get("local_path"):
        lines.append(f"- Arquivo: {media.get('local_path')}")
    if item.get("media_analysis_error"):
        lines.append(f"- Aviso de leitura de midia: {item.get('media_analysis_error')}")
    return "\n".join(lines).strip()


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


def telegram_reply(config: dict[str, Any], chat_id: str, text: str) -> None:
    telegram_send_message(config, text, [str(chat_id)])


def codex_executable() -> str:
    executable = shutil.which("codex")
    if not executable:
        raise HarnessError("codex nao encontrado no PATH.")
    return executable


def codex_prompt_from_item(item: dict[str, Any], prompt_text: str | None = None) -> str:
    text = (prompt_text if prompt_text is not None else item.get("prompt_text") or "").strip()
    media = item.get("media") or {}
    header = (
        "Mensagem recebida via Telegram pelo Harness.\n"
        f"Chat: {item.get('chat_id')}\n"
        f"Mensagem: {item.get('message_id')}\n\n"
    )
    if media.get("local_path") and media.get("local_path") not in text:
        text = f"{text}\n\nArquivo anexado salvo em: {media.get('local_path')}".strip()
    return header + (text or "Mensagem sem texto.")


def codex_image_args_from_item(item: dict[str, Any]) -> list[str]:
    media = item.get("media") or {}
    path = media.get("local_path")
    if item.get("kind") != "image" or not path:
        return []
    if not Path(path).exists():
        return []
    return ["-i", str(path)]


def build_codex_exec_argv(
    root: Path,
    output_path: Path,
    *,
    resume_last: bool = False,
    session_id: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    approval: str | None = None,
    bypass: bool = False,
    images: list[str] | None = None,
) -> list[str]:
    argv = [codex_executable(), "exec"]
    if session_id or resume_last:
        argv.append("resume")
        if resume_last:
            argv.append("--last")
        elif session_id:
            argv.append(session_id)
    else:
        argv.extend(["-C", str(root), "--skip-git-repo-check"])
        if sandbox:
            argv.extend(["-s", sandbox])
        if approval:
            argv.extend(["-a", approval])
    if model:
        argv.extend(["-m", model])
    if bypass:
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    if images:
        for image in images:
            argv.extend(["-i", image])
    argv.extend(["-o", str(output_path), "-"])
    return argv


def run_codex_for_telegram(
    root: Path,
    item: dict[str, Any],
    *,
    prompt_text: str | None = None,
    resume_last: bool = False,
    session_id: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    approval: str | None = None,
    bypass: bool = False,
    timeout: int = 1800,
) -> dict[str, Any]:
    run_id = f"{item.get('id')}-{int(time.time())}"
    run_dir = telegram_codex_root(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "last-message.txt"
    prompt = codex_prompt_from_item(item, prompt_text=prompt_text)
    prompt_path = run_dir / "prompt.txt"
    write_text(prompt_path, prompt)
    images = codex_image_args_from_item(item)
    argv = build_codex_exec_argv(
        root,
        output_path,
        resume_last=resume_last,
        session_id=session_id,
        model=model,
        sandbox=sandbox,
        approval=approval,
        bypass=bypass,
        images=images,
    )
    started = time.time()
    result = subprocess.run(
        argv,
        input=prompt,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    duration_ms = int((time.time() - started) * 1000)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    write_text(stdout_path, result.stdout or "")
    write_text(stderr_path, result.stderr or "")
    response = read_text(output_path).strip() if output_path.exists() else (result.stdout or "").strip()
    payload = {
        "run_id": run_id,
        "created_at": utc_now(),
        "duration_ms": duration_ms,
        "exit_code": result.returncode,
        "argv": argv,
        "prompt_path": str(prompt_path),
        "output_path": str(output_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "response": response,
    }
    write_json(run_dir / "codex-run.json", payload)
    return payload


def codex_sessions_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"


def latest_codex_session_file() -> Path:
    root = codex_sessions_root()
    if not root.exists():
        raise HarnessError(f"Diretorio de sessoes Codex nao encontrado: {root}")
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    if not files:
        raise HarnessError(f"Nenhuma sessao Codex encontrada em {root}")
    return max(files, key=lambda path: path.stat().st_mtime)


def mirror_state_key(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode("utf-8")).hexdigest()


def read_mirror_state(root: Path, session_path: Path, from_end: bool) -> int:
    state_path = telegram_root(root) / "mirror-state.json"
    state = read_json(state_path, {})
    key = mirror_state_key(session_path)
    if key in state:
        return int(state[key].get("offset", 0))
    return session_path.stat().st_size if from_end and session_path.exists() else 0


def write_mirror_state(root: Path, session_path: Path, offset: int) -> None:
    state_path = telegram_root(root) / "mirror-state.json"
    state = read_json(state_path, {})
    key = mirror_state_key(session_path)
    state[key] = {
        "path": str(session_path),
        "offset": offset,
        "updated_at": utc_now(),
    }
    write_json(state_path, state)


def decode_codex_session_line(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def summarize_tool_arguments(name: str, arguments: str) -> str:
    try:
        parsed = json.loads(arguments)
    except Exception:
        parsed = arguments
    if name == "shell_command" and isinstance(parsed, dict):
        command = str(parsed.get("command") or "").strip()
        return command[:800]
    if isinstance(parsed, dict):
        compact = json.dumps(parsed, ensure_ascii=False)
        return compact[:800]
    return str(parsed)[:800]


def mirror_message_from_codex_event(event: dict[str, Any], include_tools: bool) -> str | None:
    timestamp = event.get("timestamp", "")
    event_type = event.get("type")
    payload = event.get("payload") or {}

    if event_type == "event_msg":
        ptype = payload.get("type")
        if ptype == "agent_message":
            phase = payload.get("phase")
            label = "Codex"
            if phase == "commentary":
                label = "Codex update"
            elif phase == "final_answer":
                label = "Codex final"
            message = str(payload.get("message") or "").strip()
            return f"{label}:\n{message}" if message else None
        if include_tools and ptype == "token_count":
            usage = payload.get("info", {}).get("last_token_usage", {})
            total = usage.get("total_tokens")
            return f"Codex tokens: ultimo turno usou {total} tokens." if total else None
        return None

    if event_type == "response_item":
        ptype = payload.get("type")
        if include_tools and ptype == "function_call":
            name = str(payload.get("name") or "tool")
            args = summarize_tool_arguments(name, str(payload.get("arguments") or ""))
            return f"Codex ferramenta: {name}\n{args}".strip()
        if include_tools and ptype == "function_call_output":
            output = str(payload.get("output") or "").strip()
            first_lines = "\n".join(output.splitlines()[:6])
            return f"Codex ferramenta terminou:\n{first_lines[:1200]}" if first_lines else None
    if include_tools and event_type:
        return None if timestamp else None
    return None


def read_new_codex_session_events(
    session_path: Path,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if not session_path.exists():
        raise HarnessError(f"Arquivo de sessao Codex nao encontrado: {session_path}")
    size = session_path.stat().st_size
    if offset > size:
        offset = 0
    events: list[dict[str, Any]] = []
    with session_path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        while True:
            line = handle.readline()
            if not line:
                break
            offset = handle.tell()
            event = decode_codex_session_line(line)
            if event:
                events.append(event)
    return events, offset


def queued_operator_messages_path(root: Path) -> Path:
    return telegram_root(root) / "operator-messages.md"


def queue_operator_message(root: Path, item: dict[str, Any], prompt_text: str) -> Path:
    path = queued_operator_messages_path(root)
    record = {
        "ts": utc_now(),
        "chat_id": item.get("chat_id"),
        "message_id": item.get("message_id"),
        "telegram_item_id": item.get("id"),
        "text": prompt_text,
    }
    append_jsonl(telegram_root(root) / "operator-messages.jsonl", record)
    existing = read_text(path) if path.exists() else "# Mensagens do operador via Telegram\n\n"
    block = (
        f"## {record['ts']} - {record['telegram_item_id']}\n\n"
        f"{prompt_text.strip() or 'Mensagem vazia.'}\n\n"
    )
    write_text(path, existing.rstrip() + "\n\n" + block)
    return path


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
                message = render_resume_brief(root, task_id, checkpoint)
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
        state = collect_dashboard_state(root)
        path = dashboard_root(root) / "index.html"
        write_text(path, render_dashboard_html(root, state))
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
        return save_telegram_inbox_item(root, item)

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
        "raw_update": update,
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

    return save_telegram_inbox_item(root, item)


def command_task_create(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "task create")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "task import")
    for raw in args.files:
        source = Path(raw).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"Arquivo nao encontrado: {source}")
        body = read_text(source)
        title = first_heading_or_filename(source, body)
        task = create_task(root, title, body, str(source))
        print(f"Importado {source.name} -> {task['task_id']}: {title}")


def command_task_list(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    tasks = load_tasks(root)
    if not tasks:
        print("Nenhuma task ainda.")
        return
    for task in tasks:
        print(f"{task['task_id']} [{task['status']}] {task['title']}")


def command_pick(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    for task in load_tasks(root):
        if task["status"] not in {"passed", "done"}:
            print(f"{task['task_id']} [{task['status']}] {task['title']}")
            print(task["task_file"])
            return
    print("Nenhuma task pendente.")


def next_queue_id_from(items: list[dict[str, Any]]) -> str:
    numbers = []
    for item in items:
        match = re.match(r"QUEUE-(\d+)$", str(item.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"QUEUE-{(max(numbers) + 1) if numbers else 1:03d}"


def command_queue_add(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "queue add")
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
    with state_lock(root, "queue"):
        queue = load_queue(root)
        if not args.force and task_id:
            for existing in queue:
                if existing.get("task_id") == task_id and existing.get("status") in {
                    "queued",
                    "active",
                }:
                    raise SystemExit(
                        f"{task_id} já está na fila como {existing.get('id')}. "
                        "Use --force para duplicar."
                    )
        created_at = utc_now()
        item = {
            "id": next_queue_id_from(queue),
            "task_id": task_id,
            "title": title,
            "body": body,
            "status": "queued",
            "priority": args.priority,
            "profile": args.profile,
            "created_at": created_at,
            "updated_at": created_at,
        }
        queue.append(item)
        write_json(queue_path(root), queue)
    if task_id and args.profile:
        linked_task = find_task(root, task_id)
        budget = dict(linked_task.get("budget") or {})
        budget["profile"] = args.profile
        update_task(root, task_id, budget=budget)
    print(f"{item['id']} queued: {title}")
    if task_id:
        print(f"Task: {task_id}")


def command_queue_list(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    item = active_queue_item(root) if args.include_active else None
    item = item or next_queued_item(root)
    if not item:
        print("Nenhum item pendente na fila.")
        return
    if args.activate and item.get("status") == "queued":
        require_safe_branch(root, args, "queue next --activate")
        item = update_queue_item(root, item["id"], status="active", activated_at=utc_now())
    print(f"{item['id']} [{item.get('status')}] {item.get('title')}")
    if item.get("task_id"):
        print(f"Task: {item.get('task_id')}")
    if item.get("body"):
        print("\n" + str(item.get("body")).strip())


def command_queue_done(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "queue done")
    items = load_queue(root)
    current = next((item for item in items if item.get("id") == args.queue_id), None)
    if not current:
        raise SystemExit(f"Item de fila não encontrado: {args.queue_id}")
    if current.get("task_id") and args.status == "done":
        task = find_task(root, str(current["task_id"]))
        if task.get("status") != "passed":
            raise SystemExit(
                f"Fila bloqueada: {task['task_id']} ainda não está com status `passed`. "
                "Conclua sensores, segurança, revisão PT-BR, reviewer e avaliação antes."
            )
    item = update_queue_item(
        root,
        args.queue_id,
        status=args.status,
        completed_at=utc_now() if args.status == "done" else None,
        note=args.note or "",
    )
    print(f"{item['id']} -> {item['status']}")


def command_profile_add(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "profile add")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "profile set")
    config = load_config(root)
    active_profile_name(config, args.name)
    config["active_profile"] = args.name
    write_json(config_path(root), config)
    print(f"Profile ativo: {args.name}")


def command_budget_set(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "budget set")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "budget task-set")
    budget = {
        "profile": args.profile,
        "time_budget_minutes": args.minutes,
        "max_fix_attempts": args.max_fix_attempts,
        "sensor_tier": args.sensor_tier,
    }
    update_task(root, args.task_id, budget={k: v for k, v in budget.items() if v is not None})
    print(f"Budget da task atualizado: {args.task_id}")


def command_budget_list(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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


def next_memory_id(root: Path) -> str:
    numbers = []
    for entry in load_memory(root):
        match = re.match(r"MEM-(\d+)$", str(entry.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"MEM-{(max(numbers) + 1) if numbers else 1:03d}"


def command_memory_remember(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "memory remember")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
        "sensor_review": make_sensor_review(sensor_tiers) if args.reviewed_sensors else None,
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


def extract_checklist(text: str) -> list[str]:
    criteria: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            heading = stripped.lower()
            in_section = (
                "acceptance" in heading
                or "criteria" in heading
                or "criterios" in heading
                or "criterio" in heading
                or "aceite" in heading
            )
            continue
        if in_section and stripped.startswith("- ["):
            item = re.sub(r"^- \[[ xX]\]\s*", "", stripped).strip()
            if item and not item.lower().startswith("todo:"):
                criteria.append(item)
    return criteria


def extract_out_of_scope(text: str) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            in_section = "out of scope" in stripped.lower() or "fora de escopo" in stripped.lower()
            continue
        if in_section and stripped.startswith("-"):
            item = stripped.lstrip("-").strip()
            if item and not item.lower().startswith("todo:"):
                items.append(item)
    return items


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
        "Registre também as verificações de segurança e de texto em PT-BR:\n\n"
        f"`python {Path(__file__).resolve()} --repo {root} security scan --task-id {task['task_id']} --fail-on-findings`\n\n"
        f"`python {Path(__file__).resolve()} --repo {root} ptbr-review {task['task_id']} --status pass --notes \"Ortografia, acentuação e clareza conferidas.\"`\n\n"
        "Em seguida, peça avaliação contratual e review Greptile-style usando os handoffs gerados por:\n\n"
        f"`python {Path(__file__).resolve()} --repo {root} evaluate {task['task_id']}`\n\n"
        "O `pass` final também precisa receber o parecer do reviewer com `--review-file` ou `--review-note`.\n\n"
        f"Diretorio da run: `{run_dir}`\n"
    )


def command_start(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "start")
    config = load_config(root)
    maybe_warn_unevaluated_runs(root, config, args.task_id)
    task = find_task(root, args.task_id)
    contract = load_contract(root, args.task_id)
    require_context_preflight(root, args.task_id, args)
    run_id = (
        datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%f")
        + f"-{uuid.uuid4().hex[:8]}Z"
    )
    run_dir = harness_root(root) / "runs" / args.task_id / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    git_repo = is_git_repo(root)
    raw_base_commit = git_output(root, ["rev-parse", "HEAD"]) if git_repo else ""
    base_commit = (
        raw_base_commit if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", raw_base_commit) else None
    )
    initial_git_status = git_output(root, ["status", "--short"]) if git_repo else ""
    budget = task_budget(task, config)
    write_json(
        run_dir / "run.json",
        {
            "task_id": args.task_id,
            "run_id": run_id,
            "created_at": utc_now(),
            "status": "started",
            "root": str(root),
            "base_commit": base_commit,
            "base_branch": current_git_branch(root),
            "initial_git_status": initial_git_status,
            "initial_surface_digest": source_surface_digest(root),
            "budget": budget,
        },
    )
    write_text(run_dir / "builder-brief.md", render_builder_brief(root, task, contract, run_dir))
    create_checkpoint(root, args.task_id, "run_started", run_dir)
    append_and_maybe_notify_event(root, run_dir, "run_started", {"task_id": args.task_id, "run_id": run_id})
    update_task(root, args.task_id, status="in_progress")
    print(f"Run iniciada para {args.task_id} em {run_dir}")
    print(f"Brief do implementador: {run_dir / 'builder-brief.md'}")


def command_sensors(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "sensors")
    contract = load_contract(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)
    tier = args.tier
    if tier == "quick":
        tier = fastest_available_sensor_tier(contract)
    commands = args.command or sensors_for_tier(contract, tier)
    review_digest = sensor_plan_digest(tier, commands, bool(args.allow_shell))
    contract_review = contract.get("sensor_review") or {}
    reviewed_by_contract = (
        not args.allow_shell
        and review_digest == (contract_review.get("tier_digests") or {}).get(tier)
    )
    reviewed = bool(args.reviewed or reviewed_by_contract)
    if commands and not reviewed:
        raise SystemExit(
            "Execução bloqueada: o plano exato de sensores ainda não foi revisado.\n"
            "Revise os comandos, o tier e o uso de shell. Depois rode novamente com "
            "`sensors --reviewed`, ou recrie o contrato com `--reviewed-sensors`."
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
        "reviewed": reviewed,
        "review_source": "execution" if args.reviewed else "contract",
        "review_digest": review_digest,
        "surface_digest": source_surface_digest(root),
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


def render_evaluator_brief(root: Path, task: dict[str, Any], contract: dict[str, Any], run_dir: Path) -> str:
    sensors = read_json(run_dir / "sensors.json", {"passed": False, "results": []})
    security = read_json(run_dir / "security-scan.json", {})
    ptbr_review = read_json(run_dir / "ptbr-review.json", {})
    preflight = check_context_preflight(root, task["task_id"])
    run_meta = read_json(run_dir / "run.json", {})
    base_commit = run_meta.get("base_commit")
    status = git_output(root, ["status", "--short"]) if is_git_repo(root) else "Nao e um repo git."
    if is_git_repo(root) and base_commit:
        diff = git_output(root, ["diff", "--stat", str(base_commit)])
        changed_files = git_output(root, ["diff", "--name-status", str(base_commit)])
        full_diff_hint = f"Para o diff completo desta run, use `git diff {base_commit}`."
    elif is_git_repo(root):
        diff = git_output(root, ["diff", "--stat"])
        changed_files = git_output(root, ["diff", "--name-status"])
        full_diff_hint = "Para o diff completo, use `git diff`."
    else:
        diff = "Diff git indisponivel."
        changed_files = "Superficie alterada indisponivel."
        full_diff_hint = ""
    write_json(
        run_dir / "changed-surface.json",
        {
            "created_at": utc_now(),
            "base_commit": base_commit,
            "head_commit": git_output(root, ["rev-parse", "HEAD"]) if is_git_repo(root) else None,
            "files": changed_files.splitlines() if changed_files else [],
            "worktree_status": status.splitlines() if status else [],
        },
    )
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
        "## Security scan da run\n\n"
        f"```json\n{json.dumps(security, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Revisão PT-BR\n\n"
        f"```json\n{json.dumps(ptbr_review, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Preflight de contexto\n\n"
        f"```json\n{json.dumps(preflight, indent=2, ensure_ascii=False)}\n```\n\n"
        "## Memoria do projeto\n\n"
        f"{render_memory_context(root, task['task_id'])}\n\n"
        "## Status do Git\n\n"
        f"```text\n{status}\n```\n\n"
        "## Baseline imutável da run\n\n"
        f"Commit inicial: `{base_commit or 'indisponível'}`\n\n"
        "## Superfície alterada desde o início da run\n\n"
        f"```text\n{changed_files}\n```\n\n"
        "## Estatística do diff\n\n"
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
        f"`python {Path(__file__).resolve()} --repo {root} evaluate {task['task_id']} --status <pass|fail> --notes-file <arquivo-com-notas>`\n"
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
        "- Antes de `pass`, registre o security scan e a revisão PT-BR da run.\n"
        "- Se o avaliador retornou PASS e o reviewer não encontrou P0/P1 bloqueante, "
        "registre `evaluate --status pass --review-file reviewer-output.md`.\n"
        "- Inclua nas notas finais o resumo do avaliador e identifique os dois revisores.\n"
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
        if re.search(
            r"\bachados?(?:\s+bloqueantes?)?\s*:\s*nenhum\b"
            r"|\bnenhum\s+(?:achado|finding|p[012])\b"
            r"|\bp[012](?:/p[012])*\s*:\s*nenhum\b",
            line,
            re.IGNORECASE,
        ):
            continue
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
    quick_command = (
        f"python {Path(__file__).resolve()} --repo {root} sensors {task['task_id']} --tier {quick_tier} --reviewed"
    )
    full_command = (
        f"python {Path(__file__).resolve()} --repo {root} sensors {task['task_id']} --tier full --reviewed"
    )
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


def command_fix_brief(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "fix-brief")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "checkpoint create")
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
    print(f"Checkpoint escrito: {path}")


def command_checkpoint_resume_plan(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    plan = render_resume_brief(root, args.task_id, checkpoint)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "artifacts add")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "plugin add")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    plugins = load_plugins(root)
    if not plugins:
        print("Nenhum plugin registrado.")
        return
    for plugin in plugins:
        enabled = "on" if config_bool(plugin.get("enabled"), True) else "off"
        location = plugin.get("path") or plugin.get("command") or "-"
        print(f"{plugin.get('name')} [{enabled}] {location} - {plugin.get('description', '')}")


def command_plugin_set_enabled(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, f"plugin {args.plugin_command}")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    plugins = [
        plugin
        for plugin in load_plugins(root)
        if config_bool(plugin.get("enabled"), True)
        and plugin.get("command")
        and (not plugin.get("events") or args.event in plugin.get("events", []))
    ]
    if not plugins:
        print("Nenhum plugin habilitado para este evento.")
        return
    results = []
    for plugin in plugins:
        command = str(plugin["command"]).format(repo=str(root), task_id=args.task_id or "", event=args.event)
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


def iter_security_scan_files(root: Path, tracked_only: bool = True) -> list[Path]:
    if tracked_only and is_git_repo(root):
        output = git_output(root, ["ls-files"])
        return [root / line.strip() for line in output.splitlines() if line.strip()]
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SECURITY_EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def is_probably_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\0" not in sample


def scan_file_for_secrets(root: Path, path: Path) -> list[dict[str, Any]]:
    if any(part in SECURITY_EXCLUDED_DIRS for part in path.relative_to(root).parts):
        return []
    if not is_probably_text(path):
        return []
    findings = []
    try:
        lines = read_text(path).splitlines()
    except UnicodeDecodeError:
        return []
    for line_number, line in enumerate(lines, start=1):
        for kind, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(0)
            redacted = value[:8] + "..." + value[-4:] if len(value) > 16 else "[redacted]"
            findings.append(
                {
                    "kind": kind,
                    "path": relative_to_root(root, path),
                    "line": line_number,
                    "match": redacted,
                }
            )
    return findings


def command_security_scan(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    run_dir = latest_run_dir(root, args.task_id) if args.task_id else None
    include_untracked = bool(args.include_untracked or args.task_id)
    files = iter_security_scan_files(root, tracked_only=not include_untracked)
    findings: list[dict[str, Any]] = []
    for file in files:
        if file.exists():
            findings.extend(scan_file_for_secrets(root, file))
    report = {
        "created_at": utc_now(),
        "tracked_only": not include_untracked,
        "files_scanned": len(files),
        "findings": findings,
        "task_id": args.task_id,
        "run_id": run_dir.name if run_dir else None,
        "surface_digest": source_surface_digest(root),
    }
    path = security_root(root) / "scan-latest.json"
    write_json(path, report)
    if run_dir:
        write_json(run_dir / "security-scan.json", report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Security scan: {len(findings)} finding(s), {len(files)} arquivo(s).")
        for finding in findings:
            print(f"- {finding['kind']} {finding['path']}:{finding['line']}")
        print(f"Relatorio: {path}")
    if findings and args.fail_on_findings:
        raise SystemExit(1)


def command_ptbr_review(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "ptbr-review")
    find_task(root, args.task_id)
    run_dir = latest_run_dir(root, args.task_id)
    notes = str(args.notes or "").strip()
    if args.status == "pass" and not notes:
        raise SystemExit(
            "Revisão PT-BR bloqueada: registre uma nota curta sobre ortografia, "
            "acentuação e clareza."
        )
    review = {
        "task_id": args.task_id,
        "run_id": run_dir.name,
        "created_at": utc_now(),
        "status": args.status,
        "reviewer": args.reviewer or "não informado",
        "notes": notes,
        "checks": ["ortografia", "acentuação", "clareza"],
        "surface_digest": source_surface_digest(root),
    }
    write_json(run_dir / "ptbr-review.json", review)
    append_and_maybe_notify_event(
        root,
        run_dir,
        "ptbr_review_recorded",
        {"task_id": args.task_id, "status": args.status},
    )
    if args.status == "needs-work":
        update_task(root, args.task_id, status="needs_work")
    print(f"Revisão PT-BR registrada para {args.task_id}: {args.status}")


def command_security_status(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    path = security_root(root) / "scan-latest.json"
    if not path.exists():
        print("Nenhum security scan registrado.")
        return
    report = read_json(path, {})
    print(f"Ultimo scan: {report.get('created_at')}")
    print(f"Findings: {len(report.get('findings') or [])}")


def collect_dashboard_state(root: Path) -> dict[str, Any]:
    config = load_config(root)
    security_report = read_json(security_root(root) / "scan-latest.json", {})
    return {
        "project": config.get("project_name") or root.name,
        "root": str(root),
        "generated_at": utc_now(),
        "active_profile": config.get("active_profile", "balanced"),
        "tasks": load_tasks(root),
        "queue": sorted_queue_items(load_queue(root)),
        "artifacts": collect_run_artifacts(root),
        "memory": load_memory(root),
        "plugins": load_plugins(root),
        "security": security_report,
        "unevaluated_runs": find_unevaluated_runs(root),
    }


def hub_repo_paths(args: argparse.Namespace) -> list[Path]:
    raw_paths = list(getattr(args, "watch_repo", None) or [])
    if not raw_paths:
        raw_paths = [args.repo]
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


def latest_checkpoint_summary(root: Path, task_id: str | None) -> str:
    if not task_id:
        return ""
    path = latest_checkpoint_path(root, task_id)
    if not path:
        return ""
    checkpoint = read_json(path, {})
    return str(checkpoint.get("summary") or checkpoint.get("reason") or checkpoint.get("created_at") or "")


def hub_repo_phase(tasks: list[dict[str, Any]], queue: list[dict[str, Any]], security: dict[str, Any]) -> str:
    if security.get("findings"):
        return "security"
    active = next((item for item in queue if item.get("status") == "active"), None)
    active_task = None
    if active and active.get("task_id"):
        active_task = next((task for task in tasks if task.get("task_id") == active.get("task_id")), None)
    if active_task:
        status = str(active_task.get("status") or "")
        if status in {"in_progress", "needs_work", "sensors_failed"}:
            return "build"
        if status == "sensors_passed":
            return "review"
        if status in {"passed", "done"}:
            return "report"
    if any(task.get("status") in {"in_progress", "needs_work"} for task in tasks):
        return "build"
    if any(task.get("status") == "sensors_passed" for task in tasks):
        return "review"
    if any(item.get("status") == "queued" for item in queue):
        return "queue"
    if any(task.get("status") in {"passed", "done"} for task in tasks):
        return "report"
    return "idle"


def collect_hub_repo_state(root: Path, index: int = 0) -> dict[str, Any]:
    if not root.exists() or not root.is_dir():
        return {
            "index": index,
            "project": root.name,
            "root": str(root),
            "error": "repo_missing",
            "phase": "offline",
            "tasks": [],
            "queue": [],
            "agents": [],
        }
    if not config_path(root).exists():
        return {
            "index": index,
            "project": root.name,
            "root": str(root),
            "error": "harness_not_initialized",
            "phase": "offline",
            "tasks": [],
            "queue": [],
            "agents": [],
        }
    config = load_config(root)
    tasks = load_tasks(root)
    queue = sorted_queue_items(load_queue(root))
    security_report = read_json(security_root(root) / "scan-latest.json", {})
    active = next((item for item in queue if item.get("status") == "active"), None)
    active_task_id = str(active.get("task_id") or "") if active else ""
    active_task = next((task for task in tasks if task.get("task_id") == active_task_id), None)
    if not active_task:
        active_task = next((task for task in tasks if task.get("status") in {"in_progress", "needs_work", "sensors_failed"}), None)
        active_task_id = str(active_task.get("task_id") or "") if active_task else ""
    phase = hub_repo_phase(tasks, queue, security_report)
    latest_run = latest_run_dir_or_none(root, active_task_id) if active_task_id else None
    agents = []
    if active_task_id:
        agents.append(
            {
                "id": f"{index}-builder",
                "name": "Builder",
                "role": "builder",
                "task_id": active_task_id,
                "phase": phase if phase in {"queue", "build", "sensors"} else "build",
            }
        )
    if phase in {"review", "report"}:
        agents.append(
            {
                "id": f"{index}-reviewer",
                "name": "Reviewer",
                "role": "reviewer",
                "task_id": active_task_id,
                "phase": "review",
            }
        )
    if security_report.get("findings"):
        agents.append(
            {
                "id": f"{index}-sentinel",
                "name": "Sentinel",
                "role": "security",
                "task_id": active_task_id,
                "phase": "security",
            }
        )
    if not agents:
        agents.append(
            {
                "id": f"{index}-scout",
                "name": "Scout",
                "role": "observer",
                "task_id": active_task_id,
                "phase": phase,
            }
        )
    return {
        "index": index,
        "project": config.get("project_name") or root.name,
        "root": str(root),
        "branch": current_git_branch(root),
        "phase": phase,
        "active_profile": config.get("active_profile", "balanced"),
        "active_task": active_task,
        "active_queue": active,
        "latest_run": str(latest_run) if latest_run else "",
        "latest_checkpoint": latest_checkpoint_summary(root, active_task_id),
        "counts": {
            "tasks": len(tasks),
            "queued": len([item for item in queue if item.get("status") == "queued"]),
            "active": len([item for item in queue if item.get("status") == "active"]),
            "done": len([item for item in queue if item.get("status") == "done"]),
            "security_findings": len(security_report.get("findings") or []),
            "artifacts": len(collect_run_artifacts(root)),
            "unevaluated_runs": len(find_unevaluated_runs(root)),
        },
        "tasks": tasks[-10:],
        "queue": queue[-10:],
        "security": security_report,
        "agents": agents,
    }


def collect_dashboard_hub_state(paths: list[Path]) -> dict[str, Any]:
    repos = [collect_hub_repo_state(path, index) for index, path in enumerate(paths)]
    return {
        "generated_at": utc_now(),
        "repo_count": len(repos),
        "active_repos": len([repo for repo in repos if repo.get("phase") not in {"idle", "offline"}]),
        "total_tasks": sum(int(repo.get("counts", {}).get("tasks") or 0) for repo in repos),
        "total_findings": sum(int(repo.get("counts", {}).get("security_findings") or 0) for repo in repos),
        "repos": repos,
    }


def render_dashboard_hub_html(state: dict[str, Any], refresh_seconds: int = 3) -> str:
    initial_state = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harness Hub</title>
  <style>
    :root {{
      color-scheme: dark;
      --stone-0: #0b0908;
      --stone-1: #15100d;
      --stone-2: #241a14;
      --stone-3: #3b2a1e;
      --stone-4: #68462e;
      --wood-1: #3a2113;
      --wood-2: #6f4328;
      --brass: #c28b43;
      --blue: #21a7ff;
      --green: #4ade80;
      --red: #ff5b5b;
      --amber: #f6b74a;
      --violet: #a987ff;
      --ink: #f3ead7;
      --muted: #b59f7b;
      font-family: "Trebuchet MS", Arial, sans-serif;
      image-rendering: pixelated;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
        var(--stone-0);
      background-size: 16px 16px;
      color: var(--ink);
      letter-spacing: 0;
      overflow-x: hidden;
    }}
    header {{
      min-height: 72px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      border-bottom: 4px solid #070504;
      background: var(--stone-2);
      box-shadow: inset 0 -4px 0 var(--stone-4);
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.1;
      text-transform: uppercase;
    }}
    .subhead {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }}
    .hud {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .chip {{
      border: 2px solid var(--stone-4);
      background: #120d0a;
      color: var(--ink);
      min-height: 34px;
      padding: 7px 10px;
      box-shadow: inset -2px -2px 0 #050403, inset 2px 2px 0 #3b2a1e;
      font-size: 12px;
    }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      min-height: calc(100vh - 72px);
    }}
    .world-wrap {{
      padding: 18px;
      overflow: auto;
      background:
        radial-gradient(circle at 50% 50%, rgba(33,167,255,.08), transparent 34%),
        #050403;
    }}
    .world {{
      position: relative;
      min-width: 1040px;
      min-height: 680px;
      border: 8px solid #070504;
      background:
        linear-gradient(90deg, rgba(0,0,0,.18) 1px, transparent 1px),
        linear-gradient(rgba(0,0,0,.18) 1px, transparent 1px),
        var(--wood-1);
      background-size: 24px 24px;
      box-shadow: inset 0 0 0 5px var(--stone-4), 0 0 0 4px #000;
    }}
    .hall {{
      position: absolute;
      left: 31%;
      top: 14%;
      width: 38%;
      height: 72%;
      border: 6px solid var(--stone-4);
      background:
        linear-gradient(90deg, rgba(246,183,74,.14) 2px, transparent 2px),
        linear-gradient(rgba(246,183,74,.08) 2px, transparent 2px),
        #2b1a10;
      background-size: 34px 34px;
      box-shadow: inset 0 0 0 4px #120d0a;
    }}
    .core {{
      position: absolute;
      left: 50%;
      top: 50%;
      width: 112px;
      height: 112px;
      transform: translate(-50%, -50%);
      border: 5px solid var(--brass);
      background: #09131b;
      box-shadow: inset 0 0 0 8px #12304a, 0 0 24px rgba(33,167,255,.45);
    }}
    .core::before {{
      content: "";
      position: absolute;
      left: 29px;
      top: 29px;
      width: 44px;
      height: 44px;
      border: 4px solid var(--blue);
      background: #064c7a;
      animation: pulse 1.8s steps(4) infinite;
    }}
    .room {{
      position: absolute;
      width: 300px;
      height: 210px;
      border: 7px solid #1b100a;
      background:
        linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
        var(--stone-2);
      background-size: 18px 18px;
      box-shadow:
        inset 0 0 0 4px var(--stone-4),
        inset 0 -10px 0 rgba(0,0,0,.22),
        0 0 0 4px #070504;
      cursor: pointer;
    }}
    .room[data-phase="build"] {{ --phase: var(--blue); }}
    .room[data-phase="queue"] {{ --phase: var(--amber); }}
    .room[data-phase="review"] {{ --phase: var(--violet); }}
    .room[data-phase="security"] {{ --phase: var(--red); }}
    .room[data-phase="report"] {{ --phase: var(--green); }}
    .room[data-phase="idle"] {{ --phase: var(--muted); }}
    .room[data-phase="offline"] {{ --phase: #666; }}
    .room::before {{
      content: "";
      position: absolute;
      inset: 10px;
      border: 3px solid var(--phase, var(--muted));
      opacity: .75;
      pointer-events: none;
    }}
    .room-title {{
      position: absolute;
      left: 17px;
      top: 14px;
      right: 17px;
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .room-meta {{
      position: absolute;
      left: 18px;
      top: 36px;
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      right: 18px;
    }}
    .console {{
      position: absolute;
      left: 22px;
      bottom: 24px;
      width: 108px;
      height: 58px;
      background: #130f0c;
      border: 4px solid var(--wood-2);
      box-shadow: inset 0 0 0 3px #050403;
    }}
    .console::before {{
      content: "";
      position: absolute;
      left: 12px;
      top: 10px;
      width: 72px;
      height: 18px;
      background: var(--phase, var(--blue));
      box-shadow: 0 28px 0 #2d1d12;
      opacity: .9;
    }}
    .station {{
      position: absolute;
      right: 26px;
      bottom: 28px;
      width: 92px;
      height: 72px;
      border: 4px solid var(--brass);
      background: #0a1116;
      box-shadow: inset 0 0 0 5px #172a37;
    }}
    .station::before {{
      content: "";
      position: absolute;
      left: 25px;
      top: 18px;
      width: 32px;
      height: 32px;
      background: var(--phase, var(--blue));
      box-shadow: 0 0 16px var(--phase, var(--blue));
      animation: pulse 2.4s steps(4) infinite;
    }}
    .metric-line {{
      position: absolute;
      left: 18px;
      right: 18px;
      bottom: 100px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .mini {{
      min-width: 48px;
      padding: 5px 6px;
      border: 2px solid #4b3321;
      background: #0f0b09;
      font-size: 10px;
      color: var(--ink);
    }}
    .agent {{
      position: absolute;
      width: 18px;
      height: 18px;
      background: var(--phase, var(--blue));
      border: 3px solid #071018;
      box-shadow: 0 0 0 2px rgba(255,255,255,.22), 0 0 14px var(--phase, var(--blue));
      animation: patrol 3.2s steps(6) infinite;
      z-index: 3;
    }}
    .agent::before {{
      content: "";
      position: absolute;
      left: 4px;
      top: -8px;
      width: 8px;
      height: 5px;
      background: #f2d7a5;
      border: 2px solid #071018;
    }}
    .agent[data-role="reviewer"] {{ animation-duration: 4.2s; }}
    .agent[data-role="security"] {{ animation-duration: 2.5s; }}
    .path {{
      position: absolute;
      height: 6px;
      background: rgba(194,139,67,.45);
      box-shadow: 0 0 0 2px rgba(20,12,8,.8);
      transform-origin: left center;
    }}
    aside {{
      border-left: 5px solid #070504;
      background: #100c0a;
      min-width: 0;
      padding: 16px;
      overflow: auto;
    }}
    .panel {{
      border: 4px solid var(--stone-4);
      background: #18110d;
      padding: 14px;
      box-shadow: inset -3px -3px 0 #080504, inset 3px 3px 0 #3b2a1e;
      margin-bottom: 14px;
    }}
    h2 {{
      margin: 0 0 10px;
      font-size: 15px;
      text-transform: uppercase;
    }}
    .repo-list {{
      display: grid;
      gap: 8px;
    }}
    button.repo-button {{
      width: 100%;
      min-height: 44px;
      text-align: left;
      border: 3px solid var(--stone-4);
      background: #0d0907;
      color: var(--ink);
      padding: 8px;
      cursor: pointer;
      font: inherit;
      box-shadow: inset -2px -2px 0 #050403;
    }}
    button.repo-button:focus {{
      outline: 3px solid var(--blue);
      outline-offset: 2px;
    }}
    .detail {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .task-list {{
      margin: 8px 0 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 7px;
    }}
    .task-list li {{
      border-left: 4px solid var(--brass);
      padding-left: 8px;
      color: var(--ink);
      font-size: 12px;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: .7; transform: scale(1); }}
      50% {{ opacity: 1; transform: scale(1.14); }}
    }}
    @keyframes patrol {{
      0% {{ transform: translate(0, 0); }}
      25% {{ transform: translate(24px, 0); }}
      50% {{ transform: translate(24px, 24px); }}
      75% {{ transform: translate(0, 24px); }}
      100% {{ transform: translate(0, 0); }}
    }}
    @media (max-width: 900px) {{
      .shell {{ grid-template-columns: 1fr; }}
      aside {{ border-left: 0; border-top: 5px solid #070504; }}
      .world {{ min-width: 760px; min-height: 620px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Harness Hub</h1>
      <div class="subhead" id="generated">Mapa operacional local</div>
    </div>
    <div class="hud" aria-label="Resumo do hub">
      <div class="chip" id="repoCount">Repos: 0</div>
      <div class="chip" id="activeCount">Ativos: 0</div>
      <div class="chip" id="taskCount">Tasks: 0</div>
      <div class="chip" id="findingCount">Findings: 0</div>
    </div>
  </header>
  <div class="shell">
    <main class="world-wrap" aria-label="Mapa pixelado do Harness">
      <div class="world" id="world">
        <div class="hall"></div>
        <div class="core" title="Hub core"></div>
      </div>
    </main>
    <aside>
      <section class="panel">
        <h2>Projetos</h2>
        <div class="repo-list" id="repoList"></div>
      </section>
      <section class="panel">
        <h2>Inspecao</h2>
        <div class="detail" id="detail">Selecione uma sala no mapa.</div>
      </section>
    </aside>
  </div>
  <script>
    const initialState = {initial_state};
    const refreshMs = {max(refresh_seconds, 1) * 1000};
    let hubState = initialState;
    let selectedIndex = 0;
    const roomSlots = [
      [32, 36], [708, 36], [32, 418], [708, 418],
      [370, 36], [370, 418], [32, 226], [708, 226]
    ];
    const phaseLabels = {{
      queue: "Fila", build: "Implementacao", review: "Revisao",
      security: "Security", report: "Relatorio", idle: "Ocioso", offline: "Offline"
    }};
    function esc(value) {{
      return String(value ?? "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }}[char]));
    }}
    function roomPosition(index) {{
      if (index < roomSlots.length) return roomSlots[index];
      const col = index % 3;
      const row = Math.floor(index / 3);
      return [32 + col * 338, 650 + row * 240];
    }}
    function render() {{
      document.getElementById("generated").textContent = "Atualizado " + (hubState.generated_at || "-");
      document.getElementById("repoCount").textContent = "Repos: " + (hubState.repo_count || 0);
      document.getElementById("activeCount").textContent = "Ativos: " + (hubState.active_repos || 0);
      document.getElementById("taskCount").textContent = "Tasks: " + (hubState.total_tasks || 0);
      document.getElementById("findingCount").textContent = "Findings: " + (hubState.total_findings || 0);
      const world = document.getElementById("world");
      world.querySelectorAll(".room,.path").forEach(node => node.remove());
      const repos = hubState.repos || [];
      const maxY = repos.reduce((max, repo, index) => Math.max(max, roomPosition(index)[1] + 250), 680);
      world.style.minHeight = maxY + "px";
      repos.forEach((repo, index) => {{
        const [left, top] = roomPosition(index);
        const room = document.createElement("section");
        room.className = "room";
        room.dataset.phase = repo.phase || "idle";
        room.style.left = left + "px";
        room.style.top = top + "px";
        room.tabIndex = 0;
        room.setAttribute("role", "button");
        room.setAttribute("aria-label", "Abrir " + (repo.project || repo.root));
        room.innerHTML = `
          <div class="room-title">${{esc(repo.project || "Projeto")}}</div>
          <div class="room-meta">${{esc(phaseLabels[repo.phase] || repo.phase)}} · ${{esc(repo.branch || "sem branch")}}</div>
          <div class="metric-line">
            <div class="mini">T ${{esc(repo.counts?.tasks ?? 0)}}</div>
            <div class="mini">Q ${{esc(repo.counts?.queued ?? 0)}}</div>
            <div class="mini">A ${{esc(repo.counts?.artifacts ?? 0)}}</div>
            <div class="mini">S ${{esc(repo.counts?.security_findings ?? 0)}}</div>
          </div>
          <div class="console"></div>
          <div class="station"></div>
        `;
        (repo.agents || []).slice(0, 4).forEach((agent, agentIndex) => {{
          const sprite = document.createElement("div");
          sprite.className = "agent";
          sprite.dataset.role = agent.role || "observer";
          sprite.title = (agent.name || "Agent") + " · " + (agent.task_id || "");
          sprite.style.left = 148 + agentIndex * 22 + "px";
          sprite.style.top = 86 + (agentIndex % 2) * 28 + "px";
          sprite.style.animationDelay = (agentIndex * -0.55) + "s";
          room.appendChild(sprite);
        }});
        room.addEventListener("click", () => {{ selectedIndex = index; renderDetail(); }});
        room.addEventListener("keydown", event => {{
          if (event.key === "Enter" || event.key === " ") {{
            event.preventDefault();
            selectedIndex = index;
            renderDetail();
          }}
        }});
        world.appendChild(room);
      }});
      renderRepoList();
      renderDetail();
    }}
    function renderRepoList() {{
      const list = document.getElementById("repoList");
      list.innerHTML = "";
      (hubState.repos || []).forEach((repo, index) => {{
        const button = document.createElement("button");
        button.className = "repo-button";
        button.innerHTML = `<strong>${{esc(repo.project || repo.root)}}</strong><br><span class="detail">${{esc(phaseLabels[repo.phase] || repo.phase)}} · ${{esc(repo.root)}}</span>`;
        button.addEventListener("click", () => {{ selectedIndex = index; renderDetail(); }});
        list.appendChild(button);
      }});
    }}
    function renderDetail() {{
      const repo = (hubState.repos || [])[selectedIndex];
      const detail = document.getElementById("detail");
      if (!repo) {{
        detail.textContent = "Nenhum repo carregado.";
        return;
      }}
      const activeTask = repo.active_task || {{}};
      const queue = repo.queue || [];
      const tasks = repo.tasks || [];
      detail.innerHTML = `
        <strong>${{esc(repo.project)}}</strong><br>
        Fase: ${{esc(phaseLabels[repo.phase] || repo.phase)}}<br>
        Raiz: ${{esc(repo.root)}}<br>
        Branch: ${{esc(repo.branch || "-")}}<br>
        Profile: ${{esc(repo.active_profile || "-")}}<br>
        Task ativa: ${{esc(activeTask.task_id || "-")}} ${{esc(activeTask.title || "")}}<br>
        Run: ${{esc(repo.latest_run || "-")}}<br>
        Checkpoint: ${{esc(repo.latest_checkpoint || "-")}}<br>
        Security findings: ${{esc(repo.counts?.security_findings ?? 0)}}<br>
        <br><strong>Fila</strong>
        <ul class="task-list">${{queue.slice(-5).map(item => `<li>${{esc(item.id)}} [${{esc(item.status)}}] ${{esc(item.title)}}</li>`).join("") || "<li>Fila vazia.</li>"}}</ul>
        <br><strong>Tasks recentes</strong>
        <ul class="task-list">${{tasks.slice(-5).map(task => `<li>${{esc(task.task_id)}} [${{esc(task.status)}}] ${{esc(task.title)}}</li>`).join("") || "<li>Nenhuma task.</li>"}}</ul>
      `;
    }}
    async function refresh() {{
      try {{
        const response = await fetch("hub-state.json?ts=" + Date.now(), {{ cache: "no-store" }});
        if (!response.ok) return;
        hubState = await response.json();
        render();
      }} catch (error) {{
        console.warn("Hub refresh failed", error);
      }}
    }}
    render();
    setInterval(refresh, refreshMs);
  </script>
</body>
</html>
"""


def write_dashboard_hub(root: Path, paths: list[Path], refresh_seconds: int = 3) -> dict[str, Any]:
    state = collect_dashboard_hub_state(paths)
    target = dashboard_hub_root(root)
    write_text(target / "index.html", render_dashboard_hub_html(state, refresh_seconds))
    write_json(target / "hub-state.json", state)
    return {"state": state, "path": target / "index.html", "state_path": target / "hub-state.json"}


def render_dashboard_html(root: Path, state: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    task_rows = "\n".join(
        f"<tr><td>{esc(task.get('task_id'))}</td><td>{esc(task.get('status'))}</td><td>{esc(task.get('title'))}</td></tr>"
        for task in state["tasks"]
    ) or "<tr><td colspan='3'>Nenhuma task.</td></tr>"
    queue_rows = "\n".join(
        f"<tr><td>{esc(item.get('id'))}</td><td>{esc(item.get('status'))}</td><td>{esc(item.get('title'))}</td></tr>"
        for item in state["queue"]
    ) or "<tr><td colspan='3'>Fila vazia.</td></tr>"
    artifact_rows = "\n".join(
        f"<tr><td>{esc(item.get('task_id'))}</td><td>{esc(item.get('label'))}</td><td>{esc(item.get('path'))}</td></tr>"
        for item in state["artifacts"][:80]
    ) or "<tr><td colspan='3'>Nenhum artifact.</td></tr>"
    memory_items = "\n".join(
        f"<li>{esc(item.get('text'))}</li>" for item in state["memory"][-12:]
    ) or "<li>Nenhuma memoria registrada.</li>"
    plugins = "\n".join(
        f"<li>{esc(plugin.get('name'))} - {esc(plugin.get('description'))}</li>" for plugin in state["plugins"]
    ) or "<li>Nenhum plugin registrado.</li>"
    security_count = len(state.get("security", {}).get("findings") or [])
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harness Dashboard - {esc(state['project'])}</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #1f2933; }}
    header {{ background: #16213a; color: white; padding: 24px 32px; }}
    main {{ padding: 24px 32px; display: grid; gap: 20px; }}
    section {{ background: white; border: 1px solid #d8dee8; border-radius: 8px; padding: 18px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e5e9f0; padding: 8px; text-align: left; vertical-align: top; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
    .metric {{ font-size: 24px; font-weight: 700; }}
  </style>
</head>
<body>
  <header>
    <h1>Harness Dashboard</h1>
    <div>{esc(state['project'])} - {esc(state['generated_at'])} - profile {esc(state['active_profile'])}</div>
  </header>
  <main>
    <div class="grid">
      <section><h2>Tasks</h2><div class="metric">{len(state['tasks'])}</div></section>
      <section><h2>Fila</h2><div class="metric">{len(state['queue'])}</div></section>
      <section><h2>Security</h2><div class="metric">{security_count} finding(s)</div></section>
    </div>
    <section><h2>Tasks</h2><table><tbody>{task_rows}</tbody></table></section>
    <section><h2>Fila</h2><table><tbody>{queue_rows}</tbody></table></section>
    <section><h2>Artifacts</h2><table><tbody>{artifact_rows}</tbody></table></section>
    <div class="grid">
      <section><h2>Memoria</h2><ul>{memory_items}</ul></section>
      <section><h2>Plugins</h2><ul>{plugins}</ul></section>
    </div>
  </main>
</body>
</html>
"""


def command_dashboard_html(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    state = collect_dashboard_state(root)
    path = dashboard_root(root) / "index.html"
    write_text(path, render_dashboard_html(root, state))
    write_json(dashboard_root(root) / "state.json", state)
    print(f"Dashboard HTML: {path}")


def command_dashboard_hub(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    paths = hub_repo_paths(args)
    result = write_dashboard_hub(root, paths, args.refresh_seconds)
    print(f"Harness Hub: {result['path']}")
    print(f"Repos monitorados: {len(result['state']['repos'])}")
    for repo in result["state"]["repos"]:
        suffix = f" ({repo.get('error')})" if repo.get("error") else ""
        print(f"- {repo.get('project')} [{repo.get('phase')}]{suffix}: {repo.get('root')}")


def command_dashboard_hub_state(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    paths = hub_repo_paths(args)
    state = collect_dashboard_hub_state(paths)
    path = dashboard_hub_root(root) / "hub-state.json"
    write_json(path, state)
    print(json.dumps(state, indent=2, ensure_ascii=False) if args.json else f"Hub state: {path}")


def command_dashboard_hub_serve(args: argparse.Namespace) -> None:
    import functools
    import http.server

    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    paths = hub_repo_paths(args)
    write_dashboard_hub(root, paths, args.refresh_seconds)
    directory = dashboard_hub_root(root)

    class HubHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib hook
            request_path = urllib.parse.urlparse(self.path).path
            if request_path in {"/hub-state.json", "/state.json"}:
                state = collect_dashboard_hub_state(paths)
                body = json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8")
                write_json(directory / "hub-state.json", state)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

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

    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    if status in {"planned", "contracted"}:
        return f"Iniciar: python {Path(__file__).resolve()} --repo {root} start {task_id}"
    if status in {"in_progress", "sensors_failed", "needs_work"}:
        contract = load_contract(root, task_id)
        tier = fastest_available_sensor_tier(contract)
        return f"Rodar sensores: python {Path(__file__).resolve()} --repo {root} sensors {task_id} --tier {tier} --reviewed"
    if status == "sensors_passed":
        run_dir = latest_run_dir_or_none(root, task_id)
        if run_dir and not (run_dir / "security-scan.json").exists():
            return (
                "Rodar security scan: "
                f"python {Path(__file__).resolve()} --repo {root} security scan "
                f"--task-id {task_id} --fail-on-findings"
            )
        ptbr_review = read_json(run_dir / "ptbr-review.json", {}) if run_dir else {}
        if ptbr_review.get("status") != "pass":
            return (
                "Revisar PT-BR: "
                f"python {Path(__file__).resolve()} --repo {root} ptbr-review "
                f"{task_id} --status pass --notes \"Ortografia, acentuação e clareza conferidas.\""
            )
        return f"Avaliar: python {Path(__file__).resolve()} --repo {root} evaluate {task_id}"
    if status in {"passed", "done"}:
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    state = read_json(supervisor_state_path(root), {})
    counts = queue_counts(root)
    print("Supervisor:")
    print(f"- ultimo tick: {state.get('updated_at') or 'nenhum'}")
    print(f"- fila: {counts}")
    if state.get("recommendation"):
        print(f"- recomendacao: {state['recommendation']}")


def command_supervisor_tick(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "supervisor tick")
    payload = supervisor_tick(root, args)
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else payload["recommendation"])


def command_supervisor_run(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "supervisor run")
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


def render_github_pr_body(root: Path, task_id: str) -> str:
    task = find_task(root, task_id)
    report_path = harness_root(root) / "reports" / f"{task_id}.md"
    run_dir = latest_run_dir_or_none(root, task_id)
    plain = read_text(run_dir / "plain-summary.md") if run_dir and (run_dir / "plain-summary.md").exists() else ""
    report = read_text(report_path) if report_path.exists() else ""
    sensors = read_json(run_dir / "sensors.json", {}) if run_dir else {}
    security = read_json(run_dir / "security-scan.json", {}) if run_dir else {}
    ptbr_review = read_json(run_dir / "ptbr-review.json", {}) if run_dir else {}
    evaluation = read_json(run_dir / "evaluation.json", {}) if run_dir else {}
    simple_summary = render_plain_summary_for_message(plain) if plain else ""
    if not simple_summary:
        simple_summary = f"Foi trabalhada a tarefa \"{plain_clean(task.get('title'))}\"."
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
    security_line = f"{len(security.get('findings') or [])} achado(s)" if security else "não executado"
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
        f"- Relatório: `{to_posix(report_path.relative_to(root)) if report_path.exists() else 'pendente'}`\n\n"
        "## Relatório completo\n\n"
        f"{report or 'Relatório ainda não gerado.'}\n"
    )


def command_github_configure(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "github configure")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    gconfig = github_config(load_config(root))
    print(f"repo: {gconfig.get('repo') or 'nao configurado'}")
    print(f"remote: {gconfig.get('remote')}")
    print(f"base: {gconfig.get('default_base')}")
    print(f"gh CLI: {shutil.which('gh') or 'nao encontrado'}")


def command_github_pr_body(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    body = render_github_pr_body(root, args.task_id)
    path = Path(args.out).expanduser().resolve() if args.out else github_root(root) / f"{args.task_id}-pr-body.md"
    assert_inside_root(root, path, label="github pr-body out")
    write_text(path, body)
    print(body if args.print else f"PR body escrito: {path}")


def command_github_pr_create(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "github pr-create")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "github issue-import")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    config = load_config(root)
    print(
        json.dumps(
            {
                "completion_policy": config.get("policy", {}),
                "failure_policy": failure_policy(config),
                "review_policy": review_policy(config),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def command_policy_set(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "policy set")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "failure apply")
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


def collect_code_review(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    parts: list[str] = []
    for raw_path in getattr(args, "review_file", None) or []:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"Arquivo de review não encontrado: {path}")
        parts.append(read_text(path))
    parts.extend(getattr(args, "review_note", None) or [])
    text = "\n\n".join(part.strip() for part in parts if part.strip())
    blockers = blocking_findings_from_review(text, config) if text else []
    return {
        "created_at": utc_now(),
        "reviewer": getattr(args, "reviewer", None) or "não informado",
        "text": text,
        "findings": extract_review_findings(text) if text else [],
        "blocking_findings": blockers,
        "passed": bool(text) and not blockers,
    }


def parse_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def completion_gate_failures(
    root: Path,
    task: dict[str, Any],
    contract: dict[str, Any],
    run_dir: Path,
    config: dict[str, Any],
    evaluation_notes: str,
    code_review: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    policy = config.get("policy", {})
    run_meta = read_json(run_dir / "run.json", {})
    budget = dict(run_meta.get("budget") or task_budget(task, config))
    current_surface = source_surface_digest(root)

    if config_bool(policy.get("record_evidence_before_done"), True):
        sensors_payload = final_sensor_payload(run_dir, contract)
        if not sensors_payload:
            failures.append("não há evidência de sensores finais nesta run")
        elif not sensors_payload.get("passed"):
            failures.append("os sensores finais registrados não passaram")
        elif not sensors_payload.get("reviewed") or not sensors_payload.get("review_digest"):
            failures.append("o plano exato de sensores não tem revisão registrada")
        elif sensors_payload.get("surface_digest") != current_surface:
            failures.append("o código mudou depois da execução dos sensores finais")

    if config_bool(policy.get("context_preflight_required_before_start"), True):
        preflight = check_context_preflight(root, task["task_id"])
        if not preflight.get("passed"):
            failures.append("o preflight de contexto atual não passou")

    security_required = config_bool(
        policy.get("security_scan_required_before_done"), True
    ) and config_bool(budget.get("security_scan_required"), True)
    if security_required:
        security = read_json(run_dir / "security-scan.json", {})
        if not security:
            failures.append("falta um security scan desta run")
        elif security.get("run_id") != run_dir.name:
            failures.append("o security scan não pertence à run atual")
        elif security.get("findings"):
            failures.append(
                f"o security scan tem {len(security.get('findings') or [])} achado(s)"
            )
        elif security.get("surface_digest") != current_surface:
            failures.append("o código mudou depois do security scan")

    ptbr_required = config_bool(
        policy.get("ptbr_review_required_before_done"), True
    ) and config_bool(budget.get("ptbr_review_required"), True)
    if ptbr_required:
        ptbr_review = read_json(run_dir / "ptbr-review.json", {})
        if not ptbr_review:
            failures.append("falta a revisão de ortografia e clareza em PT-BR")
        elif ptbr_review.get("status") != "pass":
            failures.append("a revisão PT-BR ainda pede ajustes")
        elif not str(ptbr_review.get("notes") or "").strip():
            failures.append("a revisão PT-BR não contém uma nota de evidência")
        elif ptbr_review.get("surface_digest") != current_surface:
            failures.append("os arquivos mudaram depois da revisão PT-BR")

    reviewer_required = config_bool(
        policy.get("review_evidence_required_before_done"), True
    ) and config_bool(review_policy(config).get("enabled"), True)
    if reviewer_required:
        if not code_review.get("text"):
            failures.append("falta o parecer do code reviewer")
        elif code_review.get("blocking_findings"):
            severities = ", ".join(
                sorted(
                    {
                        str(item.get("severity"))
                        for item in code_review.get("blocking_findings") or []
                    }
                )
            )
            failures.append(f"o code reviewer registrou achado(s) bloqueante(s): {severities}")
        elif code_review.get("surface_digest") != current_surface:
            failures.append("o código mudou depois do parecer do code reviewer")

    if not evaluation_notes.strip():
        failures.append("falta uma nota curta com a decisão do avaliador")

    if config_bool(policy.get("budget_required_before_done"), True):
        started_at = parse_utc_datetime(run_meta.get("created_at"))
        time_limit = budget.get("time_budget_minutes") or budget.get("timeout_minutes")
        if started_at and time_limit:
            elapsed_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
            if elapsed_minutes > float(time_limit):
                failures.append(
                    f"o orçamento de tempo foi excedido ({elapsed_minutes:.1f}/{time_limit} min)"
                )
        max_fix_attempts = budget.get("max_fix_attempts")
        fix_attempts = len(list(run_dir.glob("fix-brief-[0-9][0-9].md")))
        if max_fix_attempts is not None and fix_attempts > int(max_fix_attempts):
            failures.append(
                f"o limite de correções foi excedido ({fix_attempts}/{max_fix_attempts})"
            )

    return failures


def command_evaluate(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "evaluate")
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

    code_review = collect_code_review(args, config)
    if code_review.get("text"):
        code_review.update(
            {
                "task_id": args.task_id,
                "run_id": run_dir.name,
                "surface_digest": source_surface_digest(root),
            }
        )
        write_json(run_dir / "code-review.json", code_review)

    if args.status == "pass":
        effective_review = (
            code_review
            if code_review.get("text")
            else read_json(run_dir / "code-review.json", {})
        )
        failures = completion_gate_failures(
            root,
            task,
            contract,
            run_dir,
            config,
            notes,
            effective_review,
        )
        if failures:
            details = "\n".join(f"- {failure}" for failure in failures)
            raise SystemExit(
                "Avaliação `pass` bloqueada pelos gates de conclusão:\n"
                f"{details}\n\n"
                "Registre somente as evidências que realmente foram conferidas e tente novamente."
            )

    evaluation = {
        "task_id": args.task_id,
        "run_dir": str(run_dir),
        "created_at": utc_now(),
        "status": args.status,
        "notes": notes,
        "gaps": args.gap or [],
        "evaluator": getattr(args, "evaluator", None) or "não informado",
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


def command_report(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "report")
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "telegram configure")
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
    print(f"- midia via OpenAI: {str(config_bool(tconfig.get('openai_media', {}).get('enabled'), False)).lower()}")


def command_telegram_send(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    print(f"- download de midia: {str(config_bool(tconfig.get('download_media'), True)).lower()}")
    print(f"- midia via OpenAI: {str(config_bool(tconfig.get('openai_media', {}).get('enabled'), False)).lower()}")


def command_telegram_listen(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "telegram listen")
    config = load_config(root)
    token = telegram_token(config)
    if not token:
        raise SystemExit(
            "Token do Telegram nao encontrado. Configure a variavel de ambiente "
            f"{telegram_config(config).get('token_env')}."
        )
    state = read_json(telegram_state_path(root), {})
    offset = state.get("offset")
    print("Ouvindo Telegram. Ctrl+C para parar.")
    while True:
        payload = {
            "timeout": args.timeout,
            "limit": args.limit,
            "allowed_updates": ["message", "edited_message"],
        }
        if offset:
            payload["offset"] = offset
        updates = telegram_api_call(token, "getUpdates", payload, timeout=args.timeout + 15)
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id", 0))
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
            offset = max(offset or 0, update_id + 1)
            write_json(telegram_state_path(root), {"offset": offset, "updated_at": utc_now()})
        if args.once:
            if not processed:
                print("Nenhuma mensagem nova.")
            return


def command_telegram_codex(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "telegram codex")
    config = load_config(root)
    token = telegram_token(config)
    if not token:
        raise SystemExit(
            "Token do Telegram nao encontrado. Configure a variavel de ambiente "
            f"{telegram_config(config).get('token_env')}."
        )
    codex_executable()
    state_path = telegram_root(root) / "codex-state.json"
    state = read_json(state_path, {})
    offset = state.get("offset")
    print("Gateway Telegram -> Codex ativo. Ctrl+C para parar.")
    while True:
        payload = {
            "timeout": args.poll_timeout,
            "limit": args.limit,
            "allowed_updates": ["message", "edited_message"],
        }
        if offset:
            payload["offset"] = offset
        updates = telegram_api_call(token, "getUpdates", payload, timeout=args.poll_timeout + 15)
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id", 0))
            message = update.get("message") or update.get("edited_message") or {}
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = str(message.get("text") or "")
            if not telegram_chat_allowed(config, chat_id):
                handle_telegram_update(root, config, update, reply=False)
                offset = max(offset or 0, update_id + 1)
                continue

            stripped = text.strip()
            if stripped.startswith("/") and not stripped.lower().startswith("/codex"):
                path = handle_telegram_update(
                    root,
                    config,
                    update,
                    create_tasks=False,
                    download_media=not args.no_download_media,
                    reply=not args.no_reply,
                )
                if path:
                    processed += 1
                    print(f"Comando Harness via Telegram: {path}")
                offset = max(offset or 0, update_id + 1)
                write_json(state_path, {"offset": offset, "updated_at": utc_now()})
                continue

            path = handle_telegram_update(
                root,
                config,
                update,
                create_tasks=False,
                download_media=not args.no_download_media,
                reply=False,
            )
            if not path:
                offset = max(offset or 0, update_id + 1)
                continue
            item = read_json(path, {})
            if item.get("action") == "rejected_chat":
                offset = max(offset or 0, update_id + 1)
                continue

            prompt_text = item.get("prompt_text") or ""
            if stripped.lower().startswith("/codex"):
                prompt_text = stripped.partition(" ")[2].strip() or prompt_text
            if not args.no_reply:
                telegram_reply(config, chat_id, "Recebido. Vou mandar isso para o Codex agora.")
            try:
                result = run_codex_for_telegram(
                    root,
                    item,
                    prompt_text=prompt_text,
                    resume_last=bool(args.resume_last),
                    session_id=args.session_id,
                    model=args.model,
                    sandbox=args.sandbox,
                    approval=args.approval,
                    bypass=bool(args.bypass),
                    timeout=args.codex_timeout,
                )
                item["action"] = "codex_completed"
                item["codex"] = {
                    "run_id": result["run_id"],
                    "exit_code": result["exit_code"],
                    "duration_ms": result["duration_ms"],
                    "output_path": result["output_path"],
                }
                write_json(path, item)
                response = result.get("response") or "Codex terminou sem mensagem final."
                if result.get("exit_code") != 0:
                    response = (
                        f"Codex terminou com erro {result.get('exit_code')}.\n"
                        f"Veja: {result.get('stderr_path')}\n\n"
                        f"{response}"
                    )
                if not args.no_reply:
                    telegram_reply(config, chat_id, response)
                print(f"Codex respondeu para {path}: {result['run_id']}")
            except subprocess.TimeoutExpired:
                item["action"] = "codex_timeout"
                write_json(path, item)
                if not args.no_reply:
                    telegram_reply(config, chat_id, "Codex demorou demais e foi interrompido por timeout.")
            except Exception as exc:
                item["action"] = "codex_failed"
                item["error"] = str(exc)
                write_json(path, item)
                if not args.no_reply:
                    telegram_reply(config, chat_id, f"Falha ao chamar Codex: {exc}")
            processed += 1
            offset = max(offset or 0, update_id + 1)
            write_json(state_path, {"offset": offset, "updated_at": utc_now()})
        if args.once:
            if not processed:
                print("Nenhuma mensagem nova.")
            return


def command_telegram_mirror(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    config = load_config(root)
    if not telegram_token(config):
        raise SystemExit(
            "Token do Telegram nao encontrado. Configure a variavel de ambiente "
            f"{telegram_config(config).get('token_env')}."
        )
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
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    require_safe_branch(root, args, "telegram bridge")
    config = load_config(root)
    token = telegram_token(config)
    if not token:
        raise SystemExit(
            "Token do Telegram nao encontrado. Configure a variavel de ambiente "
            f"{telegram_config(config).get('token_env')}."
        )
    if args.send_mode == "codex-exec":
        codex_executable()

    session_path = Path(args.session_file).expanduser().resolve() if args.session_file else latest_codex_session_file()
    mirror_offset = read_mirror_state(root, session_path, from_end=not args.from_start)
    bridge_state_path = telegram_root(root) / "bridge-state.json"
    bridge_state = read_json(bridge_state_path, {})
    update_offset = bridge_state.get("telegram_offset")
    targets = [str(item) for item in args.chat_id] if args.chat_id else [str(item) for item in telegram_config(config).get("chat_ids", [])]
    if not targets:
        raise SystemExit("Nenhum chat configurado. Use telegram configure --chat-id ou telegram bridge --chat-id.")

    print(f"Bridge ativo. Espelhando: {session_path}")
    print(f"Destino Telegram: {', '.join(targets)}")
    print(f"Modo de envio: {args.send_mode}")
    while True:
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

        payload = {
            "timeout": args.poll_timeout,
            "limit": args.limit,
            "allowed_updates": ["message", "edited_message"],
        }
        if update_offset:
            payload["offset"] = update_offset
        updates = telegram_api_call(token, "getUpdates", payload, timeout=args.poll_timeout + 15)
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id", 0))
            message = update.get("message") or update.get("edited_message") or {}
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = str(message.get("text") or "")
            stripped = text.strip()

            if not telegram_chat_allowed(config, chat_id):
                handle_telegram_update(root, config, update, reply=False)
                update_offset = max(update_offset or 0, update_id + 1)
                continue

            if stripped.startswith("/") and not stripped.lower().startswith(("/codex", "/queue", "/note", "/msg")):
                path = handle_telegram_update(
                    root,
                    config,
                    update,
                    create_tasks=False,
                    download_media=not args.no_download_media,
                    reply=not args.no_reply,
                )
                if path:
                    print(f"Comando Harness via Telegram: {path}")
                    processed += 1
                update_offset = max(update_offset or 0, update_id + 1)
                write_json(bridge_state_path, {"telegram_offset": update_offset, "updated_at": utc_now()})
                continue

            path = handle_telegram_update(
                root,
                config,
                update,
                create_tasks=False,
                download_media=not args.no_download_media,
                reply=False,
            )
            if not path:
                update_offset = max(update_offset or 0, update_id + 1)
                continue
            item = read_json(path, {})
            prompt_text = item.get("prompt_text") or ""
            if stripped.lower().startswith(("/codex", "/queue", "/note", "/msg")):
                prompt_text = stripped.partition(" ")[2].strip() or prompt_text

            force_codex = stripped.lower().startswith("/codex")
            if args.send_mode == "codex-exec" or force_codex:
                try:
                    if not args.no_reply:
                        telegram_reply(config, chat_id, "Recebido. Vou chamar o Codex em paralelo.")
                    result = run_codex_for_telegram(
                        root,
                        item,
                        prompt_text=prompt_text,
                        resume_last=bool(args.resume_last or not args.session_id),
                        session_id=args.session_id,
                        model=args.model,
                        sandbox=args.sandbox,
                        approval=args.approval,
                        bypass=bool(args.bypass),
                        timeout=args.codex_timeout,
                    )
                    item["action"] = "bridge_codex_completed"
                    item["codex"] = {
                        "run_id": result["run_id"],
                        "exit_code": result["exit_code"],
                        "duration_ms": result["duration_ms"],
                        "output_path": result["output_path"],
                    }
                    write_json(path, item)
                    response = result.get("response") or "Codex terminou sem mensagem final."
                    if result.get("exit_code") != 0:
                        response = f"Codex terminou com erro {result.get('exit_code')}.\n\n{response}"
                    if not args.no_reply:
                        telegram_reply(config, chat_id, response)
                except Exception as exc:
                    item["action"] = "bridge_codex_failed"
                    item["error"] = str(exc)
                    write_json(path, item)
                    if not args.no_reply:
                        telegram_reply(config, chat_id, f"Falha ao chamar Codex: {exc}")
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
            update_offset = max(update_offset or 0, update_id + 1)
            write_json(bridge_state_path, {"telegram_offset": update_offset, "updated_at": utc_now()})

        if processed:
            print(f"Bridge processou {processed} mensagens Telegram.")
        if args.once:
            if not mirrored and not processed:
                print("Nenhum update novo.")
            return
        time.sleep(args.interval)


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
    security = read_json(run_dir / "security-scan.json", {})
    ptbr_review = read_json(run_dir / "ptbr-review.json", {})
    code_review = read_json(run_dir / "code-review.json", {})
    security_status = (
        "PASS"
        if security and not security.get("findings")
        else f"FAIL ({len(security.get('findings') or [])} achado(s))"
        if security
        else "não registrado"
    )
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
        "## Revisões obrigatórias\n\n"
        f"- Security scan: {security_status}\n"
        f"- PT-BR: {ptbr_review.get('status', 'não registrado')}"
        f" — {ptbr_review.get('notes', 'sem nota')}\n"
        f"- Code review: {'PASS' if code_review.get('passed') else 'não aprovado'}"
        f" — {code_review.get('reviewer', 'não informado')}\n\n"
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


def command_status(args: argparse.Namespace) -> None:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
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
    security_scan.add_argument("--task-id", help="Vincula o scan à run atual de uma task")
    security_scan.add_argument("--json", action="store_true", help="Imprime JSON")
    security_scan.set_defaults(func=command_security_scan)
    security_status = security_sub.add_parser("status", help="Mostra ultimo scan")
    security_status.set_defaults(func=command_security_status)

    ptbr_review = sub.add_parser(
        "ptbr-review",
        help="Registra revisão de ortografia, acentuação e clareza em PT-BR",
    )
    ptbr_review.add_argument("task_id")
    ptbr_review.add_argument("--status", choices=["pass", "needs-work"], required=True)
    ptbr_review.add_argument("--reviewer", help="Pessoa ou agente que fez a revisão")
    ptbr_review.add_argument("--notes", help="Nota curta com o que foi conferido")
    ptbr_review.set_defaults(func=command_ptbr_review)

    evaluate = sub.add_parser("evaluate", help="Cria brief/handoff do avaliador ou registra avaliacao")
    evaluate.add_argument("task_id")
    evaluate.add_argument("--status", choices=["pass", "fail", "needs-work"])
    evaluate.add_argument("--notes", help="Notas da avaliacao")
    evaluate.add_argument("--notes-file", help="Le notas de avaliacao de um arquivo")
    evaluate.add_argument("--gap", action="append", help="Lacuna/item de correcao; repetivel")
    evaluate.add_argument("--evaluator", help="Pessoa ou agente que tomou a decisão contratual")
    evaluate.add_argument("--review-file", action="append", help="Arquivo com parecer do code reviewer")
    evaluate.add_argument("--review-note", action="append", help="Parecer curto do code reviewer")
    evaluate.add_argument("--reviewer", help="Pessoa ou agente que fez o code review")
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

    status = sub.add_parser("status", help="Mostra estado do Harness")
    status.set_defaults(func=command_status)

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
    telegram_codex.add_argument("--codex-timeout", type=int, default=1800, help="Timeout por chamada Codex em segundos")
    telegram_codex.add_argument("--resume-last", action="store_true", help="Usa `codex exec resume --last`")
    telegram_codex.add_argument("--session-id", help="Usa `codex exec resume <session-id>`")
    telegram_codex.add_argument("--model", help="Modelo Codex")
    telegram_codex.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"], help="Sandbox para sessoes novas")
    telegram_codex.add_argument("--approval", choices=["untrusted", "on-failure", "on-request", "never"], help="Politica de aprovacao para sessoes novas")
    telegram_codex.add_argument("--bypass", action="store_true", help="Passa --dangerously-bypass-approvals-and-sandbox ao Codex")
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
    telegram_bridge.add_argument("--follow-latest", action="store_true", default=True, help="Segue a sessao Codex mais recente")
    telegram_bridge.add_argument("--send-mode", choices=["queue", "codex-exec"], default="queue", help="Como tratar mensagens comuns do Telegram")
    telegram_bridge.add_argument("--resume-last", action="store_true", help="Usa `codex exec resume --last` para envios ao Codex")
    telegram_bridge.add_argument("--session-id", help="Usa `codex exec resume <session-id>` para envios ao Codex")
    telegram_bridge.add_argument("--model", help="Modelo Codex para envios ao Codex")
    telegram_bridge.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"], help="Sandbox para sessoes novas")
    telegram_bridge.add_argument("--approval", choices=["untrusted", "on-failure", "on-request", "never"], help="Politica de aprovacao para sessoes novas")
    telegram_bridge.add_argument("--bypass", action="store_true", help="Passa --dangerously-bypass-approvals-and-sandbox ao Codex")
    telegram_bridge.add_argument("--codex-timeout", type=int, default=1800, help="Timeout por chamada Codex em segundos")
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


if __name__ == "__main__":
    raise SystemExit(main())

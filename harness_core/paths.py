"""Filesystem layout for Harness state."""

from __future__ import annotations

from pathlib import Path

HARNESS_DIR = ".harness"


def harness_root(root: Path) -> Path:
    return root / HARNESS_DIR


def config_path(root: Path) -> Path:
    return harness_root(root) / "config.json"


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


def hub_repo_registry_path(root: Path) -> Path:
    return dashboard_hub_root(root) / "repos.json"


def event_stream_path(root: Path) -> Path:
    return harness_root(root) / "events.jsonl"


def agents_root(root: Path) -> Path:
    return harness_root(root) / "agents"


def agent_registry_path(root: Path) -> Path:
    return agents_root(root) / "registry.json"


def memory_index_path(root: Path) -> Path:
    return harness_root(root) / "memory" / "index.json"


def plugin_registry_path(root: Path) -> Path:
    return harness_root(root) / "plugins" / "registry.json"


def security_root(root: Path) -> Path:
    return harness_root(root) / "security"


def github_root(root: Path) -> Path:
    return harness_root(root) / "github"


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


def preflight_cache_path(root: Path, task_id: str | None = None) -> Path:
    name = task_id or "global"
    return harness_root(root) / "context" / "preflight-cache" / f"{name}.json"


def contract_file_path(root: Path, task_id: str) -> Path:
    return harness_root(root) / "contracts" / f"{task_id}.json"


def evaluation_markdown_path(root: Path, task_id: str) -> Path:
    return harness_root(root) / "evaluations" / f"{task_id}.md"


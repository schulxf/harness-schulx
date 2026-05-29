"""Dashboard hub repository registry helpers."""

from __future__ import annotations

from pathlib import Path

from harness_core.clock import utc_now
from harness_core.paths import hub_repo_registry_path, normalize_path_key
from harness_core.storage import read_json, write_json


def load_hub_repo_registry(root: Path) -> list[str]:
    payload = read_json(hub_repo_registry_path(root), {"repos": []})
    repos = payload.get("repos") if isinstance(payload, dict) else []
    return [str(item) for item in repos if str(item).strip()]


def save_hub_repo_registry(root: Path, repos: list[str]) -> None:
    normalized: list[str] = []
    seen: set[str] = set()
    for repo in repos:
        path = Path(repo).expanduser().resolve()
        key = normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(str(path))
    write_json(hub_repo_registry_path(root), {"repos": normalized, "updated_at": utc_now()})

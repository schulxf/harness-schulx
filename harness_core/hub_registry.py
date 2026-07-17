"""Dashboard hub repository registry helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from harness_core.clock import utc_now
from harness_core.paths import hub_repo_registry_path, normalize_path_key
from harness_core.storage import read_json, state_lock, write_json

HUB_CONTROL_REPO_ENV = "HARNESS_HUB_CONTROL_REPO"


def _normalized_paths(repos: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for repo in repos:
        if not str(repo).strip():
            continue
        path = Path(repo).expanduser().resolve()
        key = normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(str(path))
    return normalized


def _registry_payload(root: Path) -> dict[str, object]:
    payload = read_json(hub_repo_registry_path(root), {"repos": [], "hidden_repos": []})
    if not isinstance(payload, dict):
        return {"repos": [], "hidden_repos": []}
    repos = [str(item) for item in payload.get("repos", []) if str(item).strip()]
    hidden = [str(item) for item in payload.get("hidden_repos", []) if str(item).strip()]
    return {"repos": repos, "hidden_repos": hidden, "updated_at": payload.get("updated_at")}


def load_hub_repo_registry(root: Path) -> list[str]:
    payload = _registry_payload(root)
    hidden_keys = {
        normalize_path_key(Path(item).expanduser().resolve())
        for item in payload["hidden_repos"]
    }
    return [
        str(item)
        for item in payload["repos"]
        if normalize_path_key(Path(str(item)).expanduser().resolve()) not in hidden_keys
    ]


def hub_repo_registry_entries(root: Path) -> list[dict[str, object]]:
    payload = _registry_payload(root)
    hidden_keys = {
        normalize_path_key(Path(item).expanduser().resolve())
        for item in payload["hidden_repos"]
    }
    return [
        {
            "path": str(item),
            "hidden": normalize_path_key(Path(str(item)).expanduser().resolve()) in hidden_keys,
        }
        for item in payload["repos"]
    ]


def save_hub_repo_registry(root: Path, repos: list[str]) -> None:
    normalized = _normalized_paths(repos)
    existing = _registry_payload(root)
    repo_keys = {normalize_path_key(Path(item)) for item in normalized}
    hidden = _normalized_paths([str(item) for item in existing["hidden_repos"]])
    hidden = [item for item in hidden if normalize_path_key(Path(item)) in repo_keys]
    write_json(
        hub_repo_registry_path(root),
        {"repos": normalized, "hidden_repos": hidden, "updated_at": utc_now()},
    )


def add_hub_repo(root: Path, repo: str, *, unhide: bool = True) -> bool:
    resolved = str(Path(repo).expanduser().resolve())
    key = normalize_path_key(Path(resolved))
    with state_lock(root, "hub-repos"):
        payload = _registry_payload(root)
        repos = _normalized_paths([str(item) for item in payload["repos"]])
        existing_keys = {normalize_path_key(Path(item)) for item in repos}
        added = key not in existing_keys
        if added:
            repos.append(resolved)
        hidden_repos = _normalized_paths([str(value) for value in payload["hidden_repos"]])
        if added or unhide:
            hidden_repos = [
                item
                for item in hidden_repos
                if normalize_path_key(Path(item)) != key
            ]
        write_json(
            hub_repo_registry_path(root),
            {"repos": repos, "hidden_repos": hidden_repos, "updated_at": utc_now()},
        )
    return added


def discover_hub_control_repo(
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    values = os.environ if environ is None else environ
    if HUB_CONTROL_REPO_ENV in values:
        configured = str(values.get(HUB_CONTROL_REPO_ENV) or "").strip()
        candidates = [Path(configured)] if configured else []
    else:
        local_app_data = str(values.get("LOCALAPPDATA") or "").strip()
        candidates = (
            [Path(local_app_data) / "HarnessAcompanhamento" / "control"]
            if local_app_data
            else []
        )

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / ".harness" / "config.json").is_file():
            return resolved
    return None


def register_implementation_repo(
    root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    repo = root.expanduser().resolve()
    control = discover_hub_control_repo(environ)
    if control is None:
        return {"status": "not_configured", "repo": str(repo), "control_repo": None}

    added = add_hub_repo(control, str(repo), unhide=False)
    entry = next(
        (
            item
            for item in hub_repo_registry_entries(control)
            if normalize_path_key(Path(str(item["path"]))) == normalize_path_key(repo)
        ),
        {"hidden": False},
    )
    return {
        "status": "added" if added else "already_registered",
        "repo": str(repo),
        "control_repo": str(control),
        "hidden": bool(entry.get("hidden")),
    }


def set_hub_repo_hidden(root: Path, repo: str, *, hidden: bool) -> None:
    resolved = str(Path(repo).expanduser().resolve())
    key = normalize_path_key(Path(resolved))
    with state_lock(root, "hub-repos"):
        payload = _registry_payload(root)
        repos = _normalized_paths([str(item) for item in payload["repos"]])
        if key not in {normalize_path_key(Path(item)) for item in repos}:
            raise SystemExit(f"Pasta não encontrada no acompanhamento: {resolved}")
        hidden_repos = _normalized_paths([str(item) for item in payload["hidden_repos"]])
        hidden_keys = {normalize_path_key(Path(item)) for item in hidden_repos}
        if hidden:
            if key not in hidden_keys:
                hidden_repos.append(resolved)
        else:
            hidden_repos = [item for item in hidden_repos if normalize_path_key(Path(item)) != key]
        write_json(
            hub_repo_registry_path(root),
            {"repos": repos, "hidden_repos": hidden_repos, "updated_at": utc_now()},
        )


def remove_hub_repo(root: Path, repo: str) -> None:
    key = normalize_path_key(Path(repo).expanduser().resolve())
    with state_lock(root, "hub-repos"):
        payload = _registry_payload(root)
        repos = [
            item
            for item in _normalized_paths([str(value) for value in payload["repos"]])
            if normalize_path_key(Path(item)) != key
        ]
        hidden_repos = [
            item
            for item in _normalized_paths([str(value) for value in payload["hidden_repos"]])
            if normalize_path_key(Path(item)) != key
        ]
        write_json(
            hub_repo_registry_path(root),
            {"repos": repos, "hidden_repos": hidden_repos, "updated_at": utc_now()},
        )

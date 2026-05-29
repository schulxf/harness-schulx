"""Plugin registry persistence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.paths import plugin_registry_path
from harness_core.storage import read_json, write_json


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

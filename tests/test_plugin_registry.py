from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.plugin_registry import load_plugins, plugin_by_name, save_plugins
from harness_core.storage import write_json


def test_plugin_registry_round_trip(tmp_path: Path) -> None:
    plugins = [{"name": "audit", "enabled": True}]

    save_plugins(tmp_path, plugins)

    assert load_plugins(tmp_path) == plugins
    assert plugin_by_name(tmp_path, "audit") == plugins[0]


def test_load_plugins_accepts_legacy_list_payload(tmp_path: Path) -> None:
    plugins = [{"name": "legacy"}]
    write_json(tmp_path / ".harness" / "plugins" / "registry.json", plugins)

    assert load_plugins(tmp_path) == plugins


def test_load_plugins_ignores_invalid_payload_shape(tmp_path: Path) -> None:
    write_json(tmp_path / ".harness" / "plugins" / "registry.json", "bad")

    assert load_plugins(tmp_path) == []


def test_plugin_by_name_errors_when_missing(tmp_path: Path) -> None:
    save_plugins(tmp_path, [])

    with pytest.raises(SystemExit, match="Plugin nao encontrado"):
        plugin_by_name(tmp_path, "missing")

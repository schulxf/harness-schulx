"""Renderer and static assets for the Harness accompaniment dashboard."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from harness_core.storage import write_json, write_text

_ASSET_PACKAGE = "harness_core.dashboard_hub_assets"
_BOOTSTRAP_TAG = (
    '<script id="hub-bootstrap" type="application/json" '
    'data-refresh-ms="3000">{}</script>'
)


def dashboard_asset_text(name: str) -> str:
    return resources.files(_ASSET_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def safe_json_for_script(data: Any) -> str:
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
    )


def render_dashboard_hub_html(state: dict[str, Any], refresh_seconds: int = 3) -> str:
    refresh_ms = max(1, int(refresh_seconds)) * 1000
    replacement = (
        '<script id="hub-bootstrap" type="application/json" '
        f'data-refresh-ms="{refresh_ms}">{safe_json_for_script(state)}</script>'
    )
    return dashboard_asset_text("index.html").replace(_BOOTSTRAP_TAG, replacement, 1)


def write_dashboard_hub_files(target: Path, state: dict[str, Any], refresh_seconds: int = 3) -> None:
    target.mkdir(parents=True, exist_ok=True)
    write_text(target / "index.html", render_dashboard_hub_html(state, refresh_seconds))
    write_text(target / "hub.css", dashboard_asset_text("hub.css"))
    write_text(target / "hub.js", dashboard_asset_text("hub.js"))
    write_text(target / "presentation.js", dashboard_asset_text("presentation.js"))
    write_json(target / "hub-state.json", state)

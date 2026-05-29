"""Renderer and static assets for the pixel hub dashboard."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from harness_core.storage import write_json, write_text

_ASSET_PACKAGE = "harness_core.dashboard_hub_assets"
_HTML_SHELL = '<!doctype html>\n<html lang="pt-BR">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Harness Hub</title>\n  <link rel="stylesheet" href="hub.css">\n</head>\n<body>\n  <header>\n    <div>\n      <h1>Harness Hub</h1>\n      <div class="subhead" id="generated">Mapa operacional local</div>\n    </div>\n    <div class="hud" aria-label="Resumo do hub">\n      <div class="chip" id="repoCount">Repos: 0</div>\n      <div class="chip" id="activeCount">Ativos: 0</div>\n      <div class="chip" id="taskCount">Tasks: 0</div>\n      <div class="chip" id="findingCount">Findings: 0</div>\n    </div>\n  </header>\n  <div class="shell">\n    <main class="world-wrap" aria-label="Mapa pixelado do Harness">\n      <div class="world" id="world">\n        <div class="hall"></div>\n        <div class="core" title="Hub core"></div>\n      </div>\n    </main>\n    <aside>\n      <section class="panel">\n        <h2>Projetos</h2>\n        <div class="repo-list" id="repoList"></div>\n      </section>\n      <section class="panel">\n        <h2>Inspecao</h2>\n        <div class="detail" id="detail">Selecione uma sala no mapa.</div>\n      </section>\n    </aside>\n  </div>\n  <script id="hub-bootstrap" type="application/json" data-refresh-ms="{refresh_ms}">{bootstrap_json}</script>\n  <script src="hub.js" defer></script>\n</body>\n</html>\n'


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
    return _HTML_SHELL.format(
        refresh_ms=refresh_ms,
        bootstrap_json=safe_json_for_script(state),
    )


def write_dashboard_hub_files(target: Path, state: dict[str, Any], refresh_seconds: int = 3) -> None:
    target.mkdir(parents=True, exist_ok=True)
    write_text(target / "index.html", render_dashboard_hub_html(state, refresh_seconds))
    write_text(target / "hub.css", dashboard_asset_text("hub.css"))
    write_text(target / "hub.js", dashboard_asset_text("hub.js"))
    write_json(target / "hub-state.json", state)

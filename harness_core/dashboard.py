"""Classic single-repo dashboard state and HTML rendering."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from harness_core.artifacts import collect_run_artifacts
from harness_core.clock import utc_now
from harness_core.context_preflight import load_config
from harness_core.memory import load_memory
from harness_core.paths import dashboard_root, security_root
from harness_core.plugin_registry import load_plugins
from harness_core.queue_state import load_queue, sorted_queue_items
from harness_core.run_state import find_unevaluated_runs
from harness_core.storage import read_json, write_json, write_text
from harness_core.task_store import load_tasks


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


def write_dashboard_html(root: Path) -> dict[str, Any]:
    state = collect_dashboard_state(root)
    path = dashboard_root(root) / "index.html"
    write_text(path, render_dashboard_html(root, state))
    write_json(dashboard_root(root) / "state.json", state)
    return {"state": state, "path": path, "state_path": dashboard_root(root) / "state.json"}

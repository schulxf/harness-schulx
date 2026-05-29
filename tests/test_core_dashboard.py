from __future__ import annotations

from pathlib import Path

from harness_core.dashboard import (
    collect_dashboard_state,
    render_dashboard_html,
    write_dashboard_html,
)
from harness_core.paths import config_path, queue_path, tasks_index_path
from harness_core.storage import read_json, write_json


def init_dashboard_repo(root: Path) -> None:
    write_json(config_path(root), {"project_name": "Dash <Repo>", "active_profile": "balanced"})
    write_json(
        tasks_index_path(root),
        [{"task_id": "TASK-001", "status": "planned", "title": "Build <login>"}],
    )
    write_json(queue_path(root), [{"id": "QUEUE-001", "status": "queued", "title": "Next"}])


def test_collect_dashboard_state_reads_project_records(tmp_path: Path) -> None:
    init_dashboard_repo(tmp_path)

    state = collect_dashboard_state(tmp_path)

    assert state["project"] == "Dash <Repo>"
    assert state["tasks"][0]["task_id"] == "TASK-001"
    assert state["queue"][0]["id"] == "QUEUE-001"
    assert state["unevaluated_runs"] == []


def test_render_dashboard_html_escapes_user_content(tmp_path: Path) -> None:
    init_dashboard_repo(tmp_path)
    state = collect_dashboard_state(tmp_path)

    html = render_dashboard_html(tmp_path, state)

    assert "Dash &lt;Repo&gt;" in html
    assert "Build &lt;login&gt;" in html


def test_write_dashboard_html_writes_index_and_state(tmp_path: Path) -> None:
    init_dashboard_repo(tmp_path)

    result = write_dashboard_html(tmp_path)

    assert result["path"].is_file()
    assert result["state_path"].is_file()
    assert read_json(result["state_path"])["project"] == "Dash <Repo>"

from __future__ import annotations

from harness_core.hub_agents import (
    hub_agent_name_for_role,
    hub_agent_role_for_phase,
    hub_agent_speech,
    hub_agent_state_for_phase,
    hub_repo_phase,
)


def test_hub_repo_phase_prioritizes_security_then_active_task() -> None:
    assert hub_repo_phase([], [], {"findings": [{"severity": "high"}]}) == "security"
    assert hub_repo_phase(
        [{"task_id": "TASK-001", "status": "in_progress"}],
        [{"task_id": "TASK-001", "status": "active"}],
        {},
    ) == "build"
    assert hub_repo_phase(
        [{"task_id": "TASK-001", "status": "sensors_passed"}],
        [{"task_id": "TASK-001", "status": "active"}],
        {},
    ) == "review"


def test_hub_repo_phase_falls_back_to_queue_report_and_idle() -> None:
    assert hub_repo_phase([], [{"status": "queued"}], {}) == "queue"
    assert hub_repo_phase([{"status": "passed"}], [], {}) == "report"
    assert hub_repo_phase([], [], {}) == "idle"


def test_hub_agent_role_name_and_state_for_phase() -> None:
    assert hub_agent_role_for_phase("review") == "reviewer"
    assert hub_agent_role_for_phase("unknown") == "operator"
    assert hub_agent_name_for_role("security") == "Sentinel"
    assert hub_agent_name_for_role("unknown") == "Operator"
    assert hub_agent_state_for_phase("build", "TASK-001") == "working"
    assert hub_agent_state_for_phase("build", "") == "idle"


def test_hub_agent_speech_mentions_current_work_or_queue() -> None:
    task = {"task_id": "TASK-001", "title": "Login"}

    assert hub_agent_speech("build", task, [], {}) == "Trabalhando em TASK-001: Login."
    assert hub_agent_speech("security", None, [], {"findings": [{}]}) == (
        "Encontrei 1 alerta(s) de seguranca."
    )
    assert hub_agent_speech("idle", None, [{"status": "queued"}], {}) == (
        "Livre. 1 item(ns) na fila."
    )

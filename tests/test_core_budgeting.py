from __future__ import annotations

from harness_core.budgeting import task_budget


def test_task_budget_uses_active_profile_and_task_overrides() -> None:
    config = {
        "active_profile": "quick",
        "operation_profiles": {"quick": {"max_tokens": 100, "timeout_minutes": 5}},
    }
    task = {"budget": {"timeout_minutes": 10}}

    assert task_budget(task, config) == {
        "name": "quick",
        "max_tokens": 100,
        "timeout_minutes": 10,
    }


def test_task_budget_supports_legacy_budgets_for_unknown_profile() -> None:
    config = {"budgets": {"legacy": {"max_tokens": 200}}}
    task = {"budget": {"profile": "legacy", "timeout_minutes": 20}}

    assert task_budget(task, config) == {
        "name": "legacy",
        "max_tokens": 200,
        "profile": "legacy",
        "timeout_minutes": 20,
    }

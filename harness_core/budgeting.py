"""Budget/profile helpers."""

from __future__ import annotations

from typing import Any

from harness_core.config import active_profile, operation_profiles


def task_budget(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    requested = task.get("budget", {}).get("profile")
    if requested and requested not in operation_profiles(config):
        profile = {"name": requested}
        if isinstance(config.get("profiles"), dict):
            profile.update(config["profiles"].get(requested, {}))
        if isinstance(config.get("budgets"), dict):
            profile.update(config["budgets"].get(requested, {}))
    else:
        profile = active_profile(config, requested)
    budget = dict(profile)
    if isinstance(task.get("budget"), dict):
        budget.update(task["budget"])
    return budget

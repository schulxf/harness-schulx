import pytest

from harness_core.plugin_policy import (
    PLUGIN_REVIEW_REQUIRED_MESSAGE,
    PluginPolicyError,
    UnknownPluginPlaceholderError,
    plugin_run_decision,
    render_plugin_command,
    require_plugin_run_allowed,
)


def test_render_plugin_command_substitutes_supported_placeholders(tmp_path):
    command = render_plugin_command(
        "tool --repo {repo} --task {task_id} --event {event}",
        tmp_path,
        "TASK-123",
        "after-evaluate",
    )

    assert command == f"tool --repo {tmp_path} --task TASK-123 --event after-evaluate"


def test_render_plugin_command_rejects_unknown_placeholder(tmp_path):
    with pytest.raises(UnknownPluginPlaceholderError) as exc:
        render_plugin_command("tool --branch {branch} --repo {repo}", tmp_path)

    message = str(exc.value)
    assert "Placeholder de plugin desconhecido: {branch}" in message
    assert "{event}, {repo}, {task_id}" in message


def test_plugin_run_requires_review_for_real_execution():
    decision = plugin_run_decision(dry_run=False, reviewed=False)

    assert decision.allowed is False
    assert decision.requires_review is True
    assert decision.reason == PLUGIN_REVIEW_REQUIRED_MESSAGE
    with pytest.raises(PluginPolicyError, match="plugin run --reviewed"):
        require_plugin_run_allowed(dry_run=False, reviewed=False)


def test_plugin_run_allows_dry_run_reviewed_or_confirmed():
    assert plugin_run_decision(dry_run=True, reviewed=False).allowed is True
    assert plugin_run_decision(dry_run=False, reviewed=True).allowed is True
    assert plugin_run_decision(dry_run=False, reviewed=False, confirmed=True).allowed is True

"""Pure plugin command rendering and execution policy helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

from harness_core.config import config_bool

ALLOWED_PLUGIN_PLACEHOLDERS = frozenset({"repo", "task_id", "event"})
PLUGIN_REVIEW_REQUIRED_MESSAGE = (
    "Execucao de plugin bloqueada: revise os comandos registrados e rode novamente com "
    "`plugin run --reviewed`."
)


class PluginPolicyError(ValueError):
    """Raised when a plugin command template or execution policy is invalid."""


class UnknownPluginPlaceholderError(PluginPolicyError):
    """Raised when a plugin command template contains an unsupported placeholder."""


@dataclass(frozen=True)
class PluginRunDecision:
    allowed: bool
    requires_review: bool
    reason: str | None = None


def render_plugin_command(
    template: str,
    repo: str | Path,
    task_id: str | None = "",
    event: str = "",
) -> str:
    """Render a plugin command template using only Harness-supported placeholders."""
    values = {
        "repo": str(repo),
        "task_id": task_id or "",
        "event": event,
    }
    _validate_plugin_template(template)
    return template.format_map(values)


def plugin_run_decision(
    *,
    dry_run: bool,
    reviewed: bool,
    confirmed: bool = False,
) -> PluginRunDecision:
    """Return whether plugin execution is allowed under the current reviewed gate."""
    if dry_run or reviewed or confirmed:
        return PluginRunDecision(allowed=True, requires_review=False)
    return PluginRunDecision(
        allowed=False,
        requires_review=True,
        reason=PLUGIN_REVIEW_REQUIRED_MESSAGE,
    )


def require_plugin_run_allowed(
    *,
    dry_run: bool,
    reviewed: bool,
    confirmed: bool = False,
) -> None:
    decision = plugin_run_decision(dry_run=dry_run, reviewed=reviewed, confirmed=confirmed)
    if not decision.allowed:
        raise PluginPolicyError(decision.reason or PLUGIN_REVIEW_REQUIRED_MESSAGE)


def plugin_matches_event(plugin: Mapping[str, Any], event: str) -> bool:
    events = _plugin_events(plugin)
    return not events or event in events


def plugin_is_runnable(plugin: Mapping[str, Any], event: str) -> bool:
    return (
        config_bool(plugin.get("enabled"), True)
        and bool(plugin.get("command"))
        and plugin_matches_event(plugin, event)
    )


def runnable_plugins(plugins: Sequence[Mapping[str, Any]], event: str) -> list[Mapping[str, Any]]:
    return [plugin for plugin in plugins if plugin_is_runnable(plugin, event)]


def _validate_plugin_template(template: str) -> None:
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise PluginPolicyError(f"Template de comando de plugin invalido: {exc}") from exc

    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in ALLOWED_PLUGIN_PLACEHOLDERS:
            allowed = ", ".join(f"{{{name}}}" for name in sorted(ALLOWED_PLUGIN_PLACEHOLDERS))
            raise UnknownPluginPlaceholderError(
                f"Placeholder de plugin desconhecido: {{{field_name}}}. Use apenas: {allowed}."
            )
        if conversion or format_spec:
            raise PluginPolicyError(
                f"Placeholder de plugin {{{field_name}}} nao aceita conversao ou formato."
            )


def _plugin_events(plugin: Mapping[str, Any]) -> list[str]:
    events = plugin.get("events") or []
    if isinstance(events, str):
        return [events]
    if not isinstance(events, Sequence):
        return []
    return [str(event) for event in events]

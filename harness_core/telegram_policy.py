"""Pure Telegram allowlist and remote execution policy helpers."""

from __future__ import annotations

from typing import Any

from harness_core.config import config_bool, telegram_config


def telegram_allowed_chat_ids(config: dict[str, Any]) -> list[str]:
    """Return the effective inbound Telegram allowlist."""
    tconfig = telegram_config(config)
    allowed = [str(item) for item in tconfig.get("allowed_chat_ids", [])]
    if allowed:
        return allowed
    return [str(item) for item in tconfig.get("chat_ids", [])]


def telegram_chat_allowed(config: dict[str, Any], chat_id: str) -> bool:
    allowed = telegram_allowed_chat_ids(config)
    return bool(allowed) and str(chat_id) in set(allowed)


def telegram_remote_execution_allowed(config: dict[str, Any]) -> bool:
    tconfig = telegram_config(config)
    return config_bool(tconfig.get("allow_remote_execution"), False) and bool(
        telegram_allowed_chat_ids(config)
    )

"""Telegram API and update-state helpers."""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.config import telegram_config
from harness_core.errors import HarnessError
from harness_core.http import http_json_post
from harness_core.storage import write_json


def telegram_token(config: dict[str, Any]) -> str:
    tconfig = telegram_config(config)
    return os.environ.get(str(tconfig.get("token_env") or "HARNESS_TELEGRAM_BOT_TOKEN"), "")


def require_telegram_bot_token(config: dict[str, Any]) -> str:
    token = telegram_token(config)
    if token:
        return token
    raise SystemExit(
        "Token do Telegram nao encontrado. Configure a variavel de ambiente "
        f"{telegram_config(config).get('token_env')}."
    )


def telegram_api_call(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe=':')}/{method}"
    response = http_json_post(url, payload or {}, timeout=timeout)
    if not response.get("ok"):
        raise HarnessError(response.get("description") or f"Telegram API error in {method}")
    return response.get("result")


def split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def telegram_send_message(
    config: dict[str, Any],
    text: str,
    chat_ids: list[str] | None = None,
) -> list[Any]:
    tconfig = telegram_config(config)
    token = telegram_token(config)
    targets = chat_ids if chat_ids is not None else [str(item) for item in tconfig.get("chat_ids", [])]
    if not token or not targets:
        return []
    sent = []
    for chat_id in targets:
        for chunk in split_telegram_text(text):
            sent.append(
                telegram_api_call(
                    token,
                    "sendMessage",
                    {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                )
            )
    return sent


def telegram_poll_updates(
    token: str,
    *,
    timeout: int,
    limit: int,
    offset: int | None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "timeout": timeout,
        "limit": limit,
        "allowed_updates": ["message", "edited_message"],
    }
    if offset:
        payload["offset"] = offset
    return telegram_api_call(token, "getUpdates", payload, timeout=timeout + 15)


def telegram_update_context(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message") or {}
    text = str(message.get("text") or "")
    return {
        "update_id": int(update.get("update_id", 0)),
        "message": message,
        "chat_id": str(message.get("chat", {}).get("id", "")),
        "text": text,
        "stripped": text.strip(),
    }


def advance_telegram_offset(offset: int | None, update_id: int) -> int:
    return max(offset or 0, update_id + 1)


def write_telegram_offset_state(path: Path, offset: int | None) -> None:
    write_json(path, {"offset": offset, "updated_at": utc_now()})


def write_telegram_bridge_state(
    path: Path,
    telegram_offset: int | None,
    event_offset: int | None,
) -> None:
    write_json(
        path,
        {
            "telegram_offset": telegram_offset,
            "event_offset": event_offset,
            "updated_at": utc_now(),
        },
    )

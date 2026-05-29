from __future__ import annotations

from pathlib import Path

import pytest

from harness_core import telegram
from harness_core.errors import HarnessError
from harness_core.storage import read_json


def test_telegram_token_reads_configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN_ENV", "tok")

    assert telegram.telegram_token({"telegram": {"token_env": "BOT_TOKEN_ENV"}}) == "tok"


def test_require_telegram_bot_token_explains_missing_token() -> None:
    with pytest.raises(SystemExit, match="Token do Telegram nao encontrado"):
        telegram.require_telegram_bot_token({"telegram": {"token_env": "MISSING_TOKEN_ENV"}})


def test_split_telegram_text_chunks_without_losing_content() -> None:
    text = "alpha\nbeta\ngamma"

    chunks = telegram.split_telegram_text(text, limit=8)

    assert chunks == ["alpha", "beta", "gamma"]
    assert "".join(chunks) == "alphabetagamma"


def test_telegram_send_message_uses_configured_chats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS_TELEGRAM_BOT_TOKEN", "tok")
    calls = []

    def fake_api_call(token: str, method: str, payload: dict, timeout: int = 30) -> dict:
        calls.append((token, method, payload, timeout))
        return {"message_id": len(calls)}

    monkeypatch.setattr(telegram, "telegram_api_call", fake_api_call)

    sent = telegram.telegram_send_message(
        {"telegram": {"chat_ids": ["1", "2"]}},
        "hello",
    )

    assert sent == [{"message_id": 1}, {"message_id": 2}]
    assert [call[2]["chat_id"] for call in calls] == ["1", "2"]


def test_telegram_send_message_returns_empty_without_token_or_targets() -> None:
    assert telegram.telegram_send_message({"telegram": {"chat_ids": ["1"]}}, "hello") == []
    assert telegram.telegram_send_message({"telegram": {}}, "hello") == []


def test_telegram_api_call_raises_for_telegram_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        telegram,
        "http_json_post",
        lambda url, payload, timeout: {"ok": False, "description": "bad request"},
    )

    with pytest.raises(HarnessError, match="bad request"):
        telegram.telegram_api_call("tok", "sendMessage", {"chat_id": "1"})


def test_telegram_poll_updates_builds_standard_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_api_call(token: str, method: str, payload: dict, timeout: int) -> list[dict]:
        calls.append((token, method, payload, timeout))
        return [{"update_id": 1}]

    monkeypatch.setattr(telegram, "telegram_api_call", fake_api_call)

    assert telegram.telegram_poll_updates("tok", timeout=5, limit=2, offset=9) == [{"update_id": 1}]
    assert calls == [
        (
            "tok",
            "getUpdates",
            {
                "timeout": 5,
                "limit": 2,
                "allowed_updates": ["message", "edited_message"],
                "offset": 9,
            },
            20,
        )
    ]


def test_telegram_update_context_and_offset_helpers() -> None:
    context = telegram.telegram_update_context(
        {
            "update_id": 41,
            "message": {
                "chat": {"id": 123},
                "text": "  /codex oi  ",
            },
        }
    )

    assert context["update_id"] == 41
    assert context["chat_id"] == "123"
    assert context["text"] == "  /codex oi  "
    assert context["stripped"] == "/codex oi"
    assert telegram.advance_telegram_offset(None, 41) == 42
    assert telegram.advance_telegram_offset(100, 41) == 100


def test_write_telegram_state_files(tmp_path: Path) -> None:
    telegram.write_telegram_offset_state(tmp_path / "state.json", 42)
    telegram.write_telegram_bridge_state(tmp_path / "bridge.json", 10, 20)

    assert read_json(tmp_path / "state.json")["offset"] == 42
    bridge = read_json(tmp_path / "bridge.json")
    assert bridge["telegram_offset"] == 10
    assert bridge["event_offset"] == 20

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


def test_telegram_send_message_returns_empty_without_token_or_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HARNESS_TELEGRAM_BOT_TOKEN", raising=False)

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


def test_openai_extract_output_text_handles_responses_shape() -> None:
    assert telegram.openai_extract_output_text({"output_text": " direct "}) == "direct"
    assert telegram.openai_extract_output_text(
        {
            "output": [
                {"content": [{"text": "first"}, {"text": "second"}]},
            ]
        }
    ) == "first\nsecond"


def test_telegram_message_media_selects_largest_photo_and_documents() -> None:
    assert telegram.telegram_message_media(
        {"photo": [{"file_id": "small", "file_size": 1}, {"file_id": "large", "file_size": 2}]}
    ) == ("image", "large", ".jpg")
    assert telegram.telegram_message_media(
        {"document": {"file_id": "doc", "mime_type": "audio/mpeg", "file_name": "voice.m4a"}}
    ) == ("audio", "doc", ".m4a")


def test_build_telegram_prompt_text_prefers_text_then_media_context() -> None:
    assert telegram.build_telegram_prompt_text("image", "  do this  ", "", "", "") == "do this"
    assert telegram.build_telegram_prompt_text(
        "image",
        "",
        "caption",
        "local/file.jpg",
        "uma tela de login",
    ) == "caption\n\nDescricao da imagem: uma tela de login\n\nArquivo recebido: local/file.jpg"


def test_render_task_body_from_telegram_includes_origin_and_media_warning() -> None:
    body = telegram.render_task_body_from_telegram(
        {
            "prompt_text": "Criar login",
            "chat_id": "123",
            "message_id": 10,
            "update_id": 20,
            "media": {"local_path": "media/a.jpg"},
            "media_analysis_error": "sem chave",
        }
    )

    assert "Criar login" in body
    assert "- Chat: 123" in body
    assert "- Arquivo: media/a.jpg" in body
    assert "Aviso de leitura de midia: sem chave" in body


def test_save_telegram_inbox_item_writes_json_and_index(tmp_path: Path) -> None:
    path = telegram.save_telegram_inbox_item(tmp_path, {"id": "tg-1", "text": "hello"})

    assert path == tmp_path / ".harness" / "inbox" / "telegram" / "tg-1.json"
    assert read_json(path)["text"] == "hello"
    assert (tmp_path / ".harness" / "inbox" / "telegram" / "index.jsonl").exists()


def test_analyze_telegram_media_skips_when_disabled(tmp_path: Path) -> None:
    media_path = tmp_path / "voice.ogg"
    media_path.write_text("x", encoding="utf-8")

    assert telegram.analyze_telegram_media(media_path, "voice", {"telegram": {"openai_media": {}}}) == ("", None)


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

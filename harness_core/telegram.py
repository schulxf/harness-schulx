"""Telegram API and update-state helpers."""

from __future__ import annotations

import base64
import mimetypes
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.config import config_bool, telegram_config
from harness_core.errors import HarnessError
from harness_core.http import http_json_post, http_multipart_post
from harness_core.paths import telegram_inbox_root, telegram_media_root
from harness_core.storage import append_jsonl, write_json


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


def openai_media_config(config: dict[str, Any]) -> dict[str, Any]:
    return telegram_config(config).get("openai_media", {})


def openai_api_key(config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    return os.environ.get(str(media.get("api_key_env") or "OPENAI_API_KEY"), "")


def openai_extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    texts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "\n".join(texts).strip()


def openai_transcribe_audio(path: Path, config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    api_key = openai_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key not found.")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = http_multipart_post(
        "https://api.openai.com/v1/audio/transcriptions",
        {
            "model": str(media.get("audio_model") or "gpt-4o-mini-transcribe"),
            "response_format": "json",
        },
        [("file", path, content_type)],
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    text = response.get("text") or response.get("transcript")
    return str(text).strip() if text else ""


def openai_describe_image(path: Path, config: dict[str, Any]) -> str:
    media = openai_media_config(config)
    api_key = openai_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key not found.")
    content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    image_data = base64.b64encode(path.read_bytes()).decode("ascii")
    response = http_json_post(
        "https://api.openai.com/v1/responses",
        {
            "model": str(media.get("vision_model") or "gpt-4.1-mini"),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Descreva esta imagem em portugues de forma objetiva, "
                                "focando no pedido que ela provavelmente representa para uma task."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{content_type};base64,{image_data}",
                        },
                    ],
                }
            ],
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    return openai_extract_output_text(response)


def save_telegram_inbox_item(root: Path, item: dict[str, Any]) -> Path:
    inbox = telegram_inbox_root(root)
    inbox.mkdir(parents=True, exist_ok=True)
    item_id = str(item["id"])
    path = inbox / f"{item_id}.json"
    write_json(path, item)
    append_jsonl(inbox / "index.jsonl", {"ts": utc_now(), "id": item_id, "path": str(path)})
    return path


def telegram_file_extension(file_path: str, fallback: str) -> str:
    suffix = Path(file_path).suffix
    if suffix:
        return suffix
    return fallback


def telegram_download_file(
    root: Path,
    config: dict[str, Any],
    file_id: str,
    item_id: str,
    fallback_ext: str,
) -> dict[str, Any]:
    token = telegram_token(config)
    if not token:
        raise RuntimeError("Telegram token not found.")
    file_info = telegram_api_call(token, "getFile", {"file_id": file_id})
    file_path = str(file_info.get("file_path") or "")
    if not file_path:
        raise RuntimeError("Telegram did not return file_path.")
    max_bytes = int(telegram_config(config).get("max_download_bytes") or 20 * 1024 * 1024)
    url = f"https://api.telegram.org/file/bot{urllib.parse.quote(token, safe=':')}/{file_path}"
    extension = telegram_file_extension(file_path, fallback_ext)
    target = telegram_media_root(root) / f"{item_id}{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, method="GET")
    total = 0
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"Arquivo do Telegram excede limite de {max_bytes} bytes.")
            handle.write(chunk)
    return {
        "file_id": file_id,
        "telegram_file_path": file_path,
        "local_path": str(target),
        "size": total,
    }


def telegram_message_media(message: dict[str, Any]) -> tuple[str | None, str | None, str]:
    if message.get("photo"):
        photo = sorted(message["photo"], key=lambda item: item.get("file_size", 0))[-1]
        return "image", photo.get("file_id"), ".jpg"
    if message.get("voice"):
        return "voice", message["voice"].get("file_id"), ".ogg"
    if message.get("audio"):
        audio = message["audio"]
        suffix = Path(audio.get("file_name") or "").suffix or ".mp3"
        return "audio", audio.get("file_id"), suffix
    document = message.get("document")
    if document:
        mime = str(document.get("mime_type") or "")
        filename = str(document.get("file_name") or "")
        if mime.startswith("image/"):
            return "image", document.get("file_id"), Path(filename).suffix or ".jpg"
        if mime.startswith("audio/"):
            return "audio", document.get("file_id"), Path(filename).suffix or ".mp3"
    return None, None, ""


def analyze_telegram_media(
    path: Path,
    media_kind: str,
    config: dict[str, Any],
) -> tuple[str, str | None]:
    media_config = openai_media_config(config)
    if not config_bool(media_config.get("enabled"), False):
        return "", None
    try:
        if media_kind in {"voice", "audio"} and config_bool(media_config.get("transcribe_audio"), True):
            return openai_transcribe_audio(path, config), None
        if media_kind == "image" and config_bool(media_config.get("describe_images"), True):
            return openai_describe_image(path, config), None
    except Exception as exc:
        return "", str(exc)
    return "", None


def build_telegram_prompt_text(
    kind: str,
    text: str,
    caption: str,
    media_path: str,
    media_analysis: str,
) -> str:
    if text:
        return text.strip()
    parts = []
    if caption:
        parts.append(caption.strip())
    if media_analysis:
        label = "Transcricao" if kind in {"voice", "audio"} else "Descricao da imagem"
        parts.append(f"{label}: {media_analysis.strip()}")
    if media_path:
        parts.append(f"Arquivo recebido: {media_path}")
    if not parts:
        parts.append(f"Mensagem de {kind or 'Telegram'} recebida.")
    return "\n\n".join(parts).strip()


def render_task_body_from_telegram(item: dict[str, Any]) -> str:
    media = item.get("media") or {}
    lines = [
        item.get("prompt_text") or "",
        "",
        "## Origem Telegram",
        "",
        f"- Chat: {item.get('chat_id')}",
        f"- Message ID: {item.get('message_id')}",
        f"- Update ID: {item.get('update_id')}",
    ]
    if media.get("local_path"):
        lines.append(f"- Arquivo: {media.get('local_path')}")
    if item.get("media_analysis_error"):
        lines.append(f"- Aviso de leitura de midia: {item.get('media_analysis_error')}")
    return "\n".join(lines).strip()


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

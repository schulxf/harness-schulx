"""Codex session discovery and mirror parsing helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from harness_core.errors import HarnessError


def codex_sessions_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"


def latest_codex_session_file() -> Path:
    root = codex_sessions_root()
    if not root.exists():
        raise HarnessError(f"Diretorio de sessoes Codex nao encontrado: {root}")
    files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    if not files:
        raise HarnessError(f"Nenhuma sessao Codex encontrada em {root}")
    return max(files, key=lambda path: path.stat().st_mtime)


def mirror_state_key(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode("utf-8")).hexdigest()


def decode_codex_session_line(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def summarize_tool_arguments(name: str, arguments: str) -> str:
    try:
        parsed = json.loads(arguments)
    except Exception:
        parsed = arguments
    if name == "shell_command" and isinstance(parsed, dict):
        command = str(parsed.get("command") or "").strip()
        return command[:800]
    if isinstance(parsed, dict):
        compact = json.dumps(parsed, ensure_ascii=False)
        return compact[:800]
    return str(parsed)[:800]


def mirror_message_from_codex_event(event: dict[str, Any], include_tools: bool) -> str | None:
    event_type = event.get("type")
    payload = event.get("payload") or {}

    if event_type == "event_msg":
        ptype = payload.get("type")
        if ptype == "agent_message":
            phase = payload.get("phase")
            label = "Codex"
            if phase == "commentary":
                label = "Codex update"
            elif phase == "final_answer":
                label = "Codex final"
            message = str(payload.get("message") or "").strip()
            return f"{label}:\n{message}" if message else None
        if include_tools and ptype == "token_count":
            usage = payload.get("info", {}).get("last_token_usage", {})
            total = usage.get("total_tokens")
            return f"Codex tokens: ultimo turno usou {total} tokens." if total else None
        return None

    if event_type == "response_item":
        ptype = payload.get("type")
        if include_tools and ptype == "function_call":
            name = str(payload.get("name") or "tool")
            args = summarize_tool_arguments(name, str(payload.get("arguments") or ""))
            return f"Codex ferramenta: {name}\n{args}".strip()
        if include_tools and ptype == "function_call_output":
            output = str(payload.get("output") or "").strip()
            first_lines = "\n".join(output.splitlines()[:6])
            return f"Codex ferramenta terminou:\n{first_lines[:1200]}" if first_lines else None
    return None


def read_new_codex_session_events(
    session_path: Path,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if not session_path.exists():
        raise HarnessError(f"Arquivo de sessao Codex nao encontrado: {session_path}")
    size = session_path.stat().st_size
    if offset > size:
        offset = 0
    events: list[dict[str, Any]] = []
    with session_path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        while True:
            line = handle.readline()
            if not line:
                break
            offset = handle.tell()
            event = decode_codex_session_line(line)
            if event:
                events.append(event)
    return events, offset

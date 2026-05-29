from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.codex_session import (
    decode_codex_session_line,
    mirror_message_from_codex_event,
    mirror_state_key,
    read_new_codex_session_events,
    summarize_tool_arguments,
)
from harness_core.errors import HarnessError


def test_decode_codex_session_line_ignores_invalid_json() -> None:
    assert decode_codex_session_line('{"type":"event_msg"}') == {"type": "event_msg"}
    assert decode_codex_session_line("{not-json") is None


def test_mirror_state_key_is_stable_for_path(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"

    assert mirror_state_key(path) == mirror_state_key(path)
    assert mirror_state_key(path) != mirror_state_key(tmp_path / "other.jsonl")


def test_summarize_tool_arguments_compacts_shell_command() -> None:
    summary = summarize_tool_arguments("shell_command", '{"command": "python -m pytest"}')

    assert summary == "python -m pytest"


def test_mirror_message_from_codex_event_handles_agent_and_tool_events() -> None:
    assert mirror_message_from_codex_event(
        {"type": "event_msg", "payload": {"type": "agent_message", "phase": "commentary", "message": "Oi"}},
        include_tools=False,
    ) == "Codex update:\nOi"

    assert mirror_message_from_codex_event(
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell_command", "arguments": '{"command":"ls"}'}},
        include_tools=True,
    ) == "Codex ferramenta: shell_command\nls"

    assert mirror_message_from_codex_event(
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell_command", "arguments": '{"command":"ls"}'}},
        include_tools=False,
    ) is None


def test_read_new_codex_session_events_advances_offset(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text('{"id": 1}\nnot-json\n{"id": 2}\n', encoding="utf-8")

    events, offset = read_new_codex_session_events(path, 0)

    assert events == [{"id": 1}, {"id": 2}]
    assert offset == path.stat().st_size


def test_read_new_codex_session_events_errors_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(HarnessError, match="Arquivo de sessao Codex nao encontrado"):
        read_new_codex_session_events(tmp_path / "missing.jsonl", 0)

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from harness_core import telegram_codex
from harness_core.storage import read_json, read_jsonl


def test_run_codex_for_telegram_writes_run_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(telegram_codex.time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        telegram_codex,
        "build_codex_exec_argv",
        lambda *args, **kwargs: ["codex", "exec"],
    )

    def fake_run(*args, **kwargs):
        assert kwargs["input"].endswith("Do the work")
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(telegram_codex.subprocess, "run", fake_run)

    payload = telegram_codex.run_codex_for_telegram(
        tmp_path,
        {"id": "tg-1", "prompt_text": "Do the work"},
    )

    assert payload["run_id"] == "tg-1-1000"
    assert payload["exit_code"] == 0
    assert payload["response"] == "done"
    assert Path(payload["prompt_path"]).read_text(encoding="utf-8").endswith("Do the work")
    assert read_json(tmp_path / ".harness" / "telegram" / "codex" / "tg-1-1000" / "codex-run.json")[
        "response"
    ] == "done"


def test_execute_telegram_codex_item_records_success_and_replies(monkeypatch, tmp_path: Path) -> None:
    item_path = tmp_path / "item.json"
    item = {"id": "tg-1"}
    replies = []
    monkeypatch.setattr(telegram_codex, "telegram_reply", lambda config, chat_id, text: replies.append(text))
    monkeypatch.setattr(
        telegram_codex,
        "run_codex_for_telegram",
        lambda *args, **kwargs: {
            "run_id": "run-1",
            "exit_code": 0,
            "duration_ms": 10,
            "output_path": "out.txt",
            "response": "finished",
        },
    )

    result = telegram_codex.execute_telegram_codex_item(
        tmp_path,
        {},
        item_path,
        item,
        "123",
        "prompt",
        resume_last=False,
        session_id=None,
        model=None,
        sandbox=None,
        approval=None,
        bypass=False,
        timeout=30,
        reply=True,
        start_message="starting",
        completed_action="done",
        failed_action="failed",
    )

    assert result["run_id"] == "run-1"
    assert read_json(item_path)["action"] == "done"
    assert replies == ["starting", "finished"]


def test_read_and_write_mirror_state(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text("abcdef", encoding="utf-8")

    assert telegram_codex.read_mirror_state(tmp_path, session, from_end=True) == 6
    telegram_codex.write_mirror_state(tmp_path, session, 3)
    assert telegram_codex.read_mirror_state(tmp_path, session, from_end=True) == 3


def test_queue_operator_message_writes_markdown_and_jsonl(tmp_path: Path) -> None:
    path = telegram_codex.queue_operator_message(
        tmp_path,
        {"id": "tg-1", "chat_id": "123", "message_id": 10},
        "please continue",
    )

    assert path.read_text(encoding="utf-8").count("please continue") == 1
    rows = read_jsonl(tmp_path / ".harness" / "telegram" / "operator-messages.jsonl")
    assert rows[0]["telegram_item_id"] == "tg-1"
    assert rows[0]["text"] == "please continue"

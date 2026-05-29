from __future__ import annotations

import json
from pathlib import Path

from harness_core import wmux


def test_extract_wmux_surface_id_finds_terminal_surface() -> None:
    payload = {
        "pane": {
            "surfaces": [
                {"id": "ignored", "type": "editor"},
                {"id": "surface-1", "type": "terminal"},
            ]
        }
    }

    assert wmux.extract_wmux_surface_id(payload) == "surface-1"


def test_ps_single_quote_escapes_powershell_single_quotes() -> None:
    assert wmux.ps_single_quote("C:\\Users\\O'Brien") == "'C:\\Users\\O''Brien'"


def test_wmux_send_v2_handles_pipe_error(monkeypatch) -> None:
    monkeypatch.setattr(wmux, "wmux_pipe_exchange", lambda payload: (False, "missing pipe"))

    assert wmux.wmux_send_v2("pane.list") == {
        "ok": False,
        "error": "missing pipe",
        "result": None,
    }


def test_wmux_send_v2_handles_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(wmux, "wmux_pipe_exchange", lambda payload: (True, "not-json"))

    result = wmux.wmux_send_v2("pane.list")

    assert result["ok"] is False
    assert result["error"] == "not-json"


def test_wmux_send_v2_returns_result(monkeypatch) -> None:
    def fake_exchange(payload: bytes) -> tuple[bool, str]:
        assert json.loads(payload.decode("utf-8"))["method"] == "pane.list"
        return True, json.dumps({"result": {"panes": [{"id": "pane-1"}]}})

    monkeypatch.setattr(wmux, "wmux_pipe_exchange", fake_exchange)

    assert wmux.wmux_send_v2("pane.list") == {
        "ok": True,
        "error": "",
        "result": {"panes": [{"id": "pane-1"}]},
    }


def test_collect_wmux_state_reports_unavailable_pipe(monkeypatch) -> None:
    monkeypatch.setattr(wmux, "wmux_pipe_path", lambda: r"\\.\pipe\missing")
    monkeypatch.setattr(wmux, "wmux_cli_path", lambda: "")

    state = wmux.collect_wmux_state()

    assert state["available"] is False
    assert state["pipe"] == r"\\.\pipe\missing"
    assert state["error"]


def test_wmux_new_terminal_changes_directory(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_send_v2(method: str, params: dict | None = None) -> dict:
        calls.append((method, params))
        return {
            "ok": True,
            "result": {"surface": {"surfaceId": "surface-1"}},
            "error": "",
        }

    sent_texts = []
    monkeypatch.setattr(wmux, "wmux_send_v2", fake_send_v2)
    monkeypatch.setattr(wmux, "wmux_send_text", lambda payload: sent_texts.append(payload) or {"ok": True})
    monkeypatch.setattr(wmux.time, "sleep", lambda seconds: None)

    result = wmux.wmux_new_terminal({"cwd": str(tmp_path), "direction": "right"})

    assert result["ok"] is True
    assert result["surface_id"] == "surface-1"
    assert calls == [("pane.split", {"direction": "right", "type": "terminal"})]
    assert sent_texts[0]["text"].startswith("Set-Location -LiteralPath ")

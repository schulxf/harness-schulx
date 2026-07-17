"""Focused tests for extracted security scan helpers."""

from __future__ import annotations

from pathlib import Path

from harness_core.security_scan import (
    is_probably_text,
    iter_security_inbox_files,
    iter_security_scan_files,
    scan_file_for_secrets,
)

OPENAI_KEY_SAMPLE = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz123456"


def test_binary_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"hello\0SECRET=" + OPENAI_KEY_SAMPLE.encode("ascii"))

    assert is_probably_text(path) is False
    assert scan_file_for_secrets(tmp_path, path) == []


def test_real_secret_is_found_in_text_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.env"
    path.write_text(("OPENAI_" + f"API_KEY={OPENAI_KEY_SAMPLE}\n"), encoding="utf-8")

    findings = scan_file_for_secrets(tmp_path, path)

    assert len(findings) == 1
    assert findings[0]["kind"] == "openai_key"


def test_harness_directory_is_ignored_by_default(tmp_path: Path) -> None:
    path = tmp_path / ".harness" / "state.json"
    path.parent.mkdir()
    path.write_text(f'{{"token":"{OPENAI_KEY_SAMPLE}"}}\n', encoding="utf-8")

    assert scan_file_for_secrets(tmp_path, path) == []


def test_harness_directory_can_be_scanned_when_allowed(tmp_path: Path) -> None:
    path = tmp_path / ".harness" / "inbox" / "telegram" / "message.json"
    path.parent.mkdir(parents=True)
    path.write_text(f'{{"token":"{OPENAI_KEY_SAMPLE}"}}\n', encoding="utf-8")

    findings = scan_file_for_secrets(tmp_path, path, allow_harness=True)

    assert len(findings) == 1
    assert findings[0]["path"] == ".harness/inbox/telegram/message.json"


def test_finding_format_and_redaction_are_stable(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "secrets.txt"
    path.parent.mkdir()
    path.write_text(
        "\n".join(
            [
                "safe line",
                "TOKEN=abcdefghijklmnopqrstuvwxyz123456",
            ]
        ),
        encoding="utf-8",
    )

    findings = scan_file_for_secrets(tmp_path, path)

    assert findings == [
        {
            "kind": "secret_assignment",
            "path": "nested/secrets.txt",
            "line": 2,
            "match": "TOKEN=ab...3456",
        }
    ]


def test_iter_security_scan_files_skips_harness_directory(tmp_path: Path) -> None:
    app_file = tmp_path / "app.py"
    app_file.write_text("print('ok')", encoding="utf-8")
    harness_file = tmp_path / ".harness" / "state.json"
    harness_file.parent.mkdir()
    harness_file.write_text("{}", encoding="utf-8")

    assert iter_security_scan_files(tmp_path, tracked_only=False) == [app_file]


def test_iter_security_inbox_files_returns_telegram_json_files(tmp_path: Path) -> None:
    inbox = tmp_path / ".harness" / "inbox" / "telegram"
    inbox.mkdir(parents=True)
    first = inbox / "a.json"
    second = inbox / "b.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    (inbox / "note.txt").write_text("ignored", encoding="utf-8")

    assert iter_security_inbox_files(tmp_path) == [first, second]

"""Focused tests for extracted security scan helpers."""

from __future__ import annotations

from pathlib import Path

from harness_core.security_scan import is_probably_text, scan_file_for_secrets

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

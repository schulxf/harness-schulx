from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from harness_core.errors import HarnessError
from harness_core.http import http_json_post, raise_harness_http_error


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_http_json_post_sends_json_and_accepts_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = http_json_post("https://example.test/api", {"hello": "mundo"}, timeout=7)

    assert result == {"ok": True}
    assert captured["url"] == "https://example.test/api"
    assert captured["timeout"] == 7
    assert captured["body"] == b'{"hello": "mundo"}'
    assert captured["content_type"] == "application/json"


def test_raise_harness_http_error_prefers_telegram_description() -> None:
    error = urllib.error.HTTPError(
        "https://example.test/api",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"ok": false, "description": "chat not found"}'),
    )

    with pytest.raises(HarnessError, match="HTTP 400: chat not found"):
        raise_harness_http_error(error)


def test_raise_harness_http_error_reads_nested_error_message() -> None:
    error = urllib.error.HTTPError(
        "https://example.test/api",
        500,
        "Server Error",
        {},
        io.BytesIO(b'{"error": {"message": "model unavailable"}}'),
    )

    with pytest.raises(HarnessError, match="HTTP 500: model unavailable"):
        raise_harness_http_error(error)

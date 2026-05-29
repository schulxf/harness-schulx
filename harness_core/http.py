"""HTTP helpers with Harness-friendly errors."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from harness_core.errors import HarnessError


def raise_harness_http_error(exc: urllib.error.HTTPError) -> None:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
        detail = parsed.get("description") or parsed.get("error", {}).get("message") or body
    except Exception:
        detail = body or exc.reason
    raise HarnessError(f"HTTP {exc.code}: {detail}") from exc


def open_json_request(request: urllib.request.Request, *, timeout: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise_harness_http_error(exc)
    except urllib.error.URLError as exc:
        raise HarnessError(f"Erro de rede: {exc.reason}") from exc


def http_json_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    return open_json_request(request, timeout=timeout)


def http_multipart_post(
    url: str,
    fields: dict[str, str],
    files: list[tuple[str, Path, str]],
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    boundary = f"----HarnessBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, path, content_type in files:
        chunks.append(f"--{boundary}\r\n".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\n'
        )
        chunks.append(disposition.encode("utf-8"))
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    return open_json_request(request, timeout=timeout)

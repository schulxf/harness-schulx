"""Codex exec command helpers used by Telegram bridge flows."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from harness_core.errors import HarnessError


def codex_executable() -> str:
    executable = shutil.which("codex")
    if not executable:
        raise HarnessError("codex nao encontrado no PATH.")
    return executable


def codex_prompt_from_item(item: dict[str, Any], prompt_text: str | None = None) -> str:
    text = (prompt_text if prompt_text is not None else item.get("prompt_text") or "").strip()
    media = item.get("media") or {}
    header = (
        "Mensagem recebida via Telegram pelo Harness.\n"
        f"Chat: {item.get('chat_id')}\n"
        f"Mensagem: {item.get('message_id')}\n\n"
    )
    if media.get("local_path") and media.get("local_path") not in text:
        text = f"{text}\n\nArquivo anexado salvo em: {media.get('local_path')}".strip()
    return header + (text or "Mensagem sem texto.")


def codex_image_args_from_item(item: dict[str, Any]) -> list[str]:
    media = item.get("media") or {}
    path = media.get("local_path")
    if item.get("kind") != "image" or not path:
        return []
    if not Path(path).exists():
        return []
    return ["-i", str(path)]


def build_codex_exec_argv(
    root: Path,
    output_path: Path,
    *,
    resume_last: bool = False,
    session_id: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    approval: str | None = None,
    bypass: bool = False,
    images: list[str] | None = None,
) -> list[str]:
    argv = [codex_executable(), "exec"]
    if session_id or resume_last:
        argv.append("resume")
        if resume_last:
            argv.append("--last")
        elif session_id:
            argv.append(session_id)
    else:
        argv.extend(["-C", str(root), "--skip-git-repo-check"])
        if sandbox:
            argv.extend(["-s", sandbox])
        if approval:
            argv.extend(["-a", approval])
    if model:
        argv.extend(["-m", model])
    if bypass:
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    if images:
        for image in images:
            argv.extend(["-i", image])
    argv.extend(["-o", str(output_path), "-"])
    return argv

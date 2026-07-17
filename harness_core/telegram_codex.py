"""Telegram-to-Codex execution and mirror state helpers."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.codex_exec import (
    build_codex_exec_argv,
    codex_image_args_from_item,
    codex_prompt_from_item,
)
from harness_core.codex_session import mirror_state_key
from harness_core.paths import telegram_codex_root, telegram_root
from harness_core.storage import append_jsonl, read_json, read_text, write_json, write_text
from harness_core.telegram import telegram_reply


def run_codex_for_telegram(
    root: Path,
    item: dict[str, Any],
    *,
    prompt_text: str | None = None,
    resume_last: bool = False,
    session_id: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    approval: str | None = None,
    bypass: bool = False,
    timeout: int = 1800,
) -> dict[str, Any]:
    run_id = f"{item.get('id')}-{int(time.time())}"
    run_dir = telegram_codex_root(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "last-message.txt"
    prompt = codex_prompt_from_item(item, prompt_text=prompt_text)
    prompt_path = run_dir / "prompt.txt"
    write_text(prompt_path, prompt)
    images = codex_image_args_from_item(item)
    argv = build_codex_exec_argv(
        root,
        output_path,
        resume_last=resume_last,
        session_id=session_id,
        model=model,
        sandbox=sandbox,
        approval=approval,
        bypass=bypass,
        images=images,
    )
    started = time.time()
    result = subprocess.run(
        argv,
        input=prompt,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    duration_ms = int((time.time() - started) * 1000)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    write_text(stdout_path, result.stdout or "")
    write_text(stderr_path, result.stderr or "")
    response = read_text(output_path).strip() if output_path.exists() else (result.stdout or "").strip()
    payload = {
        "run_id": run_id,
        "created_at": utc_now(),
        "duration_ms": duration_ms,
        "exit_code": result.returncode,
        "argv": argv,
        "prompt_path": str(prompt_path),
        "output_path": str(output_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "response": response,
    }
    write_json(run_dir / "codex-run.json", payload)
    return payload


def execute_telegram_codex_item(
    root: Path,
    config: dict[str, Any],
    item_path: Path,
    item: dict[str, Any],
    chat_id: str,
    prompt_text: str,
    *,
    resume_last: bool,
    session_id: str | None,
    model: str | None,
    sandbox: str | None,
    approval: str | None,
    bypass: bool,
    timeout: int,
    reply: bool,
    start_message: str,
    completed_action: str,
    failed_action: str,
    timeout_action: str | None = None,
    include_stderr_path_on_error: bool = False,
) -> dict[str, Any] | None:
    if reply:
        telegram_reply(config, chat_id, start_message)
    try:
        result = run_codex_for_telegram(
            root,
            item,
            prompt_text=prompt_text,
            resume_last=resume_last,
            session_id=session_id,
            model=model,
            sandbox=sandbox,
            approval=approval,
            bypass=bypass,
            timeout=timeout,
        )
        item["action"] = completed_action
        item["codex"] = {
            "run_id": result["run_id"],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
            "output_path": result["output_path"],
        }
        write_json(item_path, item)
        response = result.get("response") or "Codex terminou sem mensagem final."
        if result.get("exit_code") != 0:
            if include_stderr_path_on_error:
                response = (
                    f"Codex terminou com erro {result.get('exit_code')}.\n"
                    f"Veja: {result.get('stderr_path')}\n\n"
                    f"{response}"
                )
            else:
                response = f"Codex terminou com erro {result.get('exit_code')}.\n\n{response}"
        if reply:
            telegram_reply(config, chat_id, response)
        return result
    except subprocess.TimeoutExpired as exc:
        if timeout_action:
            item["action"] = timeout_action
            write_json(item_path, item)
            if reply:
                telegram_reply(config, chat_id, "Codex demorou demais e foi interrompido por timeout.")
            return None
        item["action"] = failed_action
        item["error"] = str(exc)
        write_json(item_path, item)
        if reply:
            telegram_reply(config, chat_id, f"Falha ao chamar Codex: {exc}")
        return None
    except Exception as exc:
        item["action"] = failed_action
        item["error"] = str(exc)
        write_json(item_path, item)
        if reply:
            telegram_reply(config, chat_id, f"Falha ao chamar Codex: {exc}")
        return None


def read_mirror_state(root: Path, session_path: Path, from_end: bool) -> int:
    state_path = telegram_root(root) / "mirror-state.json"
    state = read_json(state_path, {})
    key = mirror_state_key(session_path)
    if key in state:
        return int(state[key].get("offset", 0))
    return session_path.stat().st_size if from_end and session_path.exists() else 0


def write_mirror_state(root: Path, session_path: Path, offset: int) -> None:
    state_path = telegram_root(root) / "mirror-state.json"
    state = read_json(state_path, {})
    key = mirror_state_key(session_path)
    state[key] = {
        "path": str(session_path),
        "offset": offset,
        "updated_at": utc_now(),
    }
    write_json(state_path, state)


def queued_operator_messages_path(root: Path) -> Path:
    return telegram_root(root) / "operator-messages.md"


def queue_operator_message(root: Path, item: dict[str, Any], prompt_text: str) -> Path:
    path = queued_operator_messages_path(root)
    record = {
        "ts": utc_now(),
        "chat_id": item.get("chat_id"),
        "message_id": item.get("message_id"),
        "telegram_item_id": item.get("id"),
        "text": prompt_text,
    }
    append_jsonl(telegram_root(root) / "operator-messages.jsonl", record)
    existing = read_text(path) if path.exists() else "# Mensagens do operador via Telegram\n\n"
    block = (
        f"## {record['ts']} - {record['telegram_item_id']}\n\n"
        f"{prompt_text.strip() or 'Mensagem vazia.'}\n\n"
    )
    write_text(path, existing.rstrip() + "\n\n" + block)
    return path

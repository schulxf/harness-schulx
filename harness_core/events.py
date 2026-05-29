"""Harness event stream helpers."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_core.artifacts import iter_run_dirs
from harness_core.clock import utc_now
from harness_core.paths import event_stream_path
from harness_core.storage import append_jsonl, read_jsonl, read_jsonl_tail


def append_event(run_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    event = {
        "ts": utc_now(),
        "type": event_type,
        "payload": payload,
    }
    path = run_dir / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def append_harness_event(
    root: Path,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    run_dir: Path | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    source: str = "harness",
) -> dict[str, Any]:
    payload = payload or {}
    inferred_task_id = task_id or str(payload.get("task_id") or "")
    if not inferred_task_id and run_dir:
        inferred_task_id = run_dir.parent.name
    event = {
        "id": f"EVT-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "ts": utc_now(),
        "type": event_type,
        "source": source,
        "project": root.name,
        "root": str(root),
        "task_id": inferred_task_id,
        "agent_id": agent_id or str(payload.get("agent_id") or ""),
        "run_dir": str(run_dir) if run_dir else str(payload.get("run_dir") or ""),
        "payload": payload,
    }
    append_jsonl(event_stream_path(root), event)
    if run_dir:
        append_jsonl(run_dir / "events.jsonl", event)
    return event


def read_recent_harness_events(root: Path, limit: int = 40, task_id: str | None = None) -> list[dict[str, Any]]:
    events = read_jsonl(event_stream_path(root)) if task_id else read_jsonl_tail(event_stream_path(root), limit)
    if task_id:
        events = [event for event in events if event.get("task_id") == task_id]
    if not events:
        legacy: list[dict[str, Any]] = []
        for run_dir in iter_run_dirs(root):
            for event in read_jsonl(run_dir / "events.jsonl"):
                event.setdefault("run_dir", str(run_dir))
                event.setdefault("task_id", run_dir.parent.name)
                legacy.append(event)
        events = sorted(legacy, key=lambda event: str(event.get("ts") or ""))
    return events[-limit:]


def read_new_harness_events(root: Path, offset: int | None = None) -> tuple[list[dict[str, Any]], int]:
    path = event_stream_path(root)
    if not path.exists():
        return [], 0
    offset = int(offset or 0)
    events: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        handle.seek(offset)
        for raw in handle:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        new_offset = handle.tell()
    return events, new_offset


def telegram_message_from_harness_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "event")
    task_id = str(event.get("task_id") or event.get("payload", {}).get("task_id") or "-")
    project = str(event.get("project") or "Harness")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    summary = payload.get("summary") or payload.get("speech") or payload.get("message")
    if summary:
        return f"Harness: {project}\n{task_id}: {summary}"
    return f"Harness: {project}\n{task_id}: {event_type}"

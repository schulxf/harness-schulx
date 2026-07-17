"""Project memory persistence and rendering helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.paths import memory_index_path
from harness_core.storage import read_json, write_json


def next_memory_id(root: Path) -> str:
    numbers = []
    for entry in load_memory(root):
        value = str(entry.get("id", ""))
        if value.startswith("MEM-") and value[4:].isdigit():
            numbers.append(int(value[4:]))
    return f"MEM-{(max(numbers) + 1) if numbers else 1:03d}"


def load_memory(root: Path) -> list[dict[str, Any]]:
    return read_json(memory_index_path(root), [])


def save_memory(root: Path, entries: list[dict[str, Any]]) -> None:
    write_json(memory_index_path(root), entries)


def render_memory_context(root: Path, task_id: str | None = None, limit: int = 8) -> str:
    entries = load_memory(root)
    relevant = []
    for entry in reversed(entries):
        if task_id and entry.get("task_id") not in {None, "", task_id}:
            continue
        relevant.append(entry)
        if len(relevant) >= limit:
            break
    if not relevant:
        return "- Nenhuma memoria registrada ainda."
    lines = []
    for entry in relevant:
        tags = ", ".join(entry.get("tags") or [])
        suffix = f" [{tags}]" if tags else ""
        task_suffix = f" ({entry.get('task_id')})" if entry.get("task_id") else ""
        lines.append(f"- {entry.get('text', '').strip()}{task_suffix}{suffix}")
    return "\n".join(lines)

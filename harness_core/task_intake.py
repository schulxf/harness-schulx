from __future__ import annotations

from pathlib import Path
from typing import Any

from .clock import utc_now
from .events import append_harness_event
from .paths import harness_root, to_posix
from .records import TaskRecord
from .storage import write_text
from .task_store import load_tasks, next_task_id, save_tasks
from .task_text import slugify
from .telegram import render_task_body_from_telegram


def first_heading_or_filename(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def create_task(root: Path, title: str, body: str, source: str) -> TaskRecord:
    task_id = next_task_id(root)
    task_path = harness_root(root) / "tasks" / f"{task_id}-{slugify(title)}.md"
    content = (
        f"# {task_id} - {title}\n\n"
        f"Status: planejada\n"
        f"Origem: {source}\n"
        f"Criada: {utc_now()}\n\n"
        "## O que construir\n\n"
        f"{body.strip() if body.strip() else 'TODO: descrever a fatia vertical.'}\n\n"
        "## Criterios de aceite\n\n"
        "- [ ] TODO: definir comportamento observavel.\n\n"
        "## Fora de escopo\n\n"
        "- TODO: definir o que esta task nao deve alterar.\n"
    )
    write_text(task_path, content)

    task: TaskRecord = {
        "task_id": task_id,
        "title": title,
        "status": "planned",
        "source": to_posix(source) if source and source != "manual" else source,
        "task_file": to_posix(task_path.relative_to(root)),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    tasks = load_tasks(root)
    tasks.append(task)
    save_tasks(root, tasks)
    append_harness_event(root, "task_created", {"task_id": task_id, "title": title, "source": source})
    return task


def short_title(text: str, fallback: str = "Prompt do Telegram") -> str:
    from .evaluation_text import plain_clean

    for line in text.splitlines():
        cleaned = plain_clean(line)
        if cleaned:
            return cleaned[:90]
    return fallback


def create_task_from_telegram_item(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    title = short_title(item.get("prompt_text") or "", fallback=f"Telegram {item.get('id')}")
    body = render_task_body_from_telegram(item)
    return create_task(root, title, body, f"telegram:{item.get('id')}")

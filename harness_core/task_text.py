"""Task text parsing helpers."""

from __future__ import annotations

import re


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] or "untitled"


def extract_checklist(text: str) -> list[str]:
    criteria: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            heading = stripped.lower()
            in_section = (
                "acceptance" in heading
                or "criteria" in heading
                or "criterios" in heading
                or "criterio" in heading
                or "aceite" in heading
            )
            continue
        if in_section and stripped.startswith("- ["):
            item = re.sub(r"^- \[[ xX]\]\s*", "", stripped).strip()
            if item and not item.lower().startswith("todo:"):
                criteria.append(item)
    return criteria


def extract_out_of_scope(text: str) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            in_section = "out of scope" in stripped.lower() or "fora de escopo" in stripped.lower()
            continue
        if in_section and stripped.startswith("-"):
            item = stripped.lstrip("-").strip()
            if item and not item.lower().startswith("todo:"):
                items.append(item)
    return items

#!/usr/bin/env python3
"""Validate a plain-language PR body and render its automatic comment."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

COMMENT_MARKER = "<!-- harness-simple-pr-summary -->"
PTBR_ATTESTATION = re.compile(
    r"^\s*-\s*\[[xX]\]\s*Revisei\s+ortografia,\s*acentuação\s+e\s+clareza\s+"
    r"dos\s+textos\s+em\s+PT-BR\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PLACEHOLDERS = {
    "explique em poucas frases, sem termos tecnicos, o que mudou e por que.",
    "diga como voce conferiu a mudanca de forma simples.",
    "escreva nenhuma ou liste o que ainda falta.",
}


def normalize_heading(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def clean_section(value: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    return without_comments.strip()


def extract_sections(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[normalize_heading(match.group(1))] = clean_section(body[start:end])
    return sections


def required_section(sections: dict[str, str], name: str) -> str:
    value = sections.get(name, "").strip()
    if not value:
        raise ValueError(f"Preencha a seção `{name}` do PR.")
    if normalize_heading(value) in PLACEHOLDERS:
        raise ValueError(f"Substitua o texto de exemplo da seção `{name}`.")
    if len(value) > 1200:
        raise ValueError(f"Deixe a seção `{name}` mais curta e direta.")
    if "```" in value or value.count("`") > 4:
        raise ValueError(
            f"Deixe a seção `{name}` em linguagem simples; mova detalhes técnicos para outra seção."
        )
    return value


def parse_pr_body(body: str) -> dict[str, str]:
    sections = extract_sections(body or "")
    summary = required_section(sections, "resumo simples")
    checks = required_section(sections, "como conferi")
    pending = sections.get("pendencias", "Nenhuma.").strip() or "Nenhuma."
    if not PTBR_ATTESTATION.search(body or ""):
        raise ValueError(
            "Marque o checklist de PT-BR depois de revisar ortografia, acentuação e clareza."
        )
    return {"summary": summary, "checks": checks, "pending": pending}


def render_comment(summary: dict[str, str]) -> str:
    return (
        f"{COMMENT_MARKER}\n"
        "## Resumo simples\n\n"
        "### O que mudou\n\n"
        f"{summary['summary']}\n\n"
        "### Como foi conferido\n\n"
        f"{summary['checks']}\n\n"
        "### Pendências\n\n"
        f"{summary['pending']}\n\n"
        "_A ortografia, a acentuação e a clareza dos textos em PT-BR foram revisadas._\n"
    )


def pull_request_body(event: dict[str, Any]) -> str:
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ValueError("O evento não contém um pull request.")
    return str(pull_request.get("body") or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        comment = render_comment(parse_pr_body(pull_request_body(event)))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"::error title=Resumo simples do PR::{exc}", file=sys.stderr)
        return 1
    args.output.write_text(comment, encoding="utf-8", newline="\n")
    print("Resumo simples do PR validado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

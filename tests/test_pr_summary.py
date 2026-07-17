"""Tests for the plain-language PR summary policy."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "pr_summary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pr_summary", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plain_pr_summary_generates_low_jargon_comment() -> None:
    module = load_module()
    body = """## Resumo simples

Agora duas execuções simultâneas não perdem tarefas e o fechamento exige as revisões combinadas.

## Como conferi

Rodei os testes automáticos e simulei duas execuções ao mesmo tempo.

## Pendências

Nenhuma.

## Checklist

- [x] Revisei ortografia, acentuação e clareza dos textos em PT-BR.
"""

    summary = module.parse_pr_body(body)
    comment = module.render_comment(summary)

    assert "O que mudou" in comment
    assert "duas execuções simultâneas" in comment
    assert "Como foi conferido" in comment
    assert "<!-- harness-simple-pr-summary -->" in comment


def test_plain_pr_summary_rejects_missing_ptbr_attestation() -> None:
    module = load_module()
    body = """## Resumo simples

Corrige o fechamento da tarefa.

## Como conferi

Rodei os testes.

## Checklist

- [ ] Revisei ortografia, acentuação e clareza dos textos em PT-BR.
"""

    with pytest.raises(ValueError, match="PT-BR"):
        module.parse_pr_body(body)


def test_cli_reads_github_event_and_writes_comment(tmp_path: Path) -> None:
    module = load_module()
    event_path = tmp_path / "event.json"
    output_path = tmp_path / "comment.md"
    body = """## Resumo simples

O fechamento agora exige todas as revisões combinadas.

## Como conferi

Rodei os testes automáticos.

## Pendências

Nenhuma.

## Checklist

- [x] Revisei ortografia, acentuação e clareza dos textos em PT-BR.
"""
    event_path.write_text(
        json.dumps({"pull_request": {"body": body}}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert module.main(["--event", str(event_path), "--output", str(output_path)]) == 0
    assert "O fechamento agora exige" in output_path.read_text(encoding="utf-8")


def test_plain_sections_reject_code_heavy_content() -> None:
    module = load_module()
    body = """## Resumo simples

```python
print("detalhe interno")
```

## Como conferi

Rodei os testes.

## Checklist

- [x] Revisei ortografia, acentuação e clareza dos textos em PT-BR.
"""

    with pytest.raises(ValueError, match="linguagem simples"):
        module.parse_pr_body(body)

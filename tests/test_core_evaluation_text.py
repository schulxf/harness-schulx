from pathlib import Path

from harness_core.evaluation_text import (
    blocking_findings_from_review,
    extract_review_findings,
    next_fix_brief_path,
    render_fix_brief,
    render_plain_summary,
    render_plain_summary_for_message,
)


def test_extract_review_findings_detects_severities_and_cleans_text() -> None:
    findings = extract_review_findings(
        """
        - **[P0] security**: `token` leaks
        * P1 logic: fora da superficie alterada
        P2 docs: ajustar README
        """
    )

    assert findings == [
        {"severity": "P0", "text": "**[P0] security**: token leaks"},
        {"severity": "P1", "text": "P1 logic: fora da superficie alterada"},
        {"severity": "P2", "text": "P2 docs: ajustar README"},
    ]


def test_blocking_findings_default_to_p0_and_in_scope_p1() -> None:
    blockers = blocking_findings_from_review(
        """
        [P0] bug critico
        [P1] quebra no arquivo alterado
        [P2] melhoria opcional
        """,
        {},
    )

    assert [item["severity"] for item in blockers] == ["P0", "P1"]


def test_blocking_findings_respects_p2_policy() -> None:
    blockers = blocking_findings_from_review(
        "[P2] melhoria promovida a bloqueio",
        {"review_policy": {"blocking_findings": {"p2": True}}},
    )

    assert [item["severity"] for item in blockers] == ["P2"]


def test_blocking_findings_ignore_p1_outside_changed_surface() -> None:
    blockers = blocking_findings_from_review(
        "[P1] fora da superficie alterada: seria bom refatorar outro modulo",
        {},
    )

    assert blockers == []


def test_next_fix_brief_path_uses_next_numeric_suffix(tmp_path: Path) -> None:
    (tmp_path / "fix-brief-01.md").write_text("", encoding="utf-8")
    (tmp_path / "fix-brief-09.md").write_text("", encoding="utf-8")
    (tmp_path / "fix-brief-note.md").write_text("", encoding="utf-8")

    assert next_fix_brief_path(tmp_path) == tmp_path / "fix-brief-10.md"


def test_render_fix_brief_keeps_public_harness_entrypoint(tmp_path: Path) -> None:
    brief = render_fix_brief(
        tmp_path,
        {"task_id": "TASK-001"},
        {"sensor_tiers": {"quick": ["python -m pytest"], "full": ["python -m pytest"]}},
        tmp_path / ".harness" / "runs" / "TASK-001" / "run-1",
        "[P1] falha no arquivo alterado",
        "FAIL",
        {},
    )

    assert "bin" in brief
    assert "harness.py" in brief
    assert "harness_core" not in brief


def test_plain_summary_message_keeps_only_user_facing_sections() -> None:
    summary = render_plain_summary(
        {"task_id": "TASK-001", "title": "Adicionar relatorio simples"},
        {"goal": "mostrar o resultado em linguagem simples", "acceptance_criteria": ["Sem termos tecnicos"]},
        {"passed": True, "results": [{"command": "pytest", "exit_code": 0}]},
        {"status": "pass", "notes": "Tudo certo", "gaps": []},
    )
    message = render_plain_summary_for_message(summary)

    assert "O que foi feito:" in message
    assert "Resultado:" in message
    assert "O que ficou pendente:" in message
    assert "Por que foi feito" not in message

import json
import subprocess
from pathlib import Path

import pytest

from harness_core.github_pr import (
    render_github_pr_body,
    render_github_pr_comment,
    sanitize_public_pr_text,
)
from harness_core.paths import harness_root, security_root
from harness_core.storage import write_json, write_text
from harness_core.task_store import save_tasks
from tests.conftest import harness


def run(argv: list[str]) -> int:
    return harness.main(argv)


def create_passed_task(repo: Path) -> Path:
    assert run(["--repo", str(repo), "init", "--name", "test"]) == 0
    issue = repo / "issue.md"
    issue.write_text(
        "# Publicar PR\n\n## Critérios de aceite\n\n- [ ] funciona\n",
        encoding="utf-8",
    )
    assert run(["--repo", str(repo), "task", "import", str(issue)]) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "funciona",
            "--sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    ) == 0
    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0
    run_dir = next((repo / ".harness" / "runs" / "TASK-001").iterdir())
    assert run(["--repo", str(repo), "sensors", "TASK-001"]) == 0
    assert run(["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"]) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "ptbr-review",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Ortografia, acentuação e clareza conferidas.",
        ]
    ) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "evaluate",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Atende ao contrato.",
            "--review-note",
            "Nenhum achado bloqueante.",
        ]
    ) == 0
    return run_dir


def test_render_github_pr_body_uses_report_summary_and_security(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Publicar PR",
                "status": "passed",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )
    run_dir = harness_root(tmp_path) / "runs" / "TASK-001" / "run-1"
    write_json(run_dir / "run.json", {"task_id": "TASK-001"})
    write_text(run_dir / "plain-summary.md", "# Explicacao simples\n\nTudo pronto.")
    write_text(harness_root(tmp_path) / "reports" / "TASK-001.md", "# Relatório\n\nEvidência completa.")
    write_json(security_root(tmp_path) / "scan-latest.json", {"findings": [{"type": "secret"}]})

    body = render_github_pr_body(tmp_path, "TASK-001")

    assert "# TASK-001 - Publicar PR" in body
    assert "Tudo pronto." in body
    assert "- Status da tarefa: passed" in body
    assert "- Verificação de segurança: 1 achado" in body
    assert "- Relatório: `.harness/reports/TASK-001.md`" in body
    assert "Evidência completa." not in body


def test_render_github_pr_body_has_fallbacks_without_report(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Sem relatorio",
                "status": "planned",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )

    body = render_github_pr_body(tmp_path, "TASK-001")

    assert "Resumo simples ainda não gerado." in body
    assert "- Verificação de segurança: não executada" in body
    assert "- Relatório: `pendente`" in body
    assert "## Relatório completo" not in body


def test_render_github_pr_comment_sanitizes_secrets_and_raw_commands(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Publicar PR",
                "status": "passed",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )
    run_dir = harness_root(tmp_path) / "runs" / "TASK-001" / "run-1"
    write_json(run_dir / "run.json", {"task_id": "TASK-001"})
    write_text(
        run_dir / "plain-summary.md",
        """# Explicação simples

## O que foi feito

Foi trabalhada a tarefa "Publicar PR".
python -m pytest tests/test_core_github_pr.py
token = ghp_abcdefghijklmnopqrstuvwxyz123456
-----BEGIN OPENSSH PRIVATE KEY-----
abc
-----END OPENSSH PRIVATE KEY-----

## Resultado

A tarefa foi marcada como pronta.

## O que ficou pendente

- Nada ficou pendente.
""",
    )

    comment = render_github_pr_comment(tmp_path, "TASK-001")

    assert "<!-- harness-simple-pr-summary -->" in comment
    assert "Publicar PR" in comment
    assert "python -m pytest" not in comment
    assert "ghp_" not in comment
    assert "PRIVATE KEY" not in comment
    assert "[segredo redigido]" in comment


def test_render_github_pr_comment_excludes_observation_commands_and_code_blocks(tmp_path: Path) -> None:
    save_tasks(
        tmp_path,
        [
            {
                "task_id": "TASK-001",
                "title": "Publicar PR",
                "status": "passed",
                "task_file": ".harness/tasks/TASK-001.md",
            }
        ],
    )
    run_dir = harness_root(tmp_path) / "runs" / "TASK-001" / "run-1"
    write_json(run_dir / "run.json", {"task_id": "TASK-001"})
    write_text(
        run_dir / "plain-summary.md",
        """# Explicação simples

## O que foi feito

Foi trabalhada a tarefa "Publicar PR".

## Resultado

A tarefa foi marcada como pronta.

Observação simples: executei python -m pytest tests/test_core_github_pr.py e revisei detalhes internos.

- python -m pytest tests/test_core_github_pr.py
1. npm test
$ git status
PS C:\\repo> npx ruff check

```text
python -m pytest tests/test_core_github_pr.py
segredo técnico que não deve aparecer
```

## O que ficou pendente

- Nada ficou pendente.
""",
    )

    comment = render_github_pr_comment(tmp_path, "TASK-001")

    assert "Foi trabalhada" in comment
    assert "A tarefa foi marcada como pronta." in comment
    assert "Nada ficou pendente" in comment
    assert "Observação simples" not in comment
    assert "python -m pytest" not in comment
    assert "npm test" not in comment
    assert "git status" not in comment
    assert "npx ruff" not in comment
    assert "segredo técnico" not in comment


def test_sanitize_public_pr_text_removes_unclosed_fence_and_sensitive_values() -> None:
    jwt = "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12
    text = (
        "Resumo aprovado para contato@example.com.\n"
        f"Token temporário: {jwt}\n"
        "~~~powershell\n"
        "conteúdo técnico que não deve aparecer\n"
    )

    sanitized = sanitize_public_pr_text(text)

    assert "contato@example.com" not in sanitized
    assert jwt not in sanitized
    assert "conteúdo técnico" not in sanitized
    assert sanitized.count("[conteúdo sensível redigido]") == 2


def test_github_pr_create_dry_run_writes_body_and_comment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    create_passed_task(repo)

    assert run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"]) == 0

    out = capsys.readouterr().out
    github_dir = repo / ".harness" / "github"
    assert (github_dir / "TASK-001-pr-body.md").is_file()
    assert (github_dir / "TASK-001-pr-comment.md").is_file()
    assert "gh pr create" in out
    assert "gh pr comment" in out
    assert "<PR_URL>" in out
    assert "--body-file" in out


def test_github_pr_create_posts_comment_after_pr_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    create_passed_task(repo)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs):
        calls.append(argv)
        if argv[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(argv, 0, stdout="https://github.com/acme/demo/pull/7\n", stderr="")
        if argv[:3] == ["gh", "pr", "comment"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(harness.shutil, "which", lambda name: "gh" if name == "gh" else None)
    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    assert run(["--repo", str(repo), "github", "pr-create", "TASK-001"]) == 0

    out = capsys.readouterr().out
    assert calls[0][:3] == ["gh", "pr", "create"]
    assert calls[1][:3] == ["gh", "pr", "comment"]
    assert calls[1][3] == "https://github.com/acme/demo/pull/7"
    assert "--body-file" in calls[1]
    assert "PR criado: https://github.com/acme/demo/pull/7" in out
    assert "Comentário simples publicado no PR." in out


def test_github_pr_create_uses_repository_comment_automation_without_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    workflow = repo / ".github" / "workflows" / "pr-communication.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("marker: <!-- harness-simple-pr-summary -->\n", encoding="utf-8")
    create_passed_task(repo)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs):
        calls.append(argv)
        if argv[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(argv, 0, stdout="https://github.com/acme/demo/pull/9\n", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(harness.shutil, "which", lambda name: "gh" if name == "gh" else None)
    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    assert run(["--repo", str(repo), "github", "pr-create", "TASK-001"]) == 0

    out = capsys.readouterr().out
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "pr", "create"]
    assert "automação do repositório" in out


def test_github_pr_create_fails_clearly_when_comment_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    create_passed_task(repo)

    def fake_run(argv: list[str], **kwargs):
        if argv[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(argv, 0, stdout="https://github.com/acme/demo/pull/8\n", stderr="")
        if argv[:3] == ["gh", "pr", "comment"]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="comentário recusado")
        raise AssertionError(argv)

    monkeypatch.setattr(harness.shutil, "which", lambda name: "gh" if name == "gh" else None)
    monkeypatch.setattr(harness.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "github", "pr-create", "TASK-001"])

    message = str(exc.value)
    assert "https://github.com/acme/demo/pull/8" in message
    assert "comentário" in message.lower()


def test_github_pr_create_blocks_without_passed_evaluation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run(["--repo", str(repo), "init", "--name", "test"]) == 0
    issue = repo / "issue.md"
    issue.write_text("# Publicar PR\n", encoding="utf-8")
    assert run(["--repo", str(repo), "task", "import", str(issue)]) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "funciona",
            "--sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    ) == 0
    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"])

    assert "avaliação final pass" in str(exc.value).lower()


def test_github_pr_create_blocks_failure_decision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = create_passed_task(repo)
    write_json(
        run_dir / "failure-decision.json",
        {"status": "blocked", "blockers": [{"severity": "P0", "text": "Falha real."}]},
    )

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"])

    assert "failure-decision bloqueante" in str(exc.value).lower()


@pytest.mark.parametrize(
    "decision",
    [
        {"status": "clear", "blockers": [{"severity": "P1", "text": "Falha real."}]},
        {"status": "clear", "blockers": [], "evaluator_failed": True},
    ],
)
def test_github_pr_create_blocks_failure_decision_fields(tmp_path: Path, decision: dict[str, object]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = create_passed_task(repo)
    write_json(run_dir / "failure-decision.json", decision)

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"])

    assert "failure-decision bloqueante" in str(exc.value).lower()


def test_github_pr_create_blocks_latest_reviewer_result_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = create_passed_task(repo)
    write_text(run_dir / "greptile-reviewer-result-01.md", "[P0] achado antigo")
    write_text(run_dir / "reviewer-result-02.md", "[P1] quebra na superfície alterada")

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"])

    assert "resultado final do reviewer" in str(exc.value).lower()
    assert "P1" in str(exc.value)


def test_github_pr_create_ignores_elapsed_time_after_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = create_passed_task(repo)
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["created_at"] = "2000-01-01T00:00:00+00:00"
    metadata["budget"]["time_budget_minutes"] = 1
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    assert run(["--repo", str(repo), "github", "pr-create", "TASK-001", "--dry-run"]) == 0

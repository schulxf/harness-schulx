"""Regression tests for evidence and persistence guarantees."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import harness

HARNESS_PY = Path(__file__).resolve().parents[1] / "bin" / "harness.py"


def run(argv: list[str]) -> int:
    return harness.main(argv)


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run(["--repo", str(repo), "init", "--name", "test"]) == 0
    return repo


def create_started_task(repo: Path, *, sensor: str = "python -c pass") -> Path:
    issue = repo / "issue.md"
    issue.write_text(
        "# Ajuste\n\n## Critérios de aceite\n\n- [ ] funciona\n",
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
            sensor,
            "--reviewed-sensors",
        ]
    ) == 0
    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0
    return next((repo / ".harness" / "runs" / "TASK-001").iterdir())


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def test_parallel_task_creation_keeps_every_task_and_unique_id(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                str(HARNESS_PY),
                "--repo",
                str(repo),
                "task",
                "create",
                f"Tarefa {number}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for number in range(24)
    ]
    results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]

    assert all(returncode == 0 for _, _, returncode in results), results
    tasks = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )
    assert len(tasks) == 24
    assert len({task["task_id"] for task in tasks}) == 24
    assert len(list((repo / ".harness" / "tasks").glob("TASK-*.md"))) == 24


def test_two_starts_create_distinct_runs(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    create_started_task(repo)

    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0

    runs = list((repo / ".harness" / "runs" / "TASK-001").iterdir())
    assert len(runs) == 2
    assert len({path.name for path in runs}) == 2


def test_evaluator_brief_keeps_committed_changes_since_run_start(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    git(repo, "init")
    git(repo, "config", "user.email", "harness@example.com")
    git(repo, "config", "user.name", "Harness Tests")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    git(repo, "switch", "-c", "feature/evidence")

    run_dir = create_started_task(repo)
    baseline = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["base_commit"]
    assert baseline == git(repo, "rev-parse", "HEAD")

    changed = repo / "app.txt"
    changed.write_text("mudança implementada\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "implement change")

    assert run(["--repo", str(repo), "evaluate", "TASK-001"]) == 0
    brief = (run_dir / "evaluator-brief.md").read_text(encoding="utf-8")
    assert "app.txt" in brief
    assert baseline in brief


def test_surface_digest_ignores_harness_evidence_but_tracks_source(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    git(repo, "init")
    git(repo, "config", "user.email", "harness@example.com")
    git(repo, "config", "user.name", "Harness Tests")
    (repo / "app.txt").write_text("v1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    initial = harness.source_surface_digest(repo)

    (repo / ".harness" / "progress.md").write_text("evidência nova\n", encoding="utf-8")
    assert harness.source_surface_digest(repo) == initial

    (repo / "app.txt").write_text("v2\n", encoding="utf-8")
    assert harness.source_surface_digest(repo) != initial


def test_queue_done_cannot_bypass_task_approval(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# Ajuste\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "queue", "add", "TASK-001"])
    queue_id = json.loads(
        (repo / ".harness" / "queue" / "index.json").read_text(encoding="utf-8")
    )[0]["id"]

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "queue", "done", queue_id])

    assert "pass" in str(exc.value).lower()
    task = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )[0]
    queue_item = json.loads(
        (repo / ".harness" / "queue" / "index.json").read_text(encoding="utf-8")
    )[0]
    assert task["status"] == "planned"
    assert queue_item["status"] == "queued"


def test_contract_review_does_not_approve_a_different_sensor_command(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    run_dir = create_started_task(repo)

    assert run(
        [
            "--repo",
            str(repo),
            "sensors",
            "TASK-001",
            "--command",
            "python -c pass",
        ]
    ) == 0

    with pytest.raises(SystemExit) as exc:
        run(
            [
                "--repo",
                str(repo),
                "sensors",
                "TASK-001",
                "--command",
                "python -c 1",
            ]
        )
    assert "revis" in str(exc.value).lower()

    assert run(
        [
            "--repo",
            str(repo),
            "sensors",
            "TASK-001",
            "--command",
            "python -c 1",
            "--reviewed",
        ]
    ) == 0
    payload = json.loads((run_dir / "sensors-full.json").read_text(encoding="utf-8"))
    assert payload["review_digest"]
    assert payload["review_digest"] != json.loads(
        (repo / ".harness" / "contracts" / "TASK-001.json").read_text(encoding="utf-8")
    )["sensor_review"]["digest"]


def test_pass_requires_clean_security_ptbr_review_and_code_review(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    run_dir = create_started_task(repo)
    assert run(["--repo", str(repo), "sensors", "TASK-001"]) == 0
    assert run(
        ["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"]
    ) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "ptbr-review",
            "TASK-001",
            "--status",
            "pass",
            "--reviewer",
            "revisor",
            "--notes",
            "Ortografia, acentuação e clareza conferidas.",
        ]
    ) == 0

    with pytest.raises(SystemExit) as exc:
        run(
            [
                "--repo",
                str(repo),
                "evaluate",
                "TASK-001",
                "--status",
                "pass",
                "--notes",
                "Tudo certo.",
            ]
        )
    assert "review" in str(exc.value).lower()

    assert run(
        [
            "--repo",
            str(repo),
            "evaluate",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Tudo certo.",
            "--review-note",
            "Nenhum achado bloqueante.",
        ]
    ) == 0
    assert (run_dir / "ptbr-review.json").is_file()
    assert (run_dir / "security-scan.json").is_file()
    assert (run_dir / "code-review.json").is_file()
    pr_body = harness.render_github_pr_body(repo, "TASK-001")
    assert "## Resumo simples" in pr_body
    assert "## Como conferi" in pr_body
    assert "## Pendências" in pr_body
    assert "- [x] Revisei ortografia, acentuação e clareza" in pr_body


def test_blocking_code_review_finding_prevents_pass(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    create_started_task(repo)
    run(["--repo", str(repo), "sensors", "TASK-001"])
    run(["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"])
    run(
        [
            "--repo",
            str(repo),
            "ptbr-review",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Revisado.",
        ]
    )

    with pytest.raises(SystemExit) as exc:
        run(
            [
                "--repo",
                str(repo),
                "evaluate",
                "TASK-001",
                "--status",
                "pass",
                "--review-note",
                "**[P1] logic - app.py:1** Regressão real.",
            ]
        )
    assert "p1" in str(exc.value).lower()


def test_security_scan_only_fails_when_requested(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "secret.txt").write_text(
        "token = " + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )

    assert run(["--repo", str(repo), "security", "scan"]) == 0
    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "security", "scan", "--fail-on-findings"])
    assert exc.value.code == 1


def test_task_security_scan_includes_untracked_source_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    git(repo, "init")
    git(repo, "config", "user.email", "harness@example.com")
    git(repo, "config", "user.name", "Harness Tests")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "baseline")
    git(repo, "switch", "-c", "feature/security")
    run_dir = create_started_task(repo)
    (repo / "new-code.py").write_text(
        "GITHUB_TOKEN = '" + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456'\n",
        encoding="utf-8",
    )

    assert run(
        ["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"]
    ) == 0
    report = json.loads((run_dir / "security-scan.json").read_text(encoding="utf-8"))
    assert report["tracked_only"] is False
    assert any(finding["path"] == "new-code.py" for finding in report["findings"])


def test_queue_profile_is_propagated_to_linked_task(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# Ajuste\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])

    run(["--repo", str(repo), "queue", "add", "TASK-001", "--profile", "strict"])

    task = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )[0]
    assert task["budget"]["profile"] == "strict"


def test_time_budget_is_enforced_before_pass(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    run_dir = create_started_task(repo)
    run(["--repo", str(repo), "sensors", "TASK-001"])
    run(["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"])
    run(
        [
            "--repo",
            str(repo),
            "ptbr-review",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Revisado.",
        ]
    )
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["created_at"] = "2000-01-01T00:00:00+00:00"
    metadata["budget"]["time_budget_minutes"] = 1
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        run(
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
        )
    assert "orçamento" in str(exc.value).lower()


def test_source_change_invalidates_completion_evidence(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    create_started_task(repo)
    run(["--repo", str(repo), "sensors", "TASK-001"])
    run(["--repo", str(repo), "security", "scan", "--task-id", "TASK-001"])
    run(
        [
            "--repo",
            str(repo),
            "ptbr-review",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "Revisado.",
        ]
    )
    (repo / "issue.md").write_text("# Ajuste alterado depois das revisões\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        run(
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
        )

    message = str(exc.value).lower()
    assert "mudou depois" in message or "mudaram depois" in message

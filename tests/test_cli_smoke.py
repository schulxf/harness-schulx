"""End-to-end smoke tests using tmp_path as a fake repo."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import harness


def run(argv):
    """Invoke harness.main(argv) and return its exit code."""
    return harness.main(argv)


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run(["--repo", str(repo), "init", "--name", "test"]) == 0
    return repo


def record_completion_reviews(repo: Path) -> None:
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
            "--notes",
            "Ortografia, acentuação e clareza conferidas.",
        ]
    ) == 0


def test_init_creates_layout(tmp_path):
    repo = init_repo(tmp_path)
    h = repo / ".harness"
    for sub in ["context", "tasks", "contracts", "runs", "evaluations", "reports"]:
        assert (h / sub).is_dir(), sub
    assert (h / "telegram").is_dir()
    assert (h / "inbox" / "telegram" / "media").is_dir()
    assert (h / "config.json").is_file()
    assert (h / ".gitignore").is_file()
    assert (h / "progress.md").is_file()

    config = json.loads((h / "config.json").read_text(encoding="utf-8"))
    assert config["project_name"] == "test"
    assert config["telegram"]["enabled"] is False
    # Every configured policy below is enforced by a command gate.
    assert set(config["policy"].keys()) == {
        "context_preflight_required_before_start",
        "record_evidence_before_done",
        "cache_context_preflight",
        "security_scan_required_before_done",
        "ptbr_review_required_before_done",
        "review_evidence_required_before_done",
        "budget_required_before_done",
    }


def test_init_refuses_missing_dir_without_create(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SystemExit):
        run(["--repo", str(missing), "init"])


def test_init_with_create_makes_dir(tmp_path):
    target = tmp_path / "new"
    assert run(["--repo", str(target), "init", "--create"]) == 0
    assert (target / ".harness" / "config.json").is_file()


def test_task_import_then_list_and_pick(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issues" / "001-login.md"
    issue.parent.mkdir()
    issue.write_text(
        "# Login por email e senha\n\n"
        "## Criterios de aceite\n\n"
        "- [ ] Usuario valido autentica.\n"
        "- [ ] Senha invalida mostra erro claro.\n\n"
        "## Fora de escopo\n\n"
        "- OAuth.\n",
        encoding="utf-8",
    )
    assert run(["--repo", str(repo), "task", "import", str(issue)]) == 0
    index = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )
    assert len(index) == 1
    assert index[0]["task_id"] == "TASK-001"
    assert index[0]["title"] == "Login por email e senha"
    assert index[0]["status"] == "planned"


def test_contract_extracts_criteria_and_out_of_scope(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text(
        "# Login\n\n## Criterios de aceite\n\n- [ ] login funciona\n\n"
        "## Fora de escopo\n\n- OAuth\n",
        encoding="utf-8",
    )
    run(["--repo", str(repo), "task", "import", str(issue)])
    assert run(["--repo", str(repo), "contract", "TASK-001"]) == 0
    contract = json.loads(
        (repo / ".harness" / "contracts" / "TASK-001.json").read_text(encoding="utf-8")
    )
    assert "login funciona" in contract["acceptance_criteria"]
    assert "OAuth" in contract["out_of_scope"]
    assert contract["sensors_reviewed"] is False


def test_preflight_passes_without_required_context(tmp_path):
    repo = init_repo(tmp_path)
    assert run(["--repo", str(repo), "preflight"]) == 0


def test_preflight_fails_when_required_doc_missing(tmp_path):
    repo = init_repo(tmp_path)
    config_path = repo / ".harness" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["required_context"] = [{"path": "AGENTS.md", "kind": "context"}]
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "preflight"])
    assert exc.value.code == 1


def test_preflight_detects_source_changed(tmp_path):
    repo = init_repo(tmp_path)
    doc = repo / "AGENTS.md"
    doc.write_text("v1", encoding="utf-8")
    config_path = repo / ".harness" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["required_context"] = [{"path": "AGENTS.md", "kind": "context"}]
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    assert run(
        ["--repo", str(repo), "ingest", str(doc), "--kind", "context"]
    ) == 0
    assert run(["--repo", str(repo), "preflight"]) == 0

    doc.write_text("v2", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(["--repo", str(repo), "preflight"])

    # Re-ingesting brings preflight back to pass.
    assert run(
        ["--repo", str(repo), "ingest", str(doc), "--kind", "context"]
    ) == 0
    assert run(["--repo", str(repo), "preflight"]) == 0


def test_ingest_rejects_paths_outside_repo(tmp_path):
    repo = init_repo(tmp_path)
    outsider = tmp_path / "outside.md"
    outsider.write_text("nope", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "ingest", str(outsider), "--kind", "context"])
    assert "fora do repo" in str(exc.value)


def test_start_creates_run_and_brief(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text(
        "# X\n\n## Criterios de aceite\n\n- [ ] funciona\n",
        encoding="utf-8",
    )
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001"])
    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0
    runs_dir = repo / ".harness" / "runs" / "TASK-001"
    runs = list(runs_dir.iterdir())
    assert len(runs) == 1
    assert runs[0].name.startswith("run-") and runs[0].name.endswith("Z")
    assert (runs[0] / "builder-brief.md").is_file()
    assert (runs[0] / "run.json").is_file()


def test_sensors_require_review(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    # Inject a sensor that should always succeed: python -c pass
    assert run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--sensor",
            "python -c pass",
        ]
    ) == 0
    run(["--repo", str(repo), "start", "TASK-001"])
    with pytest.raises(SystemExit):
        run(["--repo", str(repo), "sensors", "TASK-001"])


def test_sensors_run_when_reviewed_and_record_pass(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    )
    run(["--repo", str(repo), "start", "TASK-001"])
    assert run(["--repo", str(repo), "sensors", "TASK-001"]) == 0
    runs_dir = repo / ".harness" / "runs" / "TASK-001"
    run_dir = next(runs_dir.iterdir())
    sensors_payload = json.loads(
        (run_dir / "sensors.json").read_text(encoding="utf-8")
    )
    assert sensors_payload["passed"] is True
    assert sensors_payload["results"][0]["exit_code"] == 0


def test_sensor_tiers_quick_and_full_outputs(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--smoke-sensor",
            "python -c pass",
            "--full-sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    )
    run(["--repo", str(repo), "start", "TASK-001"])
    assert run(["--repo", str(repo), "sensors", "TASK-001", "--tier", "quick"]) == 0
    run_dir = next((repo / ".harness" / "runs" / "TASK-001").iterdir())
    assert (run_dir / "sensors-smoke.json").is_file()
    assert run(["--repo", str(repo), "sensors", "TASK-001", "--tier", "full"]) == 0
    assert (run_dir / "sensors-full.json").is_file()


def test_evaluate_pass_requires_full_tier_when_configured(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--smoke-sensor",
            "python -c pass",
            "--full-sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    )
    run(["--repo", str(repo), "start", "TASK-001"])
    run(["--repo", str(repo), "sensors", "TASK-001", "--tier", "quick"])
    with pytest.raises(SystemExit):
        run(["--repo", str(repo), "evaluate", "TASK-001", "--status", "pass", "--notes", "ok"])
    run(["--repo", str(repo), "sensors", "TASK-001", "--tier", "full"])
    record_completion_reviews(repo)
    assert run(
        [
            "--repo",
            str(repo),
            "evaluate",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "ok",
            "--review-note",
            "Nenhum achado bloqueante.",
        ]
    ) == 0


def test_evaluate_pass_requires_passing_sensors(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    # Cross-platform "always fails": a python file that exits non-zero.
    failer = repo / "failer.py"
    failer.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--sensor",
            f"python {failer}",
            "--reviewed-sensors",
        ]
    )
    run(["--repo", str(repo), "start", "TASK-001"])
    run(["--repo", str(repo), "sensors", "TASK-001"])
    sensors_payload = json.loads(
        next(
            (repo / ".harness" / "runs" / "TASK-001").iterdir()
        ).joinpath("sensors.json").read_text(encoding="utf-8")
    )
    assert sensors_payload["passed"] is False, sensors_payload

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
                "no",
            ]
        )
    assert "sensores" in str(exc.value).lower()


def test_evaluate_pass_blocked_when_no_sensors(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])
    with pytest.raises(SystemExit):
        run(
            [
                "--repo",
                str(repo),
                "evaluate",
                "TASK-001",
                "--status",
                "pass",
                "--notes",
                "no",
            ]
        )


def test_evaluate_brief_and_handoffs_generated(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])
    assert run(["--repo", str(repo), "evaluate", "TASK-001"]) == 0
    runs_dir = repo / ".harness" / "runs" / "TASK-001"
    run_dir = next(runs_dir.iterdir())
    for f in [
        "evaluator-brief.md",
        "evaluator-agent-handoff.md",
        "greptile-reviewer-agent-handoff.md",
        "review-consolidation.md",
        "parallel-dispatch.md",
    ]:
        assert (run_dir / f).is_file(), f

    handoff = (run_dir / "greptile-reviewer-agent-handoff.md").read_text(
        encoding="utf-8"
    )
    # The earlier `$skill` bug would leave a literal "$greptile-review" in the text.
    assert "$greptile-review" not in handoff
    assert "greptile-review" in handoff


def test_evaluate_fail_marks_task_failed_distinct_from_needs_work(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])
    assert run(
        ["--repo", str(repo), "evaluate", "TASK-001", "--status", "fail", "--notes", "n"]
    ) == 0
    tasks = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )
    assert tasks[0]["status"] == "failed"

    # Now needs-work should map to a distinct status.
    assert run(
        [
            "--repo",
            str(repo),
            "evaluate",
            "TASK-001",
            "--status",
            "needs-work",
            "--notes",
            "n",
        ]
    ) == 0
    tasks = json.loads(
        (repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8")
    )
    assert tasks[0]["status"] == "needs_work"


def test_fix_brief_from_reviewer_note_marks_needs_work(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])
    assert run(
        [
            "--repo",
            str(repo),
            "fix-brief",
            "TASK-001",
            "--review-note",
            "**[P0] security - app.py:1** Falha critica.",
        ]
    ) == 0
    run_dir = next((repo / ".harness" / "runs" / "TASK-001").iterdir())
    assert (run_dir / "fix-brief-01.md").is_file()
    assert "P0" in (run_dir / "fix-brief-latest.md").read_text(encoding="utf-8")
    tasks = json.loads((repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8"))
    assert tasks[0]["status"] == "needs_work"


def test_run_id_uses_utc(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])
    runs_dir = repo / ".harness" / "runs" / "TASK-001"
    run_dir = next(runs_dir.iterdir())
    # New format: run-YYYYMMDDTHHMMSSZ
    assert run_dir.name.endswith("Z"), run_dir.name
    assert "T" in run_dir.name, run_dir.name


def test_report_renders_after_full_flow(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# X\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(
        [
            "--repo",
            str(repo),
            "contract",
            "TASK-001",
            "--criteria",
            "ok",
            "--sensor",
            "python -c pass",
            "--reviewed-sensors",
        ]
    )
    run(["--repo", str(repo), "start", "TASK-001"])
    run(["--repo", str(repo), "sensors", "TASK-001"])
    record_completion_reviews(repo)
    run(
        [
            "--repo",
            str(repo),
            "evaluate",
            "TASK-001",
            "--status",
            "pass",
            "--notes",
            "ok",
            "--review-note",
            "Nenhum achado bloqueante.",
        ]
    )
    assert run(["--repo", str(repo), "report", "TASK-001"]) == 0
    report = (repo / ".harness" / "reports" / "TASK-001.md").read_text(encoding="utf-8")
    run_dir = next((repo / ".harness" / "runs" / "TASK-001").iterdir())
    plain_summary = (run_dir / "plain-summary.md").read_text(encoding="utf-8")
    assert "Relatorio do Harness - TASK-001" in report
    assert "Explicacao simples" in report
    assert "O que foi feito" in plain_summary
    assert "Status: pass" in report


def test_telegram_configure_updates_config(tmp_path):
    repo = init_repo(tmp_path)
    assert run(
        [
            "--repo",
            str(repo),
            "telegram",
            "configure",
            "--enable",
            "--chat-id",
            "123",
            "--allowed-chat-id",
            "123",
            "--allow-remote-execution",
            "--openai-media",
        ]
    ) == 0
    config = json.loads((repo / ".harness" / "config.json").read_text(encoding="utf-8"))
    assert config["telegram"]["enabled"] is True
    assert config["telegram"]["chat_ids"] == ["123"]
    assert config["telegram"]["allowed_chat_ids"] == ["123"]
    assert config["telegram"]["allow_remote_execution"] is True
    assert config["telegram"]["openai_media"]["enabled"] is True


def test_telegram_text_update_saves_inbox(tmp_path):
    repo = init_repo(tmp_path)
    config = harness.load_config(repo)
    config["telegram"]["allowed_chat_ids"] = ["123"]
    path = harness.handle_telegram_update(
        repo,
        config,
        {
            "update_id": 10,
            "message": {
                "message_id": 20,
                "chat": {"id": 123},
                "from": {"id": 123, "first_name": "Tester"},
                "text": "Criar tela de relatorio simples",
            },
        },
        reply=False,
    )
    assert path and path.exists()
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["prompt_text"] == "Criar tela de relatorio simples"
    assert item["action"] == "inbox_saved"
    assert "raw_update" not in item
    assert item["raw_update_metadata"]["update_id"] == 10


def test_telegram_update_from_unlisted_chat_is_rejected(tmp_path):
    repo = init_repo(tmp_path)
    config = harness.load_config(repo)
    path = harness.handle_telegram_update(
        repo,
        config,
        {
            "update_id": 12,
            "message": {
                "message_id": 22,
                "chat": {"id": 999},
                "from": {"id": 999, "first_name": "Stranger"},
                "text": "Abrir acesso",
            },
        },
        reply=False,
    )
    assert path and path.exists()
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["action"] == "rejected_chat"
    assert "text" not in item


def test_telegram_codex_requires_remote_execution_flag(tmp_path, monkeypatch):
    repo = init_repo(tmp_path)
    config = harness.load_config(repo)
    config["telegram"]["chat_ids"] = ["123"]
    config["telegram"]["allowed_chat_ids"] = ["123"]
    harness.write_json(repo / ".harness" / "config.json", config)
    monkeypatch.setenv("HARNESS_TELEGRAM_BOT_TOKEN", "telegram-test-token")

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "telegram", "codex", "--once"])

    assert "Execucao remota via Telegram esta desligada" in str(exc.value)


def test_telegram_bridge_codex_exec_requires_remote_execution_flag(tmp_path, monkeypatch):
    repo = init_repo(tmp_path)
    config = harness.load_config(repo)
    config["telegram"]["chat_ids"] = ["123"]
    config["telegram"]["allowed_chat_ids"] = ["123"]
    harness.write_json(repo / ".harness" / "config.json", config)
    monkeypatch.setenv("HARNESS_TELEGRAM_BOT_TOKEN", "telegram-test-token")

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "telegram", "bridge", "--send-mode", "codex-exec", "--once"])

    assert "Modo codex-exec bloqueado" in str(exc.value)


def test_telegram_new_command_creates_task_without_reply(tmp_path):
    repo = init_repo(tmp_path)
    config = harness.load_config(repo)
    config["telegram"]["allowed_chat_ids"] = ["123"]
    path = harness.handle_telegram_update(
        repo,
        config,
        {
            "update_id": 11,
            "message": {
                "message_id": 21,
                "chat": {"id": 123},
                "from": {"id": 123, "first_name": "Tester"},
                "text": "/new Criar exportacao CSV",
            },
        },
        reply=False,
    )
    assert path and path.exists()
    item = json.loads(path.read_text(encoding="utf-8"))
    tasks = json.loads((repo / ".harness" / "tasks" / "index.json").read_text(encoding="utf-8"))
    assert item["action"] == "task_created"
    assert item["created_task_id"] == "TASK-001"
    assert tasks[0]["title"] == "Criar exportacao CSV"

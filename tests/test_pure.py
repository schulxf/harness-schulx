"""Tests for pure helper functions in harness.py."""
from __future__ import annotations

import json
import re

import pytest

from tests.conftest import harness


def test_slugify_basic():
    assert harness.slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation_and_collapses():
    assert harness.slugify("  Foo!!! Bar  --  Baz  ") == "foo-bar-baz"


def test_slugify_empty_returns_untitled():
    assert harness.slugify("   ") == "untitled"
    assert harness.slugify("!!!") == "untitled"


def test_slugify_truncates_to_80():
    out = harness.slugify("x" * 200)
    assert len(out) == 80
    assert out == "x" * 80


def test_utc_now_format():
    now = harness.utc_now()
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$", now), now


def test_extract_checklist_picks_up_items_under_aceite():
    text = (
        "# Task\n\n"
        "## Criterios de aceite\n\n"
        "- [ ] Usuario valido autentica.\n"
        "- [x] Senha invalida mostra erro.\n"
        "- [ ] TODO: ignorar isto.\n\n"
        "## Fora de escopo\n\n"
        "- [ ] OAuth (nao deve entrar)\n"
    )
    criteria = harness.extract_checklist(text)
    assert criteria == [
        "Usuario valido autentica.",
        "Senha invalida mostra erro.",
    ]


def test_extract_checklist_returns_empty_when_no_section():
    assert harness.extract_checklist("# Task\n\nNo sections here.\n") == []


def test_extract_out_of_scope():
    text = (
        "# Task\n\n"
        "## Fora de escopo\n\n"
        "- OAuth\n"
        "- TODO: skip me\n"
        "- Billing\n"
    )
    assert harness.extract_out_of_scope(text) == ["OAuth", "Billing"]


def test_extract_out_of_scope_english_heading():
    text = "# Task\n\n## Out of scope\n\n- Telemetry\n"
    assert harness.extract_out_of_scope(text) == ["Telemetry"]


def test_first_heading_or_filename_uses_first_heading(tmp_path):
    file = tmp_path / "001-login.md"
    file.write_text("# Login flow\n\nbody\n", encoding="utf-8")
    assert (
        harness.first_heading_or_filename(file, file.read_text(encoding="utf-8"))
        == "Login flow"
    )


def test_first_heading_or_filename_falls_back_to_filename(tmp_path):
    file = tmp_path / "some-task_name.md"
    file.write_text("no heading here\n", encoding="utf-8")
    assert (
        harness.first_heading_or_filename(file, file.read_text(encoding="utf-8"))
        == "Some Task Name"
    )


def test_config_bool_truthy_values():
    for value in [True, "true", "True", "1", "yes", "on"]:
        assert harness.config_bool(value) is True


def test_config_bool_falsy_values():
    for value in [False, "false", "0", "no", "off"]:
        assert harness.config_bool(value) is False


def test_config_bool_none_uses_default():
    assert harness.config_bool(None, default=True) is True
    assert harness.config_bool(None, default=False) is False


def test_evaluation_policy_merges_with_defaults():
    config = {"evaluation_policy": {"mode": "inline"}}
    policy = harness.evaluation_policy(config)
    assert policy["mode"] == "inline"
    assert policy["fork_context"] is False
    assert policy["input_scope"] == "evaluator_agent_handoff"


def test_review_policy_merges_blocking_findings():
    config = {"review_policy": {"blocking_findings": {"p2": True}}}
    policy = harness.review_policy(config)
    assert policy["blocking_findings"]["p0"] is True
    assert policy["blocking_findings"]["p1_in_changed_surface"] is True
    assert policy["blocking_findings"]["p2"] is True
    assert policy["skill"] == "greptile-review"


def test_telegram_config_merges_defaults():
    config = {"telegram": {"enabled": True, "openai_media": {"enabled": True}}}
    policy = harness.telegram_config(config)
    assert policy["enabled"] is True
    assert policy["token_env"] == "HARNESS_TELEGRAM_BOT_TOKEN"
    assert policy["openai_media"]["enabled"] is True
    assert policy["openai_media"]["audio_model"]


def test_telegram_allowlist_fails_closed_and_remote_execution_is_explicit():
    assert harness.telegram_chat_allowed({"telegram": {}}, "123") is False
    assert harness.telegram_chat_allowed({"telegram": {"chat_ids": ["123"]}}, "123") is True
    assert (
        harness.telegram_chat_allowed(
            {"telegram": {"chat_ids": ["123"], "allowed_chat_ids": ["456"]}},
            "123",
        )
        is False
    )
    assert (
        harness.telegram_chat_allowed(
            {"telegram": {"chat_ids": ["123"], "allowed_chat_ids": ["456"]}},
            "456",
        )
        is True
    )
    assert harness.telegram_remote_execution_allowed({"telegram": {"chat_ids": ["123"]}}) is False
    assert (
        harness.telegram_remote_execution_allowed(
            {"telegram": {"allow_remote_execution": True, "allowed_chat_ids": ["123"]}}
        )
        is True
    )


def test_hub_action_auth_requires_loopback_and_token():
    assert harness.hub_local_request_allowed("127.0.0.1") is True
    assert harness.hub_local_request_allowed("192.168.0.10") is False
    assert harness.hub_action_authorized("127.0.0.1", "token", "token") is True
    assert harness.hub_action_authorized("127.0.0.1", "", "token") is False
    assert harness.hub_action_authorized("192.168.0.10", "token", "token") is False


def test_read_jsonl_tail_reads_only_recent_records(tmp_path):
    path = tmp_path / "events.jsonl"
    for index in range(20):
        harness.append_jsonl(path, {"index": index})

    assert [item["index"] for item in harness.read_jsonl_tail(path, 3)] == [17, 18, 19]


def test_render_plain_summary_is_nontechnical():
    summary = harness.render_plain_summary(
        {"task_id": "TASK-001", "title": "Login"},
        {
            "goal": "Permitir entrada com email e senha.",
            "acceptance_criteria": ["Usuario valido entra."],
        },
        {"passed": True, "results": [{"command": "python -m pytest", "exit_code": 0}]},
        {"status": "pass", "notes": "Tudo certo.", "gaps": []},
    )
    assert "Explicacao simples" in summary
    assert "O que foi feito" in summary
    assert "conferencias automaticas passaram" in summary
    assert "Nada ficou pendente" in summary


def test_build_codex_exec_argv_new_session(monkeypatch, tmp_path):
    monkeypatch.setattr(harness.shutil, "which", lambda _: "codex")
    out = tmp_path / "out.txt"
    argv = harness.build_codex_exec_argv(
        tmp_path,
        out,
        model="gpt-5",
        sandbox="workspace-write",
        approval="never",
        images=["image.png"],
    )
    assert argv[:4] == ["codex", "exec", "-C", str(tmp_path)]
    assert "--skip-git-repo-check" in argv
    assert ["-m", "gpt-5"] == argv[argv.index("-m") : argv.index("-m") + 2]
    assert ["-i", "image.png"] == argv[argv.index("-i") : argv.index("-i") + 2]
    assert argv[-2:] == [str(out), "-"]


def test_build_codex_exec_argv_resume_last(monkeypatch, tmp_path):
    monkeypatch.setattr(harness.shutil, "which", lambda _: "codex")
    out = tmp_path / "out.txt"
    argv = harness.build_codex_exec_argv(tmp_path, out, resume_last=True)
    assert argv[:4] == ["codex", "exec", "resume", "--last"]
    assert "-C" not in argv
    assert argv[-2:] == [str(out), "-"]


def test_mirror_message_from_agent_event():
    event = {
        "type": "event_msg",
        "payload": {
            "type": "agent_message",
            "phase": "commentary",
            "message": "Trabalhando na task.",
        },
    }
    assert harness.mirror_message_from_codex_event(event, include_tools=False) == (
        "Codex update:\nTrabalhando na task."
    )


def test_mirror_message_from_tool_call_when_enabled():
    event = {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "shell_command",
            "arguments": json.dumps({"command": "npm test"}),
        },
    }
    assert harness.mirror_message_from_codex_event(event, include_tools=True) == (
        "Codex ferramenta: shell_command\nnpm test"
    )
    assert harness.mirror_message_from_codex_event(event, include_tools=False) is None


def test_sensor_tiers_include_legacy_full():
    contract = {"required_sensors": ["npm test"]}
    tiers = harness.normalize_sensor_tiers(contract)
    assert tiers["smoke"] == []
    assert tiers["affected"] == []
    assert tiers["full"] == ["npm test"]
    assert harness.sensors_for_tier(contract, "all") == ["npm test"]


def test_blocking_findings_from_review_detects_p0_p1():
    text = "**[P0] security - app.py:1**\n**[P1] logic - app.py:2**\n**[P2] style - app.py:3**"
    blockers = harness.blocking_findings_from_review(text, {})
    assert [item["severity"] for item in blockers] == ["P0", "P1"]


def test_render_evaluation_markdown_with_gaps():
    evaluation = {
        "task_id": "TASK-001",
        "status": "fail",
        "created_at": "2026-01-01T00:00:00+00:00",
        "run_dir": "/repo/.harness/runs/TASK-001/run-x",
        "notes": "Falta cobertura.",
        "gaps": ["Sem teste de persistencia."],
    }
    out = harness.render_evaluation_markdown(evaluation)
    assert "Status: fail" in out
    assert "Sem teste de persistencia." in out
    assert "Falta cobertura." in out


def test_render_evaluation_markdown_without_gaps_uses_placeholder():
    evaluation = {
        "task_id": "TASK-001",
        "status": "pass",
        "created_at": "2026-01-01T00:00:00+00:00",
        "run_dir": "/x",
        "notes": "",
        "gaps": [],
    }
    out = harness.render_evaluation_markdown(evaluation)
    assert "Nenhuma lacuna registrada." in out
    assert "Sem notas." in out


def test_split_sensor_command_simple():
    assert harness.split_sensor_command("npm test") == ["npm", "test"]


def test_split_sensor_command_handles_flags():
    assert harness.split_sensor_command("npm run typecheck") == [
        "npm",
        "run",
        "typecheck",
    ]


def test_resolve_sensor_argv_passthrough_when_not_found():
    # An obviously-nonexistent command shouldn't blow up; it just returns argv as-is.
    out = harness.resolve_sensor_argv(["__definitely_not_a_real_binary__", "--flag"])
    assert out == ["__definitely_not_a_real_binary__", "--flag"]


def test_resolve_sensor_argv_empty():
    assert harness.resolve_sensor_argv([]) == []


def test_make_sensor_result_includes_extras():
    r = harness.make_sensor_result(
        command="npm test",
        argv=["npm", "test"],
        resolved_argv=["/usr/bin/npm", "test"],
        shell=False,
        exit_code=124,
        duration_ms=12,
        stdout="",
        stderr="boom",
        timeout=True,
    )
    assert r["timeout"] is True
    assert r["exit_code"] == 124
    assert r["stderr"] == "boom"


def test_is_inside_root_accepts_child(tmp_path):
    child = tmp_path / "sub" / "file.md"
    child.parent.mkdir()
    child.write_text("x", encoding="utf-8")
    assert harness.is_inside_root(tmp_path, child) is True


def test_is_inside_root_rejects_sibling(tmp_path):
    outside = tmp_path.parent / "elsewhere.md"
    assert harness.is_inside_root(tmp_path, outside) is False


def test_assert_inside_root_raises_for_outside(tmp_path):
    outside = tmp_path.parent / "etc-passwd.txt"
    with pytest.raises(SystemExit):
        harness.assert_inside_root(tmp_path, outside, label="test")


def test_to_posix_normalises_backslashes():
    assert harness.to_posix("a\\b\\c") == "a/b/c"
    assert harness.to_posix("") == ""

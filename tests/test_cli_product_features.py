"""Smoke tests for newer product-facing CLI workflows."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.conftest import harness
from tests.test_cli_smoke import init_repo


def run(argv):
    """Invoke harness.main(argv) and return its exit code."""
    return harness.main(argv)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_queue_add_list_next_and_done(tmp_path, capsys):
    repo = init_repo(tmp_path)

    assert run(["--repo", str(repo), "queue", "add", "Fix login", "--body", "Use email auth"]) == 0
    add_out = capsys.readouterr().out
    assert "QUEUE-001" in add_out

    assert run(["--repo", str(repo), "queue", "list"]) == 0
    list_out = capsys.readouterr().out
    assert "QUEUE-001" in list_out
    assert "Fix login" in list_out

    assert run(["--repo", str(repo), "queue", "next"]) == 0
    next_out = capsys.readouterr().out
    assert "QUEUE-001" in next_out
    assert "Use email auth" in next_out

    assert run(["--repo", str(repo), "queue", "done", "QUEUE-001"]) == 0
    queue = read_json(repo / ".harness" / "queue" / "index.json")
    assert queue[0]["id"] == "QUEUE-001"
    assert queue[0]["title"] == "Fix login"
    assert queue[0]["status"] == "done"


def test_checkpoint_create_and_resume_plan(tmp_path, capsys):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# Login\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])
    run(["--repo", str(repo), "start", "TASK-001"])

    assert run(
        [
            "--repo",
            str(repo),
            "checkpoint",
            "create",
            "TASK-001",
            "--summary",
            "Parser updated",
            "--next",
            "Wire CLI command",
        ]
    ) == 0
    create_out = capsys.readouterr().out
    assert "checkpoint" in create_out.lower()

    assert run(["--repo", str(repo), "checkpoint", "resume-plan", "TASK-001"]) == 0
    resume_out = capsys.readouterr().out
    assert "Parser updated" in resume_out
    assert "Wire CLI command" in resume_out

    run_dir = next((repo / ".harness" / "runs" / "TASK-001").iterdir())
    checkpoint = read_json(run_dir / "checkpoints" / "checkpoint-001.json")
    assert checkpoint["summary"] == "Parser updated"
    assert checkpoint["next_steps"] == ["Wire CLI command"]
    assert (run_dir / "resume-plan.md").is_file()


def test_profiles_and_budgets_config_round_trip(tmp_path, capsys):
    repo = init_repo(tmp_path)

    assert run(
        [
            "--repo",
            str(repo),
            "profile",
            "add",
            "builder-fast",
            "--model",
            "gpt-5-mini",
            "--sandbox",
            "workspace-write",
            "--approval",
            "never",
        ]
    ) == 0
    assert run(
        [
            "--repo",
            str(repo),
            "budget",
            "set",
            "builder-fast",
            "--max-tokens",
            "12000",
            "--timeout-minutes",
            "30",
        ]
    ) == 0

    config = read_json(repo / ".harness" / "config.json")
    assert config["profiles"]["builder-fast"]["model"] == "gpt-5-mini"
    assert config["profiles"]["builder-fast"]["sandbox"] == "workspace-write"
    assert config["profiles"]["builder-fast"]["approval"] == "never"
    assert config["budgets"]["builder-fast"]["max_tokens"] == 12000
    assert config["budgets"]["builder-fast"]["timeout_minutes"] == 30

    assert run(["--repo", str(repo), "profile", "list"]) == 0
    profile_out = capsys.readouterr().out
    assert "builder-fast" in profile_out
    assert "gpt-5-mini" in profile_out

    assert run(["--repo", str(repo), "budget", "list"]) == 0
    budget_out = capsys.readouterr().out
    assert "builder-fast" in budget_out
    assert "12000" in budget_out


def test_security_scan_detects_real_looking_secret_in_tracked_text_file(tmp_path):
    repo = init_repo(tmp_path)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    safe = repo / "safe.txt"
    safe.write_text("hello\n", encoding="utf-8")
    secret = repo / "settings.py"
    fake_tracked_token = "ghp_" + "0123456789abcdef0123456789abcdefabcd"
    secret.write_text(
        f"GITHUB_TOKEN = '{fake_tracked_token}'\n",
        encoding="utf-8",
    )
    untracked = repo / "scratch.txt"
    fake_untracked_token = "ghp_" + "abcdef0123456789abcdef0123456789abcd"
    untracked.write_text(
        f"GITHUB_TOKEN = '{fake_untracked_token}'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "safe.txt", "settings.py"], cwd=repo, check=True)

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "security", "scan"])

    assert exc.value.code == 1
    report = read_json(repo / ".harness" / "security" / "scan-latest.json")
    finding_paths = {finding["path"] for finding in report["findings"]}
    assert "settings.py" in finding_paths
    assert "scratch.txt" not in finding_paths
    finding = next(item for item in report["findings"] if item["path"] == "settings.py")
    assert finding["kind"] == "github_token"
    assert finding["line"] == 1


def test_security_scan_checks_telegram_inbox_json(tmp_path):
    repo = init_repo(tmp_path)
    token = "ghp_" + "fedcba9876543210fedcba9876543210abcd"
    inbox = repo / ".harness" / "inbox" / "telegram" / "tg-1-1.json"
    inbox.write_text(json.dumps({"text": f"GITHUB_TOKEN={token}"}), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "security", "scan"])

    assert exc.value.code == 1
    report = read_json(repo / ".harness" / "security" / "scan-latest.json")
    assert report["inbox_files_scanned"] == 1
    finding = next(item for item in report["findings"] if "tg-1-1.json" in item["path"])
    assert finding["kind"] == "github_token"


def test_plugin_registry_add_and_list(tmp_path, capsys):
    repo = init_repo(tmp_path)

    assert run(
        [
            "--repo",
            str(repo),
            "plugin",
            "add",
            "greptile-review",
            "--path",
            "skills/greptile-review",
            "--description",
            "Review agent",
        ]
    ) == 0
    assert run(["--repo", str(repo), "plugin", "list"]) == 0
    out = capsys.readouterr().out
    assert "greptile-review" in out
    assert "skills/greptile-review" in out

    registry = read_json(repo / ".harness" / "plugins" / "registry.json")
    assert registry["plugins"][0]["name"] == "greptile-review"
    assert registry["plugins"][0]["path"] == "skills/greptile-review"
    assert registry["plugins"][0]["description"] == "Review agent"


def test_plugin_run_requires_review_and_uses_safe_substitution(tmp_path, capsys):
    repo = init_repo(tmp_path)

    assert run(
        [
            "--repo",
            str(repo),
            "plugin",
            "add",
            "audit",
            "--command",
            "noop {repo} {task_id} {event} {literal}",
            "--event",
            "done",
        ]
    ) == 0

    with pytest.raises(SystemExit) as exc:
        run(["--repo", str(repo), "plugin", "run", "done", "--task-id", "TASK-123"])
    assert "bloqueada" in str(exc.value)

    assert run(
        [
            "--repo",
            str(repo),
            "plugin",
            "run",
            "done",
            "--task-id",
            "TASK-123",
            "--dry-run",
        ]
    ) == 0
    out = capsys.readouterr().out
    assert f"noop {repo} TASK-123 done {{literal}}" in out


def test_memory_remember_and_list(tmp_path, capsys):
    repo = init_repo(tmp_path)

    assert run(
        [
            "--repo",
            str(repo),
            "memory",
            "remember",
            "Prefer smoke sensors before full sensors",
            "--tag",
            "workflow",
        ]
    ) == 0
    assert run(["--repo", str(repo), "memory", "list"]) == 0
    out = capsys.readouterr().out
    assert "MEM-001" in out
    assert "Prefer smoke sensors before full sensors" in out
    assert "workflow" in out

    memory = read_json(repo / ".harness" / "memory" / "index.json")
    assert memory[0]["id"] == "MEM-001"
    assert memory[0]["text"] == "Prefer smoke sensors before full sensors"
    assert memory[0]["tags"] == ["workflow"]


def test_dashboard_html_generation(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# Dashboard source\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])

    assert run(["--repo", str(repo), "dashboard", "html"]) == 0
    dashboard = repo / ".harness" / "dashboard" / "index.html"
    assert dashboard.is_file()
    html = dashboard.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower()
    assert "Dashboard source" in html
    assert "TASK-001" in html


def test_dashboard_hub_generation_for_multiple_repos(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    repo_a = init_repo(tmp_path / "a")
    repo_b = init_repo(tmp_path / "b")
    issue_a = repo_a / "issue-a.md"
    issue_b = repo_b / "issue-b.md"
    issue_a.write_text("# Alpha task\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    issue_b.write_text("# Beta task\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo_a), "task", "import", str(issue_a)])
    run(["--repo", str(repo_b), "task", "import", str(issue_b)])
    run(["--repo", str(repo_a), "queue", "add", "TASK-001"])
    run(["--repo", str(repo_b), "queue", "add", "TASK-001"])

    assert run(
        [
            "--repo",
            str(repo_a),
            "dashboard",
            "hub",
            "--watch-repo",
            str(repo_a),
            "--watch-repo",
            str(repo_b),
        ]
    ) == 0

    hub = repo_a / ".harness" / "dashboard" / "hub" / "index.html"
    state_path = repo_a / ".harness" / "dashboard" / "hub" / "hub-state.json"
    css_path = repo_a / ".harness" / "dashboard" / "hub" / "hub.css"
    js_path = repo_a / ".harness" / "dashboard" / "hub" / "hub.js"
    assert hub.is_file()
    assert state_path.is_file()
    assert css_path.is_file()
    assert js_path.is_file()
    html = hub.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")
    state = read_json(state_path)
    assert "Harness Hub" in html
    assert 'href="hub.css"' in html
    assert 'src="hub.js"' in html
    assert 'id="hub-bootstrap"' in html
    assert "room" in js
    assert "agent-token" in js
    assert "speech-bubble" in css
    assert state["repo_count"] == 2
    assert {repo["project"] for repo in state["repos"]} == {"test"}
    assert state["total_tasks"] == 2
    assert state["repos"][0]["agents"][0]["state"] in {"idle", "working"}
    assert state["repos"][0]["agents"][0]["speech"]


def test_event_stream_and_agent_registry_follow_run(tmp_path):
    repo = init_repo(tmp_path)
    issue = repo / "issue.md"
    issue.write_text("# Agent task\n\n## Criterios\n\n- [ ] ok\n", encoding="utf-8")
    run(["--repo", str(repo), "task", "import", str(issue)])
    run(["--repo", str(repo), "contract", "TASK-001", "--criteria", "ok"])

    assert run(["--repo", str(repo), "start", "TASK-001"]) == 0

    events = (repo / ".harness" / "events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in events
    registry = read_json(repo / ".harness" / "agents" / "registry.json")
    assert registry["agents"][0]["task_id"] == "TASK-001"
    assert registry["agents"][0]["state"] == "working"

    assert run(["--repo", str(repo), "events", "list", "--json"]) == 0
    assert run(["--repo", str(repo), "agent", "list", "--json"]) == 0


def test_dashboard_hub_repo_registry_and_manual_agent(tmp_path):
    (tmp_path / "control").mkdir()
    (tmp_path / "watched").mkdir()
    control = init_repo(tmp_path / "control")
    watched = init_repo(tmp_path / "watched")

    assert run(["--repo", str(control), "dashboard", "hub-add-repo", str(watched)]) == 0
    assert run(
        [
            "--repo",
            str(watched),
            "agent",
            "register",
            "agent-a",
            "--role",
            "builder",
            "--state",
            "working",
            "--speech",
            "Montando teste local.",
        ]
    ) == 0
    assert run(["--repo", str(control), "dashboard", "hub"]) == 0

    state = read_json(control / ".harness" / "dashboard" / "hub" / "hub-state.json")
    assert state["repo_count"] == 2
    watched_state = next(repo for repo in state["repos"] if repo["root"] == str(watched))
    assert watched_state["agents"][0]["id"] == "agent-a"
    assert watched_state["agents"][0]["speech"] == "Montando teste local."


def test_wmux_state_handles_unavailable_pipe(monkeypatch):
    monkeypatch.setattr(harness, "wmux_pipe_path", lambda: r"\\.\pipe\missing-harness-test")
    state = harness.collect_wmux_state()
    assert state["available"] is False
    assert state["error"]

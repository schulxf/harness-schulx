"""Compatibility tests for the public Harness skill contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from harness_core.compat import SKILL_REQUIRED_COMMANDS

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "bin" / "harness.py"


def run_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HARNESS), *args],
        cwd=cwd or ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def test_skill_manifest_is_available_from_public_entrypoint():
    result = run_cli("compat", "manifest", "--json")

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["compat_version"] == "harness-runner-skill-v0.3"
    assert "bin/harness.py" in manifest["entrypoints"]
    assert "init" in manifest["required_commands"]
    assert "telegram bridge" in manifest["required_commands"]


def test_skill_required_commands_keep_help_surface():
    for command in SKILL_REQUIRED_COMMANDS:
        result = run_cli(*command, "--help")
        assert result.returncode == 0, f"{' '.join(command)}\n{result.stderr}"


def test_skill_smoke_runs_through_public_entrypoint_without_registering_fake_repo(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".harness").mkdir(parents=True)
    (control / ".harness" / "config.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HARNESS_HUB_CONTROL_REPO", str(control))

    result = run_cli("compat", "skill-smoke", "--workdir", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert (tmp_path / "skill-compat-repo" / ".harness" / "reports" / "TASK-001.md").is_file()
    assert [item["exit_code"] for item in payload["results"]] == [0] * len(payload["results"])
    assert not (control / ".harness" / "dashboard" / "hub" / "repos.json").exists()


def test_disabled_hub_control_survives_subprocess_boundary(tmp_path):
    local_app_data = tmp_path / "local-app-data"
    control = local_app_data / "HarnessAcompanhamento" / "control"
    (control / ".harness").mkdir(parents=True)
    (control / ".harness" / "config.json").write_text("{}\n", encoding="utf-8")
    repo = tmp_path / "implementation-repo"
    repo.mkdir()
    environment = dict(os.environ)
    environment["LOCALAPPDATA"] = str(local_app_data)
    environment["HARNESS_HUB_CONTROL_REPO"] = "disabled"

    initialized = run_cli(
        "--repo",
        str(repo),
        "--allow-main",
        "init",
        env=environment,
    )
    assert initialized.returncode == 0, initialized.stderr or initialized.stdout

    registered = run_cli(
        "--repo",
        str(repo),
        "agent",
        "register",
        "implementador-isolado",
        "--role",
        "builder",
        env=environment,
    )
    assert registered.returncode == 0, registered.stderr or registered.stdout
    assert not (control / ".harness" / "dashboard" / "hub" / "repos.json").exists()

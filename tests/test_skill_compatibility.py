"""Compatibility tests for the public Harness skill contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harness_core.compat import SKILL_REQUIRED_COMMANDS

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "bin" / "harness.py"


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HARNESS), *args],
        cwd=cwd or ROOT,
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


def test_skill_smoke_runs_through_public_entrypoint(tmp_path):
    result = run_cli("compat", "skill-smoke", "--workdir", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert (tmp_path / "skill-compat-repo" / ".harness" / "reports" / "TASK-001.md").is_file()
    assert [item["exit_code"] for item in payload["results"]] == [0] * len(payload["results"])


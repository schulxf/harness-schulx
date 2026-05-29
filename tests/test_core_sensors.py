from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_core import sensors


def test_detect_default_sensors_from_package_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest",
                    "build": "vite build",
                }
            }
        ),
        encoding="utf-8",
    )

    assert sensors.detect_default_sensors(tmp_path) == [
        "npm run lint",
        "npm run typecheck",
        "npm test",
        "npm run build",
    ]


def test_detect_default_sensors_from_python_markers(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    assert sensors.detect_default_sensors(tmp_path) == ["python -m pytest"]


def test_split_sensor_command_handles_flags() -> None:
    assert sensors.split_sensor_command("npm run typecheck") == ["npm", "run", "typecheck"]


def test_resolve_sensor_argv_passthrough_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensors.shutil, "which", lambda _name: None)

    assert sensors.resolve_sensor_argv(["missing-tool", "--flag"]) == ["missing-tool", "--flag"]


def test_resolve_sensor_argv_replaces_found_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensors.shutil, "which", lambda _name: "C:/Tools/tool.exe")

    assert sensors.resolve_sensor_argv(["tool", "--flag"]) == ["C:/Tools/tool.exe", "--flag"]


def test_make_sensor_result_includes_extras() -> None:
    result = sensors.make_sensor_result(
        command="npm test",
        argv=["npm", "test"],
        resolved_argv=["/usr/bin/npm", "test"],
        shell=False,
        exit_code=124,
        duration_ms=12,
        stderr="boom",
        timeout=True,
    )

    assert result["timeout"] is True
    assert result["exit_code"] == 124
    assert result["stderr"] == "boom"


def test_sensor_tiers_include_legacy_full() -> None:
    contract = {"required_sensors": ["npm test"]}

    tiers = sensors.normalize_sensor_tiers(contract)

    assert tiers["smoke"] == []
    assert tiers["affected"] == []
    assert tiers["full"] == ["npm test"]
    assert sensors.sensors_for_tier(contract, "all") == ["npm test"]


def test_sensors_for_tier_all_preserves_order_and_deduplicates() -> None:
    contract = {
        "sensor_tiers": {
            "smoke": ["npm run lint", "npm test"],
            "affected": ["npm test", "npm run typecheck"],
            "full": ["npm run build"],
        }
    }

    assert sensors.sensors_for_tier(contract, "all") == [
        "npm run lint",
        "npm test",
        "npm run typecheck",
        "npm run build",
    ]


def test_sensors_for_tier_invalid_tier_raises() -> None:
    with pytest.raises(SystemExit, match="Tier de sensor invalido"):
        sensors.sensors_for_tier({}, "unknown")


def test_fastest_available_sensor_tier_returns_first_configured_tier() -> None:
    assert sensors.fastest_available_sensor_tier({"sensor_tiers": {"affected": ["npm test"]}}) == "affected"
    assert sensors.fastest_available_sensor_tier({}) == "full"


def test_final_sensor_payload_prefers_full_then_all_then_legacy(tmp_path: Path) -> None:
    contract = {"required_sensors": ["npm test"]}
    (tmp_path / "sensors.json").write_text(json.dumps({"tier": "full", "source": "legacy"}), encoding="utf-8")
    (tmp_path / "sensors-all.json").write_text(json.dumps({"tier": "all", "source": "all"}), encoding="utf-8")
    (tmp_path / "sensors-full.json").write_text(json.dumps({"tier": "full", "source": "full"}), encoding="utf-8")

    assert sensors.final_sensor_payload(tmp_path, contract)["source"] == "full"

    (tmp_path / "sensors-full.json").unlink()
    assert sensors.final_sensor_payload(tmp_path, contract)["source"] == "all"

    (tmp_path / "sensors-all.json").unlink()
    assert sensors.final_sensor_payload(tmp_path, contract)["source"] == "legacy"


def test_final_sensor_payload_requires_full_or_all_for_full_contract(tmp_path: Path) -> None:
    (tmp_path / "sensors.json").write_text(json.dumps({"tier": "smoke"}), encoding="utf-8")

    assert sensors.final_sensor_payload(tmp_path, {"required_sensors": ["npm test"]}) == {}


def test_final_sensor_payload_uses_legacy_when_no_full_sensor_configured(tmp_path: Path) -> None:
    (tmp_path / "sensors.json").write_text(json.dumps({"tier": "smoke", "passed": True}), encoding="utf-8")

    assert sensors.final_sensor_payload(tmp_path, {}) == {"tier": "smoke", "passed": True}

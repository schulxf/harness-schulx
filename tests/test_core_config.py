"""Focused tests for extracted config/default/compat helpers."""

from __future__ import annotations

import json

import pytest

from harness_core import config
from harness_core.compat import (
    SKILL_COMPAT_VERSION,
    SKILL_REQUIRED_COMMANDS,
    compatibility_manifest,
)
from harness_core.defaults import (
    DEFAULT_GITHUB_CONFIG,
    DEFAULT_OPERATION_PROFILES,
    DEFAULT_PROTECTED_BRANCHES,
    DEFAULT_REVIEW_POLICY,
    DEFAULT_TELEGRAM_CONFIG,
)


def test_config_bool_handles_common_cli_and_json_values() -> None:
    for value in [True, "true", "TRUE", "1", "yes", "on"]:
        assert config.config_bool(value) is True

    for value in [False, "false", "FALSE", "0", "no", "off"]:
        assert config.config_bool(value, default=True) is False

    assert config.config_bool(None, default=True) is True
    assert config.config_bool(None, default=False) is False
    assert config.config_bool("anything else") is True


def test_deep_merge_preserves_defaults_and_copies_mutable_values() -> None:
    defaults = {
        "nested": {"enabled": False, "mode": "safe"},
        "items": ["default"],
        "scalar": "fallback",
    }

    merged = config.deep_merge(
        defaults,
        {
            "nested": {"enabled": True},
            "items": ["override"],
            "extra": "kept",
        },
    )

    assert merged == {
        "nested": {"enabled": True, "mode": "safe"},
        "items": ["override"],
        "scalar": "fallback",
        "extra": "kept",
    }

    merged["items"].append("mutated")
    assert defaults["items"] == ["default"]


def test_default_profiles_keep_skill_compatible_aliases() -> None:
    assert DEFAULT_PROTECTED_BRANCHES == ["main", "master", "production"]
    assert set(DEFAULT_OPERATION_PROFILES) == {
        "fast",
        "balanced",
        "standard",
        "strict",
        "deep",
        "release",
    }
    assert DEFAULT_OPERATION_PROFILES["standard"]["sensor_tier"] == "full"
    assert DEFAULT_OPERATION_PROFILES["deep"]["max_fix_attempts"] == 3


def test_review_policy_merges_nested_blocking_findings_without_losing_defaults() -> None:
    policy = config.review_policy(
        {
            "review_policy": {
                "enabled": False,
                "blocking_findings": {"p2": True},
            }
        }
    )

    assert policy["enabled"] is False
    assert policy["skill"] == DEFAULT_REVIEW_POLICY["skill"]
    assert policy["blocking_findings"] == {
        "p0": True,
        "p1_in_changed_surface": True,
        "p2": True,
    }


def test_github_and_telegram_config_merge_nested_defaults() -> None:
    github = config.github_config({"github": {"repo": "owner/repo"}})
    telegram = config.telegram_config(
        {"telegram": {"enabled": True, "openai_media": {"enabled": True}}}
    )

    assert github == {
        **DEFAULT_GITHUB_CONFIG,
        "repo": "owner/repo",
    }
    assert telegram["enabled"] is True
    assert telegram["token_env"] == DEFAULT_TELEGRAM_CONFIG["token_env"]
    assert telegram["chat_ids"] == []
    assert telegram["openai_media"]["enabled"] is True
    assert (
        telegram["openai_media"]["audio_model"]
        == DEFAULT_TELEGRAM_CONFIG["openai_media"]["audio_model"]
    )

    telegram["chat_ids"].append("123")
    assert DEFAULT_TELEGRAM_CONFIG["chat_ids"] == []


def test_operation_profiles_merge_overrides_and_custom_profiles() -> None:
    profiles = config.operation_profiles(
        {
            "operation_profiles": {
                "fast": {"max_fix_attempts": 9},
                "audit": {"sensor_tier": "all", "review": "parallel"},
            }
        }
    )

    assert profiles["fast"]["description"] == DEFAULT_OPERATION_PROFILES["fast"]["description"]
    assert profiles["fast"]["max_fix_attempts"] == 9
    assert profiles["audit"] == {"sensor_tier": "all", "review": "parallel"}
    assert DEFAULT_OPERATION_PROFILES["fast"]["max_fix_attempts"] == 1


def test_active_profile_resolves_requested_or_configured_profile() -> None:
    cfg = {"active_profile": "strict"}

    assert config.active_profile_name(cfg) == "strict"
    assert config.active_profile_name(cfg, requested="fast") == "fast"
    assert config.active_profile(cfg)["name"] == "strict"
    assert config.active_profile(cfg)["sensor_tier"] == "full"


def test_active_profile_rejects_unknown_profile() -> None:
    with pytest.raises(SystemExit, match="Profile desconhecido: missing"):
        config.active_profile_name({}, requested="missing")


def test_compatibility_manifest_is_json_safe_and_matches_command_contract() -> None:
    manifest = compatibility_manifest()

    assert manifest["compat_version"] == SKILL_COMPAT_VERSION
    assert manifest["entrypoints"] == ["bin/harness.py", "bin/harness.ps1"]
    assert manifest["required_commands"] == [" ".join(command) for command in SKILL_REQUIRED_COMMANDS]
    assert "telegram bridge" in manifest["required_commands"]
    assert "status" in manifest["required_commands"]
    assert len(manifest["required_commands"]) == len(set(manifest["required_commands"]))
    json.dumps(manifest)

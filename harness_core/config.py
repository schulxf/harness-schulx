"""Configuration merge and policy helpers."""

from __future__ import annotations

from typing import Any

from harness_core.defaults import (
    DEFAULT_EVALUATION_POLICY,
    DEFAULT_FAILURE_POLICY,
    DEFAULT_GITHUB_CONFIG,
    DEFAULT_HUB_CONFIG,
    DEFAULT_OPERATION_PROFILES,
    DEFAULT_REVIEW_POLICY,
    DEFAULT_TELEGRAM_CONFIG,
)


def config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def deep_merge(defaults: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    overrides = overrides or {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            configured = overrides.get(key, {})
            result[key] = deep_merge(value, configured if isinstance(configured, dict) else {})
        elif isinstance(value, list):
            configured = overrides.get(key, value)
            result[key] = list(configured) if isinstance(configured, list) else list(value)
        else:
            result[key] = overrides.get(key, value)
    for key, value in overrides.items():
        if key not in result:
            result[key] = value
    return result


def evaluation_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_EVALUATION_POLICY)
    policy.update(config.get("evaluation_policy", {}))
    return policy


def review_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_REVIEW_POLICY)
    configured = config.get("review_policy", {})
    if isinstance(configured, dict):
        blocking = dict(DEFAULT_REVIEW_POLICY["blocking_findings"])
        blocking.update(configured.get("blocking_findings", {}))
        policy.update(configured)
        policy["blocking_findings"] = blocking
    return policy


def failure_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_FAILURE_POLICY)
    configured = config.get("failure_policy", {})
    if isinstance(configured, dict):
        policy.update(configured)
    return policy


def github_config(config: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("github", {})
    return deep_merge(DEFAULT_GITHUB_CONFIG, configured if isinstance(configured, dict) else {})


def operation_profiles(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = {name: dict(value) for name, value in DEFAULT_OPERATION_PROFILES.items()}
    configured = config.get("operation_profiles", {})
    if isinstance(configured, dict):
        for name, value in configured.items():
            if isinstance(value, dict):
                base = dict(profiles.get(str(name), {}))
                base.update(value)
                profiles[str(name)] = base
    return profiles


def active_profile_name(config: dict[str, Any], requested: str | None = None) -> str:
    profiles = operation_profiles(config)
    name = requested or str(config.get("active_profile") or "balanced")
    if name not in profiles:
        raise SystemExit(f"Profile desconhecido: {name}. Use `profile list`.")
    return name


def active_profile(config: dict[str, Any], requested: str | None = None) -> dict[str, Any]:
    name = active_profile_name(config, requested)
    profile = dict(operation_profiles(config)[name])
    profile["name"] = name
    return profile


def telegram_config(config: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("telegram", {})
    return deep_merge(DEFAULT_TELEGRAM_CONFIG, configured if isinstance(configured, dict) else {})


def hub_config(config: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("hub", {})
    return deep_merge(DEFAULT_HUB_CONFIG, configured if isinstance(configured, dict) else {})

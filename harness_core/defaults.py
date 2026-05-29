"""Default policies, profiles and scanner rules for Harness."""

from __future__ import annotations

import re

DEFAULT_PROTECTED_BRANCHES = ["main", "master", "production"]

DEFAULT_OPERATION_PROFILES = {
    "fast": {
        "description": "Loop curto para feedback rapido.",
        "sensor_tier": "quick",
        "review": "parallel",
        "max_fix_attempts": 1,
        "time_budget_minutes": 30,
    },
    "balanced": {
        "description": "Padrao para trabalho diario.",
        "sensor_tier": "affected",
        "review": "parallel",
        "max_fix_attempts": 2,
        "time_budget_minutes": 90,
    },
    "standard": {
        "description": "Alias documentado para trabalho diario equilibrado.",
        "sensor_tier": "full",
        "review": "parallel",
        "max_fix_attempts": 2,
        "time_budget_minutes": 90,
    },
    "strict": {
        "description": "Mais rigor para areas sensiveis.",
        "sensor_tier": "full",
        "review": "parallel",
        "max_fix_attempts": 3,
        "time_budget_minutes": 180,
    },
    "deep": {
        "description": "Alias documentado para revisao profunda.",
        "sensor_tier": "full",
        "review": "parallel",
        "max_fix_attempts": 3,
        "time_budget_minutes": 180,
    },
    "release": {
        "description": "Fechamento antes de publicar.",
        "sensor_tier": "all",
        "review": "parallel",
        "max_fix_attempts": 3,
        "time_budget_minutes": 240,
    },
}

DEFAULT_FAILURE_POLICY = {
    "max_fix_attempts": 3,
    "auto_fix_brief": True,
    "p0_blocks": True,
    "p1_blocks": True,
    "p2_blocks": False,
}

DEFAULT_GITHUB_CONFIG = {
    "repo": "",
    "remote": "origin",
    "default_base": "main",
}

SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE" r" KEY-----")),
    ("telegram_bot_token", re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "secret_assignment",
        re.compile(
            r"\b(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)\b\s*[:=]\s*['\"]?"
            r"(?!<|example|changeme|your-|novo-token|telegram-bot-token|openai-api-key)"
            r"[A-Za-z0-9_./:+-]{16,}",
            re.IGNORECASE,
        ),
    ),
]

SECURITY_EXCLUDED_DIRS = {
    ".git",
    ".harness",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
}

CONTEXT_KINDS = [
    "context",
    "domain-context",
    "prd",
    "issue",
    "architecture",
    "infrastructure",
    "security",
    "testing",
    "refactor-plan",
    "decision",
    "adr",
    "guardrail",
    "other",
]

DEFAULT_EVALUATION_POLICY = {
    "mode": "spawned_agent",
    "fork_context": False,
    "input_scope": "evaluator_agent_handoff",
}

DEFAULT_REVIEW_POLICY = {
    "enabled": True,
    "mode": "spawned_agent",
    "fork_context": False,
    "skill": "greptile-review",
    "input_scope": "greptile_reviewer_handoff",
    "blocking_findings": {
        "p0": True,
        "p1_in_changed_surface": True,
        "p2": False,
    },
}

DEFAULT_TELEGRAM_CONFIG = {
    "enabled": False,
    "token_env": "HARNESS_TELEGRAM_BOT_TOKEN",
    "chat_ids": [],
    "allowed_chat_ids": [],
    "notify_events": [
        "run_started",
        "sensors_completed",
        "evaluation_brief_created",
        "evaluation_recorded",
        "fix_brief_created",
        "report_created",
    ],
    "allow_task_creation": True,
    "allow_remote_execution": False,
    "download_media": True,
    "max_download_bytes": 20 * 1024 * 1024,
    "openai_media": {
        "enabled": False,
        "api_key_env": "OPENAI_API_KEY",
        "audio_model": "gpt-4o-mini-transcribe",
        "vision_model": "gpt-4.1-mini",
        "transcribe_audio": True,
        "describe_images": True,
    },
}

DEFAULT_HUB_CONFIG = {
    "allow_remote_execution": False,
    "max_agents": 8,
    "default_cli": "codex",
    "clis": {
        "codex": {"cmd": ["codex"], "args": []},
        "claude": {"cmd": ["claude"], "args": []},
    },
    "pty": {
        "idle_timeout_s": 1800,
        "scrollback_bytes": 262144,
    },
}

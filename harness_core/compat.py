"""Compatibility contract for the public skill-facing CLI."""

from __future__ import annotations

SKILL_COMPAT_VERSION = "harness-runner-skill-v0.3"

PUBLIC_ENTRYPOINTS = [
    "bin/harness.py",
    "bin/harness.ps1",
]

SKILL_REQUIRED_COMMANDS = [
    ("init",),
    ("ingest",),
    ("preflight",),
    ("task", "create"),
    ("task", "import"),
    ("task", "list"),
    ("pick",),
    ("queue", "add"),
    ("queue", "list"),
    ("queue", "next"),
    ("queue", "done"),
    ("contract",),
    ("start",),
    ("sensors",),
    ("quick-pass",),
    ("full-pass",),
    ("evaluate",),
    ("fix-brief",),
    ("report",),
    ("checkpoint", "create"),
    ("checkpoint", "resume-plan"),
    ("resume",),
    ("security", "scan"),
    ("security", "status"),
    ("dashboard", "hub"),
    ("dashboard", "hub-serve"),
    ("dashboard", "hub-add-repo"),
    ("dashboard", "hub-list-repos"),
    ("agent", "register"),
    ("agent", "heartbeat"),
    ("agent", "list"),
    ("events", "list"),
    ("telegram", "configure"),
    ("telegram", "status"),
    ("telegram", "send"),
    ("telegram", "listen"),
    ("telegram", "codex"),
    ("telegram", "mirror"),
    ("telegram", "bridge"),
    ("status",),
]


def compatibility_manifest() -> dict[str, object]:
    return {
        "compat_version": SKILL_COMPAT_VERSION,
        "entrypoints": PUBLIC_ENTRYPOINTS,
        "required_commands": [" ".join(command) for command in SKILL_REQUIRED_COMMANDS],
    }


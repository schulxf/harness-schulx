"""Pure helpers for local secret scanning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.defaults import SECRET_PATTERNS, SECURITY_EXCLUDED_DIRS
from harness_core.git_helpers import git_output, is_git_repo
from harness_core.paths import relative_to_root, telegram_inbox_root
from harness_core.storage import read_text


def is_probably_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\0" not in sample


def scan_file_for_secrets(root: Path, path: Path, *, allow_harness: bool = False) -> list[dict[str, Any]]:
    if not allow_harness and any(part in SECURITY_EXCLUDED_DIRS for part in path.relative_to(root).parts):
        return []
    if not is_probably_text(path):
        return []
    findings = []
    try:
        lines = read_text(path).splitlines()
    except UnicodeDecodeError:
        return []
    for line_number, line in enumerate(lines, start=1):
        for kind, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(0)
            redacted = value[:8] + "..." + value[-4:] if len(value) > 16 else "[redacted]"
            findings.append(
                {
                    "kind": kind,
                    "path": relative_to_root(root, path),
                    "line": line_number,
                    "match": redacted,
                }
            )
    return findings


def iter_security_scan_files(root: Path, tracked_only: bool = True) -> list[Path]:
    if tracked_only and is_git_repo(root):
        output = git_output(root, ["ls-files"])
        return [root / line.strip() for line in output.splitlines() if line.strip()]
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SECURITY_EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def iter_security_inbox_files(root: Path) -> list[Path]:
    inbox = telegram_inbox_root(root)
    if not inbox.exists():
        return []
    return sorted(path for path in inbox.glob("*.json") if path.is_file())

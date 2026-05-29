"""Pure helpers for local secret scanning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.defaults import SECRET_PATTERNS, SECURITY_EXCLUDED_DIRS
from harness_core.paths import relative_to_root
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

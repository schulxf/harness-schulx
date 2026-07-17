"""Pure helpers for local secret scanning."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from harness_core.defaults import SECRET_PATTERNS, SECURITY_EXCLUDED_DIRS
from harness_core.file_hash import file_sha256
from harness_core.git_helpers import git_output, is_git_repo
from harness_core.paths import HARNESS_DIR, relative_to_root, telegram_inbox_root
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


def source_surface_digest(root: Path) -> str:
    """Hash source state while excluding Harness' own mutable evidence files."""
    digest = hashlib.sha256(b"harness-source-surface-v1\n")
    if is_git_repo(root):
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
        )
        untracked = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
        )
        if tracked.returncode == 0 and untracked.returncode == 0:
            raw_paths = set(filter(None, tracked.stdout.split(b"\0")))
            raw_paths.update(filter(None, untracked.stdout.split(b"\0")))
            for raw_path in sorted(raw_paths):
                relative = Path(raw_path.decode("utf-8", errors="surrogateescape"))
                if HARNESS_DIR in relative.parts:
                    continue
                path = root / relative
                digest.update(b"FILE\0" + raw_path + b"\0")
                if path.is_file():
                    digest.update(file_sha256(path).encode())
                else:
                    digest.update(b"MISSING")
            return digest.hexdigest()

    for path in sorted(iter_security_scan_files(root, tracked_only=False)):
        relative = relative_to_root(root, path)
        digest.update(f"FILE\0{relative}\0".encode())
        digest.update(file_sha256(path).encode())
    return digest.hexdigest()


def iter_security_inbox_files(root: Path) -> list[Path]:
    inbox = telegram_inbox_root(root)
    if not inbox.exists():
        return []
    return sorted(path for path in inbox.glob("*.json") if path.is_file())

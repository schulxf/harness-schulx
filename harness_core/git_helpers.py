"""Git repository inspection helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness_core.defaults import DEFAULT_PROTECTED_BRANCHES
from harness_core.paths import config_path
from harness_core.storage import read_json, read_text


def discover_git_dir(root: Path) -> Path | None:
    resolved = root.resolve(strict=False)
    for path in [resolved, *resolved.parents]:
        dot_git = path / ".git"
        if dot_git.is_dir():
            return dot_git
        if dot_git.is_file():
            try:
                content = read_text(dot_git).strip()
            except OSError:
                continue
            prefix = "gitdir:"
            if content.lower().startswith(prefix):
                git_dir = content[len(prefix) :].strip()
                candidate = Path(git_dir)
                if not candidate.is_absolute():
                    candidate = path / candidate
                return candidate.resolve(strict=False)
    return None


def is_git_repo(root: Path) -> bool:
    if not discover_git_dir(root):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def current_git_branch(root: Path) -> str | None:
    git_dir = discover_git_dir(root)
    if git_dir:
        head_path = git_dir / "HEAD"
        try:
            head = read_text(head_path).strip()
        except OSError:
            head = ""
        if head.startswith("ref:"):
            ref = head.removeprefix("ref:").strip()
            heads_prefix = "refs/heads/"
            return ref.removeprefix(heads_prefix) or None
        if head:
            return head[:12]
    if not is_git_repo(root):
        return None
    branch = git_output(root, ["branch", "--show-current"]).strip()
    return branch or None


def git_output(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "git nao esta instalado ou nao esta no PATH."
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip()


def protected_branches(root: Path) -> list[str]:
    config = read_json(config_path(root), {}) if config_path(root).exists() else {}
    return config.get("protected_branches", DEFAULT_PROTECTED_BRANCHES)

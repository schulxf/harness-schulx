"""Repository and branch guard helpers for CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from harness_core.context_preflight import require_init
from harness_core.git_helpers import current_git_branch, protected_branches


def root_from_args(args: argparse.Namespace) -> Path:
    return Path(args.repo).expanduser().resolve()


def require_existing_root(root: Path) -> None:
    if not root.exists():
        raise SystemExit(
            f"Diretorio do repo nao existe: {root}\n"
            "Use um caminho real ja existente ou rode `init --create` de forma explicita."
        )
    if not root.is_dir():
        raise SystemExit(f"O caminho do repo nao e um diretorio: {root}")


def require_safe_branch(root: Path, args: argparse.Namespace, operation: str) -> None:
    branch = current_git_branch(root)
    if not branch:
        return
    protected = protected_branches(root)
    if branch in protected and not getattr(args, "allow_main", False):
        raise SystemExit(
            f"Operacao bloqueada: `{operation}` esta na branch protegida `{branch}`.\n"
            "Crie uma branch de trabalho, por exemplo: "
            "`git switch -c harness/TASK-001`, ou rode com `--allow-main` antes do comando "
            "se voce realmente quiser operar nessa branch."
        )


def prepared_repo(args: argparse.Namespace, *, safe_operation: str | None = None) -> Path:
    root = root_from_args(args)
    require_existing_root(root)
    require_init(root)
    if safe_operation:
        require_safe_branch(root, args, safe_operation)
    return root

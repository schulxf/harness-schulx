"""Required context preflight checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_core.clock import utc_now
from harness_core.config import config_bool
from harness_core.file_hash import file_sha256
from harness_core.paths import (
    assert_inside_root,
    config_path,
    context_manifest_path,
    contract_file_path,
    harness_root,
    normalize_path_key,
    preflight_cache_path,
    relative_to_root,
    resolve_repo_path,
)
from harness_core.storage import read_json, write_json


def require_init(root: Path) -> None:
    if not (harness_root(root) / "config.json").exists():
        raise SystemExit(
            f"Harness nao inicializado em {root}. Rode: harness --repo {root} init"
        )


def load_config(root: Path) -> dict[str, Any]:
    require_init(root)
    return read_json(config_path(root), {})


def normalize_context_requirement(root: Path, item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"path": item}
    if isinstance(item, dict):
        path = item.get("path") or item.get("source")
        if not path:
            raise SystemExit(f"Entrada de contexto obrigatorio sem `path`: {item}")
        normalized = dict(item)
        normalized["path"] = path
        return normalized
    raise SystemExit(f"Entrada de contexto obrigatorio invalida: {item}")


def context_requirements_for_task(
    root: Path,
    config: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = config if config is not None else load_config(root)
    raw_items: list[Any] = []
    raw_items.extend(config.get("required_context", []))
    if contract:
        raw_items.extend(contract.get("required_docs", []))

    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = normalize_context_requirement(root, raw_item)
        path = resolve_repo_path(root, item["path"])
        assert_inside_root(root, path, label=f"required_context `{item['path']}`")
        key = normalize_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["absolute_path"] = str(path)
        normalized["display_path"] = relative_to_root(root, path)
        requirements.append(normalized)
    return requirements


def latest_manifest_items_by_source(root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(context_manifest_path(root), [])
    latest: dict[str, dict[str, Any]] = {}
    for item in manifest:
        source = item.get("source")
        if not source:
            continue
        source_path = resolve_repo_path(root, source)
        latest[normalize_path_key(source_path)] = item
    return latest


def context_preflight_fingerprint(
    root: Path,
    task_id: str | None,
    config: dict[str, Any],
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    latest = latest_manifest_items_by_source(root)
    items: list[dict[str, Any]] = []
    for requirement in context_requirements_for_task(root, config, contract):
        path = Path(requirement["absolute_path"])
        manifest_item = latest.get(normalize_path_key(path), {})
        stat_payload: dict[str, Any] = {"exists": path.exists()}
        if path.exists():
            stat = path.stat()
            stat_payload.update(
                {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        items.append(
            {
                "path": requirement["display_path"],
                "kind": requirement.get("kind"),
                "required_by": requirement.get("required_by"),
                "source": manifest_item.get("source"),
                "stored_path": manifest_item.get("stored_path"),
                "source_sha256": manifest_item.get("source_sha256"),
                "stored_sha256": manifest_item.get("stored_sha256"),
                "source_size": manifest_item.get("source_size"),
                "source_mtime": manifest_item.get("source_mtime"),
                "stat": stat_payload,
            }
        )
    return {"task_id": task_id, "items": items}


def context_preflight_cache_enabled(config: dict[str, Any]) -> bool:
    policy = config.get("policy", {})
    return config_bool(policy.get("cache_context_preflight"), True)


def check_context_preflight(root: Path, task_id: str | None = None) -> dict[str, Any]:
    config = load_config(root)
    contract = None
    if task_id and contract_file_path(root, task_id).exists():
        contract = read_json(contract_file_path(root, task_id), {})
    fingerprint = context_preflight_fingerprint(root, task_id, config, contract)
    cache_path = preflight_cache_path(root, task_id)
    if context_preflight_cache_enabled(config):
        cached = read_json(cache_path, {})
        if cached.get("fingerprint") == fingerprint and cached.get("result"):
            result = dict(cached["result"])
            result["cache"] = "hit"
            return result
    requirements = context_requirements_for_task(root, config, contract)
    latest = latest_manifest_items_by_source(root)
    checked: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for requirement in requirements:
        path = Path(requirement["absolute_path"])
        key = normalize_path_key(path)
        entry = {
            "path": requirement["display_path"],
            "kind": requirement.get("kind"),
            "required_by": requirement.get("required_by"),
        }
        if not path.exists():
            issue = {**entry, "reason": "source_missing"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        manifest_item = latest.get(key)
        if not manifest_item:
            issue = {**entry, "reason": "not_ingested"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        stored_path = root / manifest_item["stored_path"]
        if not stored_path.exists():
            issue = {**entry, "reason": "stored_copy_missing"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        expected_kind = requirement.get("kind")
        if expected_kind and manifest_item.get("kind") != expected_kind:
            issue = {
                **entry,
                "reason": "kind_mismatch",
                "actual_kind": manifest_item.get("kind"),
            }
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        current_hash = file_sha256(path)
        stored_hash = manifest_item.get("source_sha256")
        if not stored_hash:
            issue = {**entry, "reason": "missing_hash_metadata"}
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue
        if stored_hash != current_hash:
            issue = {
                **entry,
                "reason": "source_changed_since_ingest",
                "ingested_sha256": stored_hash,
                "current_sha256": current_hash,
            }
            checked.append({**entry, "status": "fail", "reason": issue["reason"]})
            issues.append(issue)
            continue

        checked.append(
            {
                **entry,
                "status": "pass",
                "stored_path": manifest_item["stored_path"],
                "ingested_at": manifest_item.get("ingested_at"),
                "source_sha256": stored_hash,
            }
        )

    result = {
        "task_id": task_id,
        "created_at": utc_now(),
        "passed": not issues,
        "requirements": checked,
        "issues": issues,
        "cache": "miss",
    }
    if context_preflight_cache_enabled(config):
        write_json(
            cache_path,
            {
                "created_at": utc_now(),
                "fingerprint": fingerprint,
                "result": result,
            },
        )
    return result


def render_preflight_text(result: dict[str, Any]) -> str:
    lines = []
    task_id = result.get("task_id") or "global"
    lines.append(f"Preflight de contexto: {task_id}")
    if not result.get("requirements"):
        lines.append("- Nenhum contexto obrigatorio configurado.")
        return "\n".join(lines)
    for item in result.get("requirements", []):
        marker = "PASS" if item.get("status") == "pass" else "FAIL"
        suffix = f" ({item.get('kind')})" if item.get("kind") else ""
        reason = f" - {item.get('reason')}" if item.get("reason") else ""
        lines.append(f"- {marker} {item.get('path')}{suffix}{reason}")
    return "\n".join(lines)


def require_context_preflight(root: Path, task_id: str, *, skip_preflight: bool = False) -> None:
    if skip_preflight:
        return
    config = load_config(root)
    policy = config.get("policy", {})
    if policy.get("context_preflight_required_before_start", True) is False:
        return
    result = check_context_preflight(root, task_id)
    if result["passed"]:
        return
    text = render_preflight_text(result)
    raise SystemExit(
        f"{text}\n\n"
        "Start bloqueado: reingira os documentos obrigatorios com `harness ingest` "
        "ou ajuste `required_context`/`required_docs` se a exigencia estiver incorreta."
    )

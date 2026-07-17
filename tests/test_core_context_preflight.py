from __future__ import annotations

from pathlib import Path

import pytest

from harness_core.context_preflight import (
    check_context_preflight,
    context_requirements_for_task,
    load_config,
    normalize_context_requirement,
    render_preflight_text,
    require_context_preflight,
)
from harness_core.file_hash import file_sha256
from harness_core.paths import config_path, context_manifest_path, preflight_cache_path
from harness_core.storage import write_json


def write_config(root: Path, payload: dict | None = None) -> dict:
    config = {
        "project_name": "test",
        "policy": {
            "cache_context_preflight": True,
            "context_preflight_required_before_start": True,
        },
    }
    if payload:
        config.update(payload)
    write_json(config_path(root), config)
    return config


def write_manifest_for_doc(root: Path, source: Path, stored: Path, *, kind: str = "context") -> None:
    write_json(
        context_manifest_path(root),
        [
            {
                "source": source.relative_to(root).as_posix(),
                "stored_path": stored.relative_to(root).as_posix(),
                "kind": kind,
                "source_sha256": file_sha256(source),
                "stored_sha256": file_sha256(stored),
                "source_size": source.stat().st_size,
                "source_mtime": source.stat().st_mtime,
            }
        ],
    )


def test_load_config_requires_init(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Harness nao inicializado"):
        load_config(tmp_path)


def test_context_requirements_deduplicates_and_resolves_paths(tmp_path: Path) -> None:
    doc = tmp_path / "AGENTS.md"
    doc.write_text("context", encoding="utf-8")
    config = {"required_context": ["AGENTS.md", {"source": "AGENTS.md", "kind": "context"}]}

    requirements = context_requirements_for_task(tmp_path, config)

    assert len(requirements) == 1
    assert requirements[0]["path"] == "AGENTS.md"
    assert requirements[0]["display_path"] == "AGENTS.md"
    assert Path(requirements[0]["absolute_path"]) == doc.resolve()


def test_normalize_context_requirement_rejects_bad_items(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="sem `path`"):
        normalize_context_requirement(tmp_path, {"kind": "context"})
    with pytest.raises(SystemExit, match="invalida"):
        normalize_context_requirement(tmp_path, 123)


def test_check_context_preflight_missing_source_fails(tmp_path: Path) -> None:
    write_config(tmp_path, {"required_context": [{"path": "AGENTS.md", "kind": "context"}]})

    result = check_context_preflight(tmp_path)

    assert result["passed"] is False
    assert result["issues"] == [
        {"path": "AGENTS.md", "kind": "context", "required_by": None, "reason": "source_missing"}
    ]


def test_check_context_preflight_passes_and_uses_cache(tmp_path: Path) -> None:
    doc = tmp_path / "AGENTS.md"
    doc.write_text("v1", encoding="utf-8")
    stored = tmp_path / ".harness" / "context" / "context-agents.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("v1", encoding="utf-8")
    write_config(tmp_path, {"required_context": [{"path": "AGENTS.md", "kind": "context"}]})
    write_manifest_for_doc(tmp_path, doc, stored)

    first = check_context_preflight(tmp_path)
    second = check_context_preflight(tmp_path)

    assert first["passed"] is True
    assert first["cache"] == "miss"
    assert second["passed"] is True
    assert second["cache"] == "hit"
    assert preflight_cache_path(tmp_path, None).exists()


def test_check_context_preflight_detects_changed_source(tmp_path: Path) -> None:
    doc = tmp_path / "AGENTS.md"
    doc.write_text("v1", encoding="utf-8")
    stored = tmp_path / ".harness" / "context" / "context-agents.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("v1", encoding="utf-8")
    write_config(tmp_path, {"required_context": [{"path": "AGENTS.md", "kind": "context"}]})
    write_manifest_for_doc(tmp_path, doc, stored)

    doc.write_text("v2", encoding="utf-8")
    result = check_context_preflight(tmp_path)

    assert result["passed"] is False
    assert result["issues"][0]["reason"] == "source_changed_since_ingest"


def test_require_context_preflight_respects_skip_and_policy(tmp_path: Path) -> None:
    write_config(tmp_path, {"required_context": [{"path": "missing.md"}]})
    require_context_preflight(tmp_path, "TASK-001", skip_preflight=True)

    write_config(
        tmp_path,
        {
            "required_context": [{"path": "missing.md"}],
            "policy": {"context_preflight_required_before_start": False},
        },
    )
    require_context_preflight(tmp_path, "TASK-001")


def test_require_context_preflight_blocks_with_human_text(tmp_path: Path) -> None:
    write_config(tmp_path, {"required_context": [{"path": "AGENTS.md"}]})

    with pytest.raises(SystemExit) as exc:
        require_context_preflight(tmp_path, "TASK-001")

    assert "Start bloqueado" in str(exc.value)
    assert "AGENTS.md" in str(exc.value)


def test_render_preflight_text_handles_empty_requirements() -> None:
    assert render_preflight_text({"task_id": None, "requirements": []}) == (
        "Preflight de contexto: global\n"
        "- Nenhum contexto obrigatorio configurado."
    )

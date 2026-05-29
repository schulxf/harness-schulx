"""Focused tests for extracted path and storage helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_core import paths, storage


def test_harness_paths_keep_expected_state_layout(tmp_path: Path) -> None:
    assert paths.harness_root(tmp_path) == tmp_path / ".harness"
    assert paths.config_path(tmp_path) == tmp_path / ".harness" / "config.json"
    assert paths.tasks_index_path(tmp_path) == tmp_path / ".harness" / "tasks" / "index.json"
    assert paths.queue_path(tmp_path) == tmp_path / ".harness" / "queue" / "index.json"
    assert paths.supervisor_state_path(tmp_path) == (
        tmp_path / ".harness" / "supervisor" / "state.json"
    )
    assert paths.checkpoints_root(tmp_path) == tmp_path / ".harness" / "checkpoints"
    assert paths.checkpoints_root(tmp_path, "TASK-001") == (
        tmp_path / ".harness" / "checkpoints" / "TASK-001"
    )
    assert paths.artifacts_index_path(tmp_path) == (
        tmp_path / ".harness" / "artifacts" / "index.json"
    )
    assert paths.hub_repo_registry_path(tmp_path) == (
        tmp_path / ".harness" / "dashboard" / "hub" / "repos.json"
    )
    assert paths.agent_registry_path(tmp_path) == (
        tmp_path / ".harness" / "agents" / "registry.json"
    )
    assert paths.telegram_state_path(tmp_path) == (
        tmp_path / ".harness" / "telegram" / "state.json"
    )
    assert paths.telegram_inbox_root(tmp_path) == tmp_path / ".harness" / "inbox" / "telegram"
    assert paths.telegram_media_root(tmp_path) == (
        tmp_path / ".harness" / "inbox" / "telegram" / "media"
    )
    assert paths.telegram_codex_root(tmp_path) == tmp_path / ".harness" / "telegram" / "codex"


def test_task_scoped_paths_are_stable(tmp_path: Path) -> None:
    assert paths.preflight_cache_path(tmp_path) == (
        tmp_path / ".harness" / "context" / "preflight-cache" / "global.json"
    )
    assert paths.preflight_cache_path(tmp_path, "TASK-001") == (
        tmp_path / ".harness" / "context" / "preflight-cache" / "TASK-001.json"
    )
    assert paths.contract_file_path(tmp_path, "TASK-001") == (
        tmp_path / ".harness" / "contracts" / "TASK-001.json"
    )
    assert paths.evaluation_markdown_path(tmp_path, "TASK-001") == (
        tmp_path / ".harness" / "evaluations" / "TASK-001.md"
    )


def test_resolve_repo_path_expands_relative_paths_inside_repo(tmp_path: Path) -> None:
    resolved = paths.resolve_repo_path(tmp_path, "docs/../tasks/TASK-001.md")

    assert resolved == (tmp_path / "tasks" / "TASK-001.md").resolve(strict=False)


def test_root_safety_accepts_root_and_children_but_rejects_siblings(tmp_path: Path) -> None:
    child = tmp_path / "nested" / "file.txt"
    sibling = tmp_path.parent / f"{tmp_path.name}-sibling" / "file.txt"

    assert paths.is_inside_root(tmp_path, tmp_path) is True
    assert paths.is_inside_root(tmp_path, child) is True
    assert paths.is_inside_root(tmp_path, sibling) is False
    assert paths.assert_inside_root(tmp_path, child, label="artifact") == child.resolve(strict=False)

    with pytest.raises(SystemExit, match="artifact fora do repo bloqueado"):
        paths.assert_inside_root(tmp_path, sibling, label="artifact")


def test_relative_and_normalized_path_helpers_use_posix_keys(tmp_path: Path) -> None:
    child = tmp_path / "nested" / "file.txt"
    outside = tmp_path.parent / "outside.txt"

    assert paths.relative_to_root(tmp_path, child) == "nested/file.txt"
    assert paths.relative_to_root(tmp_path, outside).endswith("/outside.txt")
    assert paths.to_posix(Path("a") / "b") == "a/b"
    assert paths.to_posix("a\\b\\c") == "a/b/c"
    assert paths.to_posix("") == ""
    assert paths.normalize_path_key(child) == paths.normalize_path_key(child.parent / "." / child.name)


def test_text_and_json_storage_round_trip_with_created_parents(tmp_path: Path) -> None:
    text_path = tmp_path / "nested" / "note.txt"
    json_path = tmp_path / "nested" / "state.json"

    storage.write_text(text_path, "hello\n")
    storage.write_json(json_path, {"ok": True, "items": [1, 2]})

    assert text_path.read_bytes() == b"hello\n"
    assert storage.read_text(text_path) == "hello\n"
    assert storage.read_json(json_path) == {"ok": True, "items": [1, 2]}
    assert json_path.read_text(encoding="utf-8").endswith("\n")
    assert storage.read_json(tmp_path / "missing.json", default={"missing": True}) == {"missing": True}


def test_text_and_json_writes_use_temp_file_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    original_replace = storage.os.replace

    def replace_spy(src: Path | str, dst: Path | str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        calls.append((src_path, dst_path))
        assert src_path.parent == dst_path.parent
        assert src_path.name != dst_path.name
        original_replace(src_path, dst_path)

    monkeypatch.setattr(storage.os, "replace", replace_spy)

    text_path = tmp_path / "nested" / "atomic.txt"
    json_path = tmp_path / "nested" / "atomic.json"
    storage.write_text(text_path, "atomic\n")
    storage.write_json(json_path, {"ok": True})

    assert text_path.read_text(encoding="utf-8") == "atomic\n"
    assert storage.read_json(json_path) == {"ok": True}
    assert [dst for _, dst in calls] == [text_path, json_path]
    assert list((tmp_path / "nested").glob("*.tmp")) == []


def test_read_text_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfhello")

    assert storage.read_text(path) == "hello"


def test_jsonl_storage_skips_non_dict_and_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "events" / "stream.jsonl"

    storage.append_jsonl(path, {"event": 1})
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n")
        handle.write("[1, 2]\n")
        handle.write("{not json}\n")
    storage.append_jsonl(path, {"event": 2})

    assert storage.read_jsonl(path) == [{"event": 1}, {"event": 2}]


def test_read_jsonl_tail_reads_recent_records_without_loading_contract(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    for index in range(20):
        storage.append_jsonl(path, {"index": index})

    assert storage.read_jsonl_tail(path, 3) == [{"index": 17}, {"index": 18}, {"index": 19}]
    assert storage.read_jsonl_tail(path, 0) == []
    assert storage.read_jsonl_tail(tmp_path / "missing.jsonl", 10) == []

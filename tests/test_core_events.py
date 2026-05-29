from __future__ import annotations

from pathlib import Path

from harness_core.events import (
    append_event,
    append_harness_event,
    read_new_harness_events,
    read_recent_harness_events,
    telegram_message_from_harness_event,
)
from harness_core.paths import event_stream_path
from harness_core.storage import append_jsonl, read_jsonl


def test_append_harness_event_writes_global_and_run_streams(tmp_path: Path) -> None:
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-a"
    run_dir.mkdir(parents=True)

    event = append_harness_event(tmp_path, "run_started", {"run_id": "run-a"}, run_dir=run_dir)

    assert event["type"] == "run_started"
    assert event["task_id"] == "TASK-001"
    assert event["project"] == tmp_path.name
    assert event["id"].startswith("EVT-")
    assert read_jsonl(event_stream_path(tmp_path))[0]["id"] == event["id"]
    assert read_jsonl(run_dir / "events.jsonl")[0]["id"] == event["id"]


def test_append_harness_event_uses_explicit_task_and_agent(tmp_path: Path) -> None:
    event = append_harness_event(
        tmp_path,
        "custom",
        {"task_id": "TASK-PAYLOAD", "agent_id": "payload-agent"},
        task_id="TASK-EXPLICIT",
        agent_id="agent-explicit",
        source="test",
    )

    assert event["task_id"] == "TASK-EXPLICIT"
    assert event["agent_id"] == "agent-explicit"
    assert event["source"] == "test"


def test_read_recent_harness_events_tails_and_filters_global_stream(tmp_path: Path) -> None:
    for index in range(5):
        append_harness_event(tmp_path, f"event-{index}", {"task_id": f"TASK-{index % 2:03d}"})

    assert [event["type"] for event in read_recent_harness_events(tmp_path, limit=2)] == [
        "event-3",
        "event-4",
    ]
    assert [event["type"] for event in read_recent_harness_events(tmp_path, limit=10, task_id="TASK-001")] == [
        "event-1",
        "event-3",
    ]


def test_read_recent_harness_events_reads_legacy_run_stream_when_global_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / ".harness" / "runs" / "TASK-001" / "run-a"
    run_dir.mkdir(parents=True)
    append_jsonl(run_dir / "events.jsonl", {"ts": "2026-01-01T00:00:00+00:00", "type": "legacy"})

    events = read_recent_harness_events(tmp_path)

    assert events == [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "type": "legacy",
            "run_dir": str(run_dir),
            "task_id": "TASK-001",
        }
    ]


def test_read_new_harness_events_returns_incremental_events(tmp_path: Path) -> None:
    append_harness_event(tmp_path, "first", {})
    events, offset = read_new_harness_events(tmp_path)
    append_harness_event(tmp_path, "second", {})

    new_events, new_offset = read_new_harness_events(tmp_path, offset)

    assert [event["type"] for event in events] == ["first"]
    assert [event["type"] for event in new_events] == ["second"]
    assert new_offset > offset


def test_read_new_harness_events_skips_invalid_lines(tmp_path: Path) -> None:
    path = event_stream_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{bad json}\n", encoding="utf-8")
    append_jsonl(path, {"type": "valid"})

    events, _offset = read_new_harness_events(tmp_path)

    assert events == [{"type": "valid"}]


def test_telegram_message_from_harness_event_uses_summary_then_type() -> None:
    assert telegram_message_from_harness_event(
        {"project": "proj", "task_id": "TASK-001", "type": "run_started", "payload": {"summary": "feito"}}
    ) == "Harness: proj\nTASK-001: feito"

    assert telegram_message_from_harness_event(
        {"project": "proj", "type": "run_started", "payload": {"task_id": "TASK-002"}}
    ) == "Harness: proj\nTASK-002: run_started"


def test_append_event_writes_legacy_run_event(tmp_path: Path) -> None:
    append_event(tmp_path, "legacy", {"ok": True})

    assert read_jsonl(tmp_path / "events.jsonl")[0]["type"] == "legacy"

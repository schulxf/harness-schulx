"""Typed payloads for the core Harness JSON records."""

from __future__ import annotations

from typing import TypedDict


class TaskRecord(TypedDict, total=False):
    task_id: str
    title: str
    body: str
    source: str
    status: str
    created_at: str
    updated_at: str


class QueueRecord(TypedDict, total=False):
    id: str
    task_id: str
    title: str
    body: str
    status: str
    created_at: str
    updated_at: str


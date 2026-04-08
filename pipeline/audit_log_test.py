"""Tests for parallel-runs.jsonl audit log."""

import json

from pipeline.audit_log import append_parallel_run


def test_append_creates_file_and_adds_line(tmp_path):
    log_path = tmp_path / "parallel-runs.jsonl"

    record = {
        "task_id": "task-123",
        "processor": "lite",
        "cost_usd": 0.42,
        "timestamp": "2026-04-08T10:00:00Z",
    }
    append_parallel_run(log_path, record)

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "task_id": "task-123",
        "processor": "lite",
        "cost_usd": 0.42,
        "timestamp": "2026-04-08T10:00:00Z",
    }


def test_append_appends_to_existing_file(tmp_path):
    log_path = tmp_path / "parallel-runs.jsonl"
    r1 = {"task_id": "t1", "processor": "lite", "cost_usd": 0.1, "timestamp": "t"}
    r2 = {"task_id": "t2", "processor": "lite", "cost_usd": 0.2, "timestamp": "t"}
    append_parallel_run(log_path, r1)
    append_parallel_run(log_path, r2)

    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["task_id"] == "t1"
    assert json.loads(lines[1])["task_id"] == "t2"

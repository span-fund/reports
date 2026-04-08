"""Append-only JSONL audit log for Parallel.ai calls.

One line per call with (task_id, processor, cost_usd, timestamp). Lives in
<target>/parallel-runs.jsonl and is committed together with README.md.
"""

import json
from pathlib import Path
from typing import Any


def append_parallel_run(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")

"""Disk-backed plain-JSON cache.

Key shape: (target, namespace, key) → JSON-serialisable value.
TTL is configured per namespace at construction time. Storage layout:
    <root>/<target>/<namespace>/<sha1(key)>.json
Each file stores {"stored_at": <epoch_seconds>, "value": <payload>}.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Cache:
    root: Path
    ttls: dict[str, int]
    now: Callable[[], float] = time.time

    def _path(self, target: str, namespace: str, key: str) -> Path:
        h = hashlib.sha1(key.encode()).hexdigest()
        return self.root / target / namespace / f"{h}.json"

    def get(self, target: str, namespace: str, key: str) -> Any | None:
        path = self._path(target, namespace, key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        ttl = self.ttls.get(namespace)
        if ttl is not None and self.now() - payload["stored_at"] > ttl:
            return None
        return payload["value"]

    def set(self, target: str, namespace: str, key: str, value: Any) -> None:
        path = self._path(target, namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stored_at": self.now(), "value": value}))

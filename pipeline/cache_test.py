"""Tests for disk-backed plain-JSON cache.

Cache is keyed by (target, namespace, key). TTL is per-namespace. Tests use a
real filesystem via pytest's tmp_path — no mocks.
"""

from pipeline.cache import Cache


def test_get_returns_none_on_miss(tmp_path):
    cache = Cache(root=tmp_path, ttls={"parallel": 7 * 86400})

    assert cache.get("ethena", "parallel", "overview:totalSupply") is None


def test_set_then_get_returns_value(tmp_path):
    cache = Cache(root=tmp_path, ttls={"parallel": 7 * 86400})

    cache.set("ethena", "parallel", "overview:totalSupply", {"value": "1000000"})

    assert cache.get("ethena", "parallel", "overview:totalSupply") == {"value": "1000000"}


def test_expired_entry_returns_none(tmp_path):
    clock = [1_000_000.0]
    cache = Cache(
        root=tmp_path,
        ttls={"onchain": 3600},  # 1h TTL on onchain namespace
        now=lambda: clock[0],
    )
    cache.set("ethena", "onchain", "totalSupply@0xabc", {"value": "1000000"})

    # 30 minutes later — still fresh
    clock[0] += 1800
    assert cache.get("ethena", "onchain", "totalSupply@0xabc") == {"value": "1000000"}

    # 2 hours past original set — expired
    clock[0] += 7200
    assert cache.get("ethena", "onchain", "totalSupply@0xabc") is None

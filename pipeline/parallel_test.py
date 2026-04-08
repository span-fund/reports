"""Tests for Parallel.ai SDK wrapper.

We mock at the SDK boundary — pass in a fake client with the shape we rely on.
The wrapper builds a minimal Task Group for the Overview section with a single
totalSupply claim, calls the injected client, and returns a Finding plus an
audit record.
"""

from pipeline.parallel import fetch_overview_total_supply


class FakeParallelClient:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []

    def run_task(self, *, processor: str, schema: dict, prompt: str) -> dict:
        self.calls.append({"processor": processor, "schema": schema, "prompt": prompt})
        return self.response


def test_wrapper_builds_task_group_and_parses_finding():
    client = FakeParallelClient(
        response={
            "task_id": "task-123",
            "cost_usd": 0.42,
            "output": {
                "totalSupply": "1000000",
                "evidence_url": "https://ethena.fi/stats",
                "evidence_date": "2026-04-08",
            },
        }
    )

    finding, audit = fetch_overview_total_supply(
        target_name="Ethena",
        target_domain="ethena.fi",
        tier="lite",
        client=client,
    )

    # Built the right task
    assert client.calls[0]["processor"] == "lite"
    assert "totalSupply" in client.calls[0]["schema"]["properties"]
    assert "ethena.fi" in client.calls[0]["prompt"]

    # Parsed finding
    assert finding.claim == "totalSupply"
    assert finding.value == "1000000"
    assert finding.source_kind == "parallel"
    assert finding.evidence_url == "https://ethena.fi/stats"
    assert finding.evidence_date == "2026-04-08"

    # Audit record ready for jsonl append
    assert audit["task_id"] == "task-123"
    assert audit["processor"] == "lite"
    assert audit["cost_usd"] == 0.42
    assert "timestamp" in audit

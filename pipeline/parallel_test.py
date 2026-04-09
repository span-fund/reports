"""Tests for Parallel.ai SDK wrapper.

We mock at the SDK boundary — pass in a fake client with the shape we rely on.
The wrapper builds a minimal Task Group for the Overview section with a single
totalSupply claim, calls the injected client, and returns a Finding plus an
audit record.
"""

from pipeline.overview_claims import OnchainSpec, OverviewClaim
from pipeline.parallel import fetch_overview_claims, fetch_overview_total_supply


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


def test_fetch_overview_claims_single_call_returns_finding_per_claim():
    """Wide Overview fetch: one Parallel task call returns structured findings
    for every claim in the manifest. Each claim's nested object carries its
    own value, evidence URL, date, and confidence."""
    claims = [
        OverviewClaim(
            name="frxusd_supply",
            kind="hard",
            display_label="frxUSD total supply",
            parallel_field="frxusd_supply",
            onchain=OnchainSpec(fetcher="total_supply", contract="0xabc", decimals=18),
        ),
        OverviewClaim(
            name="tvl_usd",
            kind="hard",
            display_label="TVL",
            parallel_field="tvl_usd",
            onchain=None,
        ),
        OverviewClaim(
            name="mechanism_summary",
            kind="soft",
            display_label="Mechanism one-liner",
            parallel_field="mechanism_summary",
            onchain=None,
        ),
    ]
    client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 1.25,
            "output": {
                "frxusd_supply": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/frxusd",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.92,
                },
                "tvl_usd": {
                    "value": "75000000",
                    "evidence_url": "https://defillama.com/protocol/frax",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.85,
                },
                "mechanism_summary": {
                    "value": "Over-collateralized USD stablecoin backed by sfrxUSD yield",
                    "evidence_url": "https://docs.frax.com",
                    "evidence_date": "2026-04-07",
                    "confidence": 0.9,
                },
            },
        }
    )

    findings, audit = fetch_overview_claims(
        target_name="frax-com",
        target_domain="frax.com",
        tier="lite",
        claims=claims,
        client=client,
    )

    # Exactly one Parallel call for all claims
    assert len(client.calls) == 1
    schema_props = client.calls[0]["schema"]["properties"]
    assert set(schema_props.keys()) == {"frxusd_supply", "tvl_usd", "mechanism_summary"}
    # Each field is a nested object carrying its own evidence metadata
    assert schema_props["frxusd_supply"]["type"] == "object"
    assert "value" in schema_props["frxusd_supply"]["properties"]
    assert "evidence_url" in schema_props["frxusd_supply"]["properties"]
    assert "confidence" in schema_props["frxusd_supply"]["properties"]

    # One Finding per claim, keyed by claim name
    by_name = {f.claim: f for f in findings}
    assert set(by_name.keys()) == {"frxusd_supply", "tvl_usd", "mechanism_summary"}
    assert by_name["frxusd_supply"].value == "1000000"
    assert by_name["frxusd_supply"].source_kind == "parallel"
    assert by_name["frxusd_supply"].evidence_url == "https://frax.com/frxusd"
    assert by_name["frxusd_supply"].confidence == 0.92
    assert by_name["tvl_usd"].value == "75000000"
    assert by_name["mechanism_summary"].confidence == 0.9

    # Audit record logged once for the whole task
    assert audit["task_id"] == "task-abc"
    assert audit["cost_usd"] == 1.25


def test_fetch_overview_claims_passes_through_cost_source():
    """The client response may carry a `cost_source` marker distinguishing
    an estimated price (from the local pricing table) from an actual billed
    cost. The audit record must preserve it so downstream reports can tell
    them apart.
    """
    claims = [
        OverviewClaim(
            name="tvl_usd",
            kind="hard",
            display_label="TVL",
            parallel_field="tvl_usd",
            onchain=None,
        ),
    ]
    client = FakeParallelClient(
        response={
            "task_id": "task-xyz",
            "cost_usd": 0.005,
            "cost_source": "estimated",
            "output": {
                "tvl_usd": {
                    "value": "1",
                    "evidence_url": "https://x",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
            },
        }
    )

    _, audit = fetch_overview_claims(
        target_name="x",
        target_domain="x.y",
        tier="lite",
        claims=claims,
        client=client,
    )

    assert audit["cost_usd"] == 0.005
    assert audit["cost_source"] == "estimated"


def test_fetch_overview_claims_defaults_cost_source_when_client_omits_it():
    """Backward-compat: older clients may not set `cost_source`. Default to
    "estimated" because that's how all current callers actually price runs."""
    claims = [
        OverviewClaim(
            name="tvl_usd",
            kind="hard",
            display_label="TVL",
            parallel_field="tvl_usd",
            onchain=None,
        ),
    ]
    client = FakeParallelClient(
        response={
            "task_id": "task-xyz",
            "cost_usd": 0.005,
            "output": {
                "tvl_usd": {
                    "value": "1",
                    "evidence_url": "https://x",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
            },
        }
    )

    _, audit = fetch_overview_claims(
        target_name="x",
        target_domain="x.y",
        tier="lite",
        claims=claims,
        client=client,
    )

    assert audit["cost_source"] == "estimated"

"""Parallel.ai SDK wrapper.

Builds a minimal Task Group for the Overview section (one claim: totalSupply)
against an injected client. The client protocol is deliberately narrow so we
can swap the real Parallel SDK or a fake in tests without touching call sites.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from pipeline.verdict_engine import Finding


class ParallelClient(Protocol):
    def run_task(self, *, processor: str, schema: dict, prompt: str) -> dict: ...


OVERVIEW_TOTALSUPPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "totalSupply": {
            "type": "string",
            "description": "Primary token total supply (human units)",
        },
        "evidence_url": {"type": "string"},
        "evidence_date": {
            "type": "string",
            "description": "ISO-8601 date (YYYY-MM-DD) of the cited source",
        },
        "confidence": {
            "type": "number",
            "description": (
                "Self-assessed confidence in the totalSupply value, 0.0-1.0. "
                "Use 0.9+ only when the primary source is authoritative and fresh."
            ),
        },
    },
    "required": ["totalSupply", "evidence_url", "evidence_date", "confidence"],
}


def fetch_overview_total_supply(
    *,
    target_name: str,
    target_domain: str,
    tier: str,
    client: ParallelClient,
) -> tuple[Finding, dict[str, Any]]:
    prompt = (
        f"Find the current total supply of the primary token for {target_name} "
        f"({target_domain}). Return the human-readable value plus the primary "
        f"source URL and its publication date."
    )
    response = client.run_task(
        processor=tier,
        schema=OVERVIEW_TOTALSUPPLY_SCHEMA,
        prompt=prompt,
    )
    output = response["output"]
    finding = Finding(
        claim="totalSupply",
        value=output["totalSupply"],
        source="parallel",
        source_kind="parallel",
        evidence_url=output["evidence_url"],
        evidence_date=output["evidence_date"],
        confidence=output.get("confidence"),
    )
    audit = {
        "task_id": response["task_id"],
        "processor": tier,
        "cost_usd": response["cost_usd"],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return finding, audit

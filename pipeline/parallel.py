"""Parallel.ai SDK wrapper.

Builds a minimal Task Group for the Overview section (one claim: totalSupply)
against an injected client. The client protocol is deliberately narrow so we
can swap the real Parallel SDK or a fake in tests without touching call sites.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from pipeline.overview_claims import OverviewClaim
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
        "cost_source": response.get("cost_source", "estimated"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return finding, audit


def _claim_field_schema() -> dict[str, Any]:
    """Sub-schema for a single Overview claim: value + evidence + confidence.

    Per project memory, output_schema rejects the `format` keyword — date
    constraints live in `description` text only.
    """
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": "Claim value as a human-readable string",
            },
            "evidence_url": {"type": "string"},
            "evidence_date": {
                "type": "string",
                "description": "ISO-8601 date (YYYY-MM-DD) of the cited source",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Self-assessed confidence 0.0-1.0. Use 0.9+ only when the "
                    "primary source is authoritative and fresh."
                ),
            },
        },
        "required": ["value", "evidence_url", "evidence_date", "confidence"],
    }


def build_overview_schema(claims: list[OverviewClaim]) -> dict[str, Any]:
    """Compose the wide Overview task schema from a claim manifest."""
    props = {claim.parallel_field: _claim_field_schema() for claim in claims}
    return {
        "type": "object",
        "properties": props,
        "required": [claim.parallel_field for claim in claims],
    }


def fetch_overview_claims(
    *,
    target_name: str,
    target_domain: str,
    tier: str,
    claims: list[OverviewClaim],
    client: ParallelClient,
) -> tuple[list[Finding], dict[str, Any]]:
    """Single Parallel call covering every Overview claim in the manifest.

    Returns one Finding per claim (keyed by `claim.name`, not `parallel_field`,
    so the orchestrator can cross-check against on-chain findings that share
    the same canonical claim name).
    """
    schema = build_overview_schema(claims)
    lines = [
        f"Research the Overview section for {target_name} ({target_domain}).",
        "For every field below, return the best current value plus the primary "
        "source URL and its publication date.",
        "",
        "Fields:",
    ]
    for claim in claims:
        lines.append(f"- {claim.parallel_field}: {claim.display_label}")
    prompt = "\n".join(lines)

    response = client.run_task(processor=tier, schema=schema, prompt=prompt)
    output = response["output"]

    findings: list[Finding] = []
    for claim in claims:
        field = output[claim.parallel_field]
        findings.append(
            Finding(
                claim=claim.name,
                value=field["value"],
                source="parallel",
                source_kind="parallel",
                evidence_url=field["evidence_url"],
                evidence_date=field["evidence_date"],
                confidence=field.get("confidence"),
            )
        )

    audit = {
        "task_id": response["task_id"],
        "processor": tier,
        "cost_usd": response["cost_usd"],
        "cost_source": response.get("cost_source", "estimated"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return findings, audit

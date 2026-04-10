"""Parallel.ai SDK wrapper.

Builds a minimal Task Group for the Overview section (one claim: totalSupply)
against an injected client. The client protocol is deliberately narrow so we
can swap the real Parallel SDK or a fake in tests without touching call sites.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from pipeline.overview_claims import OverviewClaim
from pipeline.section_claims import SectionClaim
from pipeline.team_claims import TeamClaim
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


def _build_overview_prompt(
    *,
    target_name: str,
    target_domain: str,
    claims: list[OverviewClaim],
    max_chars: int = 4000,
) -> str:
    """Compose the Parallel prompt for an Overview manifest.

    For every claim that carries an `OnchainSpec`, the prompt embeds a hint
    naming the contract address, the chain, and (where applicable) the
    function selector — this is what eliminates the "Not found" failure
    mode for well-known tokens that Parallel previously had to guess at
    (issue #13). Hints also steer toward authoritative sources (Etherscan,
    project docs) over aggregators (CMC, CoinGecko, DefiLlama) which drift
    more.

    The prompt is bounded by `max_chars`. If the full hinted prompt would
    overflow, hints are dropped from trailing claims (keeping their bare
    `- field: label` line) and a `[...truncated]` marker is appended so the
    truncation is visible in the audit log.
    """
    header = [
        f"Research the Overview section for {target_name} ({target_domain}).",
        "For every field below, return the best current value plus the primary "
        "source URL and its publication date.",
        "",
        "Fields:",
    ]

    full_lines = [_render_claim_line(c) for c in claims]
    bare_lines = [f"- {c.parallel_field}: {c.display_label}" for c in claims]

    # Try the fully-hinted prompt first; if it overflows, demote trailing
    # claims to bare lines until we fit, then append a truncation marker.
    rendered = full_lines[:]
    truncated = False
    while True:
        candidate = "\n".join(header + rendered)
        if truncated:
            candidate = candidate + "\n[...truncated]"
        if len(candidate) <= max_chars:
            return candidate
        # Find the last fully-hinted line and demote it to bare.
        demoted_any = False
        for i in range(len(rendered) - 1, -1, -1):
            if rendered[i] != bare_lines[i]:
                rendered[i] = bare_lines[i]
                demoted_any = True
                truncated = True
                break
        if not demoted_any:
            # All hints already stripped — return as-is even if still over
            # (caller's max_chars is unreachably small for the bare list).
            return candidate


# ERC standard function selectors that Parallel can be told about by name.
# ERC-20 metadata + balance and the ERC-4626 vault accounting surface — these
# are the selectors we expect to see on Overview claims for token & vault
# targets. Anything outside this set falls back to the raw 4-byte selector.
_KNOWN_SELECTORS = {
    # ERC-20
    "0x06fdde03": "name()",
    "0x95d89b41": "symbol()",
    "0x313ce567": "decimals()",
    "0x18160ddd": "totalSupply()",
    "0x70a08231": "balanceOf(address)",
    # ERC-4626 vault
    "0x01e1d114": "totalAssets()",
    "0x07a2d13a": "convertToAssets(uint256)",
}


def _selector_label(selector: str) -> str:
    return _KNOWN_SELECTORS.get(selector.lower(), f"function selector {selector}")


def _render_claim_line(claim: OverviewClaim) -> str:
    base = f"- {claim.parallel_field}: {claim.display_label}"
    spec = claim.onchain
    if spec is None:
        return base
    if spec.fetcher == "total_supply":
        hint = (
            f". This is the ERC-20 at `{spec.contract}` on {spec.chain} mainnet. "
            "Cite Etherscan or the official project docs, not third-party aggregators."
        )
    elif spec.fetcher == "contract_read":
        fn_label = _selector_label(spec.selector or "")
        hint = (
            f". Read the `{fn_label}` function of the contract at `{spec.contract}` "
            f"on {spec.chain} mainnet. Cite Etherscan or the official project docs, "
            "not third-party aggregators."
        )
    elif spec.fetcher == "token_balance":
        hint = (
            f". This is the ERC-20 token balance held by `{spec.holder}` "
            f"of the token at `{spec.contract}` on {spec.chain} mainnet. "
            "Cite Etherscan or the official project docs, not third-party aggregators."
        )
    else:
        hint = ""
    return base + hint


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
    prompt = _build_overview_prompt(
        target_name=target_name,
        target_domain=target_domain,
        claims=claims,
    )

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


# ---------------------------------------------------------------------------
# Generic section fetch (Phase 5)
# ---------------------------------------------------------------------------


def build_section_schema(claims: list[SectionClaim]) -> dict[str, Any]:
    """Build Parallel output schema for a generic section manifest."""
    props = {claim.parallel_field: _claim_field_schema() for claim in claims}
    return {
        "type": "object",
        "properties": props,
        "required": [claim.parallel_field for claim in claims],
    }


def _build_section_prompt(
    *,
    section_name: str,
    target_name: str,
    target_domain: str,
    claims: list[SectionClaim],
) -> str:
    header = [
        f"Research the {section_name} section for {target_name} ({target_domain}).",
        "For every field below, return the best current value plus the primary "
        "source URL and its publication date.",
        "",
        "Fields:",
    ]
    lines = [f"- {c.parallel_field}: {c.display_label}" for c in claims]
    return "\n".join(header + lines)


def fetch_section_claims(
    *,
    section_name: str,
    target_name: str,
    target_domain: str,
    tier: str,
    claims: list[SectionClaim],
    client: ParallelClient,
) -> tuple[list[Finding], dict[str, Any]]:
    """Single Parallel call covering every claim in a generic section manifest."""
    schema = build_section_schema(claims)
    prompt = _build_section_prompt(
        section_name=section_name,
        target_name=target_name,
        target_domain=target_domain,
        claims=claims,
    )
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


def build_team_schema(claims: list[TeamClaim]) -> dict[str, Any]:
    """Mirror of build_overview_schema for the Team manifest. Each team claim
    becomes a `value/evidence_url/evidence_date/confidence` sub-object.
    """
    props = {claim.parallel_field: _claim_field_schema() for claim in claims}
    return {
        "type": "object",
        "properties": props,
        "required": [claim.parallel_field for claim in claims],
    }


def _build_team_prompt(
    *,
    target_name: str,
    target_domain: str,
    claims: list[TeamClaim],
) -> str:
    header = [
        f"Research the Team / Ownership section for {target_name} ({target_domain}).",
        "For every field below, return the best current value plus the primary "
        "source URL and its publication date.",
        "Prefer official company sources, regulatory filings and registry "
        "records over press articles or Crunchbase.",
        "",
        "Fields:",
    ]
    lines = [f"- {c.parallel_field}: {c.display_label}" for c in claims]
    return "\n".join(header + lines)


def fetch_team_claims(
    *,
    target_name: str,
    target_domain: str,
    tier: str,
    claims: list[TeamClaim],
    client: ParallelClient,
) -> tuple[list[Finding], dict[str, Any]]:
    """Single Parallel call covering every Team claim in the manifest.

    Returns one Finding per claim keyed by `claim.name` (officer:..., owner:...
    or generic) so the orchestrator can cross-check uniformly against legal-
    registry findings.
    """
    schema = build_team_schema(claims)
    prompt = _build_team_prompt(
        target_name=target_name,
        target_domain=target_domain,
        claims=claims,
    )
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

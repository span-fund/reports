"""Tests for Parallel.ai SDK wrapper.

We mock at the SDK boundary — pass in a fake client with the shape we rely on.
The wrapper builds a minimal Task Group for the Overview section with a single
totalSupply claim, calls the injected client, and returns a Finding plus an
audit record.
"""

from pathlib import Path

from pipeline.overview_claims import OnchainSpec, OverviewClaim
from pipeline.parallel import (
    _build_overview_prompt,
    build_section_schema,
    fetch_overview_claims,
    fetch_overview_total_supply,
    fetch_section_claims,
)
from pipeline.section_claims import SectionClaim


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
            onchain=OnchainSpec(
                fetcher="total_supply",
                contract="0xabc",
                decimals=18,
                chain="ethereum",
            ),
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
    # Per issue #13: prompt must mention the on-chain contract address from
    # the OnchainSpec so Parallel knows which token/chain to research.
    assert "0xabc" in client.calls[0]["prompt"]
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


# ---------------------------------------------------------------------------
# Prompt-builder unit tests (issue #13): on-chain hints
# ---------------------------------------------------------------------------


def _claim(
    name: str,
    parallel_field: str | None = None,
    onchain: OnchainSpec | None = None,
    kind: str = "hard",
    display_label: str | None = None,
) -> OverviewClaim:
    return OverviewClaim(
        name=name,
        kind=kind,
        display_label=display_label or name,
        parallel_field=parallel_field or name,
        onchain=onchain,
    )


def test_build_prompt_total_supply_includes_contract_chain_and_authoritative_hint():
    """For a claim backed by an on-chain `total_supply` fetcher, the prompt
    must give Parallel the contract address, the chain, and steer it toward
    authoritative sources rather than aggregators — that's the entire point
    of the hint per issue #13."""
    claims = [
        _claim(
            "fxs_supply",
            display_label="FXS (Frax Share) total supply",
            onchain=OnchainSpec(
                fetcher="total_supply",
                contract="0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0",
                decimals=18,
                chain="ethereum",
            ),
        ),
    ]
    prompt = _build_overview_prompt(
        target_name="frax-com",
        target_domain="frax.com",
        claims=claims,
    )

    # Contract address — verbatim, mixed-case preserved (Etherscan-friendly).
    assert "0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0" in prompt
    # Chain name from the spec, not hard-coded.
    assert "ethereum" in prompt.lower()
    # Authoritative-source steering — Etherscan + project docs over aggregators.
    assert "Etherscan" in prompt
    # Display label still present so Parallel knows the human-readable claim.
    assert "FXS (Frax Share) total supply" in prompt


def test_build_prompt_contract_read_known_selector_uses_function_name():
    """contract_read with a known ERC selector should expand to the human
    function name (totalAssets() for 0x01e1d114) — that's how Parallel can
    actually disambiguate the metric instead of guessing what 0x01e1d114
    means."""
    claims = [
        _claim(
            "sfrxusd_total_assets",
            display_label="sfrxUSD totalAssets (ERC-4626)",
            onchain=OnchainSpec(
                fetcher="contract_read",
                contract="0xcf62F905562626CfcDD2261162a51fd02Fc9c5b6",
                selector="0x01e1d114",
                decimals=18,
                chain="ethereum",
            ),
        ),
    ]
    prompt = _build_overview_prompt(target_name="frax-com", target_domain="frax.com", claims=claims)
    assert "0xcf62F905562626CfcDD2261162a51fd02Fc9c5b6" in prompt
    assert "totalAssets()" in prompt
    # Raw selector should NOT leak into the hint when we can name the function.
    assert "0x01e1d114" not in prompt


def test_build_prompt_contract_read_unknown_selector_falls_back_to_raw():
    """An unrecognised selector still gets surfaced — better to give Parallel
    the raw 4-byte selector than to silently drop the hint."""
    claims = [
        _claim(
            "weird_metric",
            onchain=OnchainSpec(
                fetcher="contract_read",
                contract="0xDEAD",
                selector="0xcafef00d",
                decimals=18,
                chain="ethereum",
            ),
        ),
    ]
    prompt = _build_overview_prompt(target_name="x", target_domain="x.y", claims=claims)
    assert "0xcafef00d" in prompt
    assert "function selector" in prompt


def test_build_prompt_known_erc20_and_erc4626_selectors_render_by_name():
    """The selector map covers the standard ERC-20 metadata surface plus the
    ERC-4626 vault accounting surface — verify each one renders as the human
    function name (not raw selector) so future Overview claims that read
    decimals/symbol/convertToAssets etc. all benefit from the hint."""
    cases = {
        "0x06fdde03": "name()",
        "0x95d89b41": "symbol()",
        "0x313ce567": "decimals()",
        "0x18160ddd": "totalSupply()",
        "0x70a08231": "balanceOf(address)",
        "0x01e1d114": "totalAssets()",
        "0x07a2d13a": "convertToAssets(uint256)",
    }
    for selector, expected in cases.items():
        claims = [
            _claim(
                "metric",
                onchain=OnchainSpec(
                    fetcher="contract_read",
                    contract="0xCAFE",
                    selector=selector,
                    decimals=18,
                    chain="ethereum",
                ),
            ),
        ]
        prompt = _build_overview_prompt(target_name="x", target_domain="x.y", claims=claims)
        assert expected in prompt, f"{selector} should render as {expected}"
        assert selector not in prompt, f"raw {selector} leaked into prompt"


def test_build_prompt_token_balance_mentions_holder_and_token():
    """token_balance hints have to identify both sides — the holder address
    and the token contract — otherwise Parallel can't reproduce the metric."""
    claims = [
        _claim(
            "psm_usdc_balance",
            display_label="USDC held by PSM",
            onchain=OnchainSpec(
                fetcher="token_balance",
                contract="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
                holder="0x37305B1cD40574E4C5Ce33f8e8306Be057fD7341",  # PSM
                decimals=6,
                chain="ethereum",
            ),
        ),
    ]
    prompt = _build_overview_prompt(target_name="x", target_domain="x.y", claims=claims)
    assert "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48" in prompt
    assert "0x37305B1cD40574E4C5Ce33f8e8306Be057fD7341" in prompt


def test_build_prompt_frax_8claim_manifest_stays_under_4000_chars(tmp_path):
    """The real frax-com 8-claim manifest must still fit comfortably under
    the 4000-char hard cap with hints fully expanded — that's the cap the
    issue calls out as the budget for normal manifests."""
    from pipeline.overview_claims import load_overview_claims

    manifest_path = (
        Path(__file__).resolve().parent.parent / "targets" / "frax-com" / "overview_claims.json"
    )
    claims = load_overview_claims(manifest_path)
    prompt = _build_overview_prompt(target_name="frax-com", target_domain="frax.com", claims=claims)
    assert len(prompt) <= 4000
    # And the FXS contract from the manifest is in the rendered prompt —
    # this is the regression hook for the original "Not found" failure.
    assert "0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0" in prompt
    # No truncation needed for an 8-claim manifest.
    assert "[...truncated]" not in prompt


def test_build_prompt_truncates_trailing_hints_when_over_budget():
    """When a manifest is large enough that the fully-hinted prompt exceeds
    `max_chars`, hints get dropped from trailing claims first (their bare
    `- field: label` line stays so the field isn't lost), and the prompt
    ends with a `[...truncated]` marker so the truncation is visible in
    the audit log."""
    # Construct 20 contract_read claims — way more than the cap can hold
    # with full hints, but fits as bare lines.
    claims = [
        _claim(
            f"metric_{i:02d}",
            display_label=f"Metric number {i}",
            onchain=OnchainSpec(
                fetcher="contract_read",
                contract=f"0x{i:040x}",
                selector="0x01e1d114",
                decimals=18,
                chain="ethereum",
            ),
        )
        for i in range(20)
    ]
    # Pick a small cap that forces truncation but still fits all bare lines.
    prompt = _build_overview_prompt(
        target_name="t",
        target_domain="t.io",
        claims=claims,
        max_chars=1500,
    )
    assert len(prompt) <= 1500
    assert "[...truncated]" in prompt
    # First claim still has its hint (we drop trailing hints first).
    assert "metric_00" in prompt
    assert "0x" + "0" * 39 + "0" in prompt
    # Last claim still has its bare line — field never silently disappears.
    assert "metric_19" in prompt
    # ...but the last claim's hint specifically is gone.
    assert "0x" + "0" * 38 + "13" not in prompt


# ---------------------------------------------------------------------------
# Phase 5: generic section schema & fetch
# ---------------------------------------------------------------------------


def test_build_section_schema_produces_nested_claim_objects():
    claims = [
        SectionClaim(
            name="annual_revenue",
            kind="hard",
            display_label="Annualized revenue",
            parallel_field="annual_revenue",
        ),
        SectionClaim(
            name="revenue_commentary",
            kind="soft",
            display_label="Revenue commentary",
            parallel_field="revenue_commentary",
        ),
    ]
    schema = build_section_schema(claims)

    assert schema["type"] == "object"
    assert set(schema["properties"].keys()) == {"annual_revenue", "revenue_commentary"}
    assert set(schema["required"]) == {"annual_revenue", "revenue_commentary"}
    # Each field is the standard value/evidence/confidence sub-object
    prop = schema["properties"]["annual_revenue"]
    assert prop["type"] == "object"
    assert "value" in prop["properties"]
    assert "evidence_url" in prop["properties"]
    assert "confidence" in prop["properties"]


def test_fetch_section_claims_returns_findings_keyed_by_name():
    claims = [
        SectionClaim(
            name="collateral_composition",
            kind="hard",
            display_label="Collateral breakdown",
            parallel_field="collateral_composition",
        ),
        SectionClaim(
            name="collateralization_ratio",
            kind="hard",
            display_label="Coll. ratio",
            parallel_field="collateralization_ratio",
        ),
    ]
    client = FakeParallelClient(
        response={
            "task_id": "task-sec-1",
            "cost_usd": 0.50,
            "output": {
                "collateral_composition": {
                    "value": "60% USDC, 30% ETH, 10% RWA",
                    "evidence_url": "https://example.com/collateral",
                    "evidence_date": "2026-04-10",
                    "confidence": 0.88,
                },
                "collateralization_ratio": {
                    "value": "119.58%",
                    "evidence_url": "https://example.com/ratio",
                    "evidence_date": "2026-04-10",
                    "confidence": 0.95,
                },
            },
        }
    )

    findings, audit = fetch_section_claims(
        section_name="Collateral",
        target_name="sky-protocol",
        target_domain="sky.money",
        tier="base",
        claims=claims,
        client=client,
    )

    assert len(findings) == 2
    by_name = {f.claim: f for f in findings}
    assert by_name["collateral_composition"].value == "60% USDC, 30% ETH, 10% RWA"
    assert by_name["collateral_composition"].source_kind == "parallel"
    assert by_name["collateralization_ratio"].confidence == 0.95
    assert audit["task_id"] == "task-sec-1"
    # Prompt must mention the section name
    assert "Collateral" in client.calls[0]["prompt"]

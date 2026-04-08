"""Tests for section-renderer Overview.

Takes a section JSON (claims + verdicts + findings) and returns markdown with
verdict tags and citations from all sources.
"""

from pipeline.section_renderer import render_overview
from pipeline.verdict_engine import Finding, Verdict


def test_overview_renders_claim_with_verdict_tag_and_both_citations():
    section = {
        "target_name": "Ethena",
        "claims": [
            {
                "name": "totalSupply",
                "verdict": Verdict(tag="✅", rationale="2 sources agree"),
                "findings": [
                    Finding(
                        claim="totalSupply",
                        value="1000000",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://ethena.fi/docs",
                        evidence_date="2026-04-08",
                    ),
                    Finding(
                        claim="totalSupply",
                        value="1000000",
                        source="etherscan",
                        source_kind="onchain",
                        evidence_url="https://etherscan.io/token/0xabc",
                        evidence_date="2026-04-08",
                    ),
                ],
            }
        ],
    }

    md = render_overview(section)

    assert "# Overview" in md
    assert "Ethena" in md
    assert "✅" in md
    assert "totalSupply" in md
    assert "1000000" in md
    # Both citations present
    assert "https://ethena.fi/docs" in md
    assert "https://etherscan.io/token/0xabc" in md
    assert "2026-04-08" in md


def test_overview_marks_claims_needing_manual_review():
    # A hard claim (or soft with low confidence) surfaces in markdown with a
    # [MANUAL REVIEW NEEDED] marker so the analyst cannot miss it at review.
    section = {
        "target_name": "Ethena",
        "claims": [
            {
                "name": "totalSupply",
                "kind": "hard",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=True,
                ),
                "findings": [
                    Finding(
                        claim="totalSupply",
                        value="1000000",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://ethena.fi/docs",
                        evidence_date="2026-04-08",
                    ),
                    Finding(
                        claim="totalSupply",
                        value="1000000",
                        source="etherscan",
                        source_kind="onchain",
                        evidence_url="https://etherscan.io/token/0xabc",
                        evidence_date="2026-04-08",
                    ),
                ],
            }
        ],
    }

    md = render_overview(section)

    assert "[MANUAL REVIEW NEEDED]" in md


def test_overview_renders_metric_table_with_display_label_and_sources():
    """Production Overview matches sky-protocol/README.md layout:
    a `| Metric | Value | Source |` table with one row per cross-checked claim.
    The metric column uses the claim's display_label, value comes from findings,
    sources are rendered as inline markdown links.
    """
    section = {
        "target_name": "frxUSD",
        "claims": [
            {
                "name": "frxusd_supply",
                "display_label": "frxUSD total supply",
                "kind": "hard",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=True,
                ),
                "findings": [
                    Finding(
                        claim="frxusd_supply",
                        value="1000000",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://frax.com/frxusd",
                        evidence_date="2026-04-08",
                    ),
                    Finding(
                        claim="frxusd_supply",
                        value="1000000",
                        source="etherscan",
                        source_kind="onchain",
                        evidence_url="https://etherscan.io/token/0xabc",
                        evidence_date="2026-04-08",
                    ),
                ],
            },
        ],
    }

    md = render_overview(section)

    # Table header present
    assert "| Metric | Value | Source |" in md
    assert "|---|---|---|" in md
    # Row uses display_label, not internal claim name
    assert "frxUSD total supply" in md
    # Value carried through
    assert "1000000" in md
    # Inline source link (at least one of the two cited)
    assert "etherscan.io" in md
    # Hard claim still flagged to manual review in the row
    assert "[MANUAL REVIEW NEEDED]" in md


def test_overview_renders_founder_questions_for_failed_claims():
    """Claims with ❌ verdict (e.g. on-chain fetch failed) drop out of the
    main metric table and surface under a `## Pytania do founders` section.
    This lets the rest of the report render even when a single verifier is
    broken."""
    section = {
        "target_name": "frxUSD",
        "claims": [
            {
                "name": "frxusd_supply",
                "display_label": "frxUSD total supply",
                "kind": "hard",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=True,
                ),
                "findings": [
                    Finding(
                        claim="frxusd_supply",
                        value="1000000",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://frax.com/frxusd",
                        evidence_date="2026-04-08",
                    ),
                    Finding(
                        claim="frxusd_supply",
                        value="1000000",
                        source="etherscan",
                        source_kind="onchain",
                        evidence_url="https://etherscan.io/token/0xabc",
                        evidence_date="2026-04-08",
                    ),
                ],
            },
            {
                "name": "top_holders",
                "display_label": "Top token holders",
                "kind": "hard",
                "verdict": Verdict(
                    tag="❌",
                    rationale="on-chain fetch failed: holder-list endpoint pro-only",
                    requires_manual_review=True,
                ),
                "findings": [
                    Finding(
                        claim="top_holders",
                        value="[a,b,c]",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://frax.com/holders",
                        evidence_date="2026-04-08",
                    ),
                ],
            },
        ],
    }

    md = render_overview(section)

    # Successful claim still in the metrics table
    assert "frxUSD total supply" in md
    # Failed claim gets a founder-questions section, not a metric row
    assert "## Pytania do founders" in md
    assert "Top token holders" in md
    # Rationale exposed so the analyst knows why it failed
    assert "holder-list endpoint pro-only" in md


def test_overview_omits_marker_for_auto_passed_soft_claims():
    section = {
        "target_name": "Ethena",
        "claims": [
            {
                "name": "mechanism_summary",
                "kind": "soft",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=False,
                ),
                "findings": [
                    Finding(
                        claim="mechanism_summary",
                        value="delta-neutral",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://ethena.fi/docs",
                        evidence_date="2026-04-08",
                    ),
                    Finding(
                        claim="mechanism_summary",
                        value="delta-neutral",
                        source="etherscan",
                        source_kind="onchain",
                        evidence_url="https://etherscan.io/token/0xabc",
                        evidence_date="2026-04-08",
                    ),
                ],
            }
        ],
    }

    md = render_overview(section)

    assert "[MANUAL REVIEW NEEDED]" not in md

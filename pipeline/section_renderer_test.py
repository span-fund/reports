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

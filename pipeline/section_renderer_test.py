"""Tests for section-renderer Overview.

Takes a section JSON (claims + verdicts + findings) and returns markdown with
verdict tags and citations from all sources.
"""

from pipeline.section_renderer import render_overview, render_section, render_team
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


def _f(claim: str, value: str, source: str, kind: str, url: str) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source=source,
        source_kind=kind,
        evidence_url=url,
        evidence_date="2026-04-09",
    )


def test_team_renders_officers_owners_and_generic_claims():
    """Team markdown groups findings by claim category. Officer/owner claims
    (claim names prefixed `officer:` / `owner:`) get their own subsections;
    everything else lands under a generic 'Team' bucket. Each row carries
    verdict tag + sources + manual-review marker for hard claims."""
    section = {
        "target_name": "Foo Sp. z o.o.",
        "claims": [
            {
                "name": "officer:Jan Kowalski",
                "display_label": "Jan Kowalski",
                "kind": "hard",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=True,
                ),
                "findings": [
                    _f(
                        "officer:Jan Kowalski",
                        "Prezes Zarządu",
                        "parallel",
                        "parallel",
                        "https://foo.pl/team",
                    ),
                    _f(
                        "officer:Jan Kowalski",
                        "Prezes Zarządu",
                        "krs",
                        "legal",
                        "https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
                    ),
                ],
            },
            {
                "name": "owner:Anna Nowak",
                "display_label": "Anna Nowak",
                "kind": "hard",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=True,
                ),
                "findings": [
                    _f(
                        "owner:Anna Nowak",
                        "50 udziałów",
                        "parallel",
                        "parallel",
                        "https://foo.pl/team",
                    ),
                    _f(
                        "owner:Anna Nowak",
                        "50 udziałów",
                        "krs",
                        "legal",
                        "https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
                    ),
                ],
            },
            {
                "name": "team_size",
                "display_label": "Team size",
                "kind": "soft",
                "verdict": Verdict(
                    tag="✅",
                    rationale="2 sources agree",
                    requires_manual_review=False,
                ),
                "findings": [
                    _f("team_size", "12", "parallel", "parallel", "https://foo.pl/team"),
                    _f("team_size", "12", "linkedin", "browser", "https://linkedin.com/foo"),
                ],
            },
        ],
    }

    md = render_team(section)

    assert "# Team — Foo Sp. z o.o." in md
    # Subsection headings
    assert "## Zarząd" in md
    assert "## Wspólnicy" in md
    # Officers + owners rendered with names + values
    assert "Jan Kowalski" in md
    assert "Prezes Zarządu" in md
    assert "Anna Nowak" in md
    assert "50 udziałów" in md
    # Generic team claim still rendered
    assert "Team size" in md
    assert "12" in md
    # Hard claims flagged
    assert md.count("[MANUAL REVIEW NEEDED]") == 2
    # Soft auto-pass not flagged
    # (only the two hard claims should carry the marker)
    # KRS citation reaches the markdown
    assert "wyszukiwarka-krs.ms.gov.pl" in md


def test_team_renders_warning_claims_and_open_questions():
    """A claim with ⚠️ (e.g. ownership not confirmed by registry) lands in
    its normal subsection AND surfaces under 'Open questions' so the analyst
    can't miss the missing registry confirmation."""
    section = {
        "target_name": "Bar S.A.",
        "claims": [
            {
                "name": "owner:Mystery Person",
                "display_label": "Mystery Person",
                "kind": "hard",
                "verdict": Verdict(
                    tag="⚠️",
                    rationale="no registry confirmation for owner:Mystery Person",
                    requires_manual_review=True,
                ),
                "findings": [
                    _f(
                        "owner:Mystery Person",
                        "30%",
                        "parallel",
                        "parallel",
                        "https://bar.com/about",
                    ),
                ],
            },
        ],
    }

    md = render_team(section)

    assert "## Open questions" in md
    assert "Mystery Person" in md
    assert "no registry confirmation" in md
    # Also surfaced under "Pytania do founders" — same data, different framing
    assert "## Pytania do founders" in md


def test_team_renders_failed_claims_only_in_pytania_section():
    section = {
        "target_name": "Baz Ltd",
        "claims": [
            {
                "name": "ownership_structure",
                "display_label": "Ownership structure",
                "kind": "hard",
                "verdict": Verdict(
                    tag="❌",
                    rationale="legal adapter unreachable",
                    requires_manual_review=True,
                ),
                "findings": [],
            },
        ],
    }

    md = render_team(section)

    assert "## Pytania do founders" in md
    assert "Ownership structure" in md
    assert "legal adapter unreachable" in md


# ---------------------------------------------------------------------------
# Phase 5: generic section renderer
# ---------------------------------------------------------------------------


def test_render_section_metric_table():
    """Default render style: metric table like Overview — used for
    Collateral, Revenue, Key Contracts."""
    section = {
        "section_name": "Collateral",
        "target_name": "sky-protocol",
        "render_style": "metric_table",
        "claims": [
            {
                "name": "collateral_composition",
                "display_label": "Collateral breakdown",
                "verdict": Verdict(
                    tag="✅", rationale="2 sources agree", requires_manual_review=True
                ),
                "findings": [
                    Finding(
                        claim="collateral_composition",
                        value="60% USDC, 30% ETH",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://example.com/c",
                        evidence_date="2026-04-10",
                    ),
                ],
            },
        ],
    }

    md = render_section(section)

    assert "# Collateral — sky-protocol" in md
    assert "| Metric | Value | Source |" in md
    assert "Collateral breakdown" in md
    assert "60% USDC, 30% ETH" in md


def test_render_section_risk_table():
    """Risks section renders with severity column."""
    section = {
        "section_name": "Risks",
        "target_name": "sky-protocol",
        "render_style": "risk_table",
        "claims": [
            {
                "name": "governance_centralization",
                "display_label": "Governance centralization",
                "severity": "High",
                "verdict": Verdict(tag="✅", rationale="confirmed", requires_manual_review=True),
                "findings": [
                    Finding(
                        claim="governance_centralization",
                        value="S&P B-, ECB paper",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://example.com",
                        evidence_date="2026-04-10",
                    ),
                ],
            },
            {
                "name": "yield_sustainability",
                "display_label": "Yield sustainability",
                "severity": "Medium",
                "verdict": Verdict(tag="⚠️", rationale="uncertain", requires_manual_review=True),
                "findings": [
                    Finding(
                        claim="yield_sustainability",
                        value="Proven unsustainable at higher levels",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://example.com/y",
                        evidence_date="2026-04-10",
                    ),
                ],
            },
        ],
    }

    md = render_section(section)

    assert "# Risks — sky-protocol" in md
    assert "| Risk | Severity | Evidence |" in md
    assert "Governance centralization" in md
    assert "High" in md
    assert "Medium" in md


def test_render_section_incident_table():
    """Historical Incidents renders with date and impact columns."""
    section = {
        "section_name": "Historical Incidents",
        "target_name": "sky-protocol",
        "render_style": "incident_table",
        "claims": [
            {
                "name": "black_thursday",
                "display_label": "Black Thursday",
                "verdict": Verdict(tag="✅", rationale="confirmed", requires_manual_review=True),
                "findings": [
                    Finding(
                        claim="black_thursday",
                        value="ETH -43%, $8.32M exploited",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://example.com/bt",
                        evidence_date="2020-03-12",
                    ),
                ],
            },
        ],
    }

    md = render_section(section)

    assert "# Historical Incidents — sky-protocol" in md
    assert "| Incident | Date | Impact | Source |" in md
    assert "Black Thursday" in md
    assert "ETH -43%" in md


def test_render_section_narrative():
    """Mechanism and Regulatory use narrative style — prose, not table."""
    section = {
        "section_name": "Mechanism",
        "target_name": "ethena",
        "render_style": "narrative",
        "claims": [
            {
                "name": "mechanism_description",
                "display_label": "How the protocol works",
                "verdict": Verdict(tag="✅", rationale="confirmed", requires_manual_review=False),
                "findings": [
                    Finding(
                        claim="mechanism_description",
                        value="Delta-neutral position: short ETH perp + long staked ETH",
                        source="parallel",
                        source_kind="parallel",
                        evidence_url="https://ethena.fi/docs",
                        evidence_date="2026-04-10",
                    ),
                ],
            },
        ],
    }

    md = render_section(section)

    assert "# Mechanism — ethena" in md
    # Narrative style: no table, claim rendered as bullet or paragraph
    assert "How the protocol works" in md
    assert "Delta-neutral position" in md
    assert "| Metric |" not in md


def test_render_section_failed_claims_go_to_pytania():
    """Failed claims in any generic section land in Pytania do founders."""
    section = {
        "section_name": "Revenue",
        "target_name": "test",
        "render_style": "metric_table",
        "claims": [
            {
                "name": "annual_revenue",
                "display_label": "Annual revenue",
                "verdict": Verdict(
                    tag="❌", rationale="no data found", requires_manual_review=True
                ),
                "findings": [],
            },
        ],
    }

    md = render_section(section)

    assert "## Pytania do founders" in md
    assert "Annual revenue" in md
    assert "no data found" in md

"""Tests for the generic section claim manifest loader.

New sections (Mechanism, Collateral, Revenue, Governance, Regulatory,
Historical Incidents, Risks, Key Contracts) all share the same SectionClaim
dataclass. Each claim has a name, kind, display_label, parallel_field, and
an optional section-specific render_style hint. The manifest is plain JSON —
same convention as OverviewClaim and TeamClaim.
"""

import json
from pathlib import Path

from pipeline.section_claims import load_section_claims


def test_load_minimal_section(tmp_path: Path):
    manifest = {
        "section": "Mechanism",
        "claims": [
            {
                "name": "mechanism_description",
                "kind": "soft",
                "display_label": "How the protocol works",
                "parallel_field": "mechanism_description",
            },
        ],
    }
    path = tmp_path / "mechanism_claims.json"
    path.write_text(json.dumps(manifest))

    section_name, claims = load_section_claims(path)

    assert section_name == "Mechanism"
    assert len(claims) == 1
    c = claims[0]
    assert c.name == "mechanism_description"
    assert c.kind == "soft"
    assert c.display_label == "How the protocol works"
    assert c.parallel_field == "mechanism_description"


def test_load_multiple_claims_preserves_order(tmp_path: Path):
    manifest = {
        "section": "Risks",
        "claims": [
            {
                "name": "governance_centralization",
                "kind": "hard",
                "display_label": "Governance centralization",
                "parallel_field": "governance_centralization",
            },
            {
                "name": "usdc_dependency",
                "kind": "hard",
                "display_label": "USDC dependency",
                "parallel_field": "usdc_dependency",
            },
            {
                "name": "yield_sustainability",
                "kind": "soft",
                "display_label": "Yield sustainability",
                "parallel_field": "yield_sustainability",
            },
        ],
    }
    path = tmp_path / "risks_claims.json"
    path.write_text(json.dumps(manifest))

    section_name, claims = load_section_claims(path)

    assert section_name == "Risks"
    assert [c.name for c in claims] == [
        "governance_centralization",
        "usdc_dependency",
        "yield_sustainability",
    ]
    assert claims[0].kind == "hard"
    assert claims[2].kind == "soft"


def test_claim_with_severity_field(tmp_path: Path):
    """Risk claims can carry a severity hint used by the renderer."""
    manifest = {
        "section": "Risks",
        "claims": [
            {
                "name": "smart_contract_risk",
                "kind": "hard",
                "display_label": "Smart contract risk",
                "parallel_field": "smart_contract_risk",
                "severity": "High",
            },
        ],
    }
    path = tmp_path / "risks_claims.json"
    path.write_text(json.dumps(manifest))

    _, claims = load_section_claims(path)

    assert claims[0].severity == "High"


def test_severity_defaults_to_none(tmp_path: Path):
    manifest = {
        "section": "Revenue",
        "claims": [
            {
                "name": "annual_revenue",
                "kind": "hard",
                "display_label": "Annualized revenue",
                "parallel_field": "annual_revenue",
            },
        ],
    }
    path = tmp_path / "revenue_claims.json"
    path.write_text(json.dumps(manifest))

    _, claims = load_section_claims(path)

    assert claims[0].severity is None

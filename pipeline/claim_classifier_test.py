"""Claim classifier: declarative hard/soft taxonomy per report section.

Hard claims (numbers, ownership, regulatory, team credentials) always need
manual review regardless of cross-check confidence. Soft claims (mechanism
narrative, ecosystem context) can be auto-tagged when STRICT policy passes
and Parallel confidence is above threshold.
"""

from pipeline.claim_classifier import classify


def test_overview_total_supply_is_hard():
    assert classify(section="Overview", claim_name="totalSupply") == "hard"


def test_unknown_claim_defaults_to_soft():
    assert classify(section="Overview", claim_name="mechanism_narrative") == "soft"


def test_unknown_section_defaults_to_soft():
    assert classify(section="Mechanism", claim_name="totalSupply") == "soft"


def test_team_ownership_is_hard():
    # Ownership decides who controls the company — always hard, regardless
    # of how confident Parallel is.
    assert classify(section="Team", claim_name="ownership_structure") == "hard"


def test_team_credentials_are_hard():
    # Founder/team credentials are claims that drive invest decisions and
    # have legal/regulatory consequences if wrong.
    assert classify(section="Team", claim_name="team_credentials") == "hard"


def test_team_cap_table_changes_are_hard():
    assert classify(section="Team", claim_name="cap_table_changes") == "hard"


def test_team_bio_is_soft():
    # Narrative bio context — lower stakes, can auto-pass with confidence.
    assert classify(section="Team", claim_name="founder_bio") == "soft"


# --- Phase 5: new section rules ---


def test_collateral_composition_is_hard():
    assert classify(section="Collateral", claim_name="collateral_composition") == "hard"


def test_collateral_ratio_is_hard():
    assert classify(section="Collateral", claim_name="collateralization_ratio") == "hard"


def test_revenue_annual_is_hard():
    assert classify(section="Revenue", claim_name="annual_revenue") == "hard"


def test_revenue_narrative_is_soft():
    assert classify(section="Revenue", claim_name="revenue_commentary") == "soft"


def test_governance_centralization_is_hard():
    assert classify(section="Governance", claim_name="governance_centralization") == "hard"


def test_governance_voter_turnout_is_hard():
    assert classify(section="Governance", claim_name="voter_turnout") == "hard"


def test_regulatory_compliance_status_is_hard():
    assert classify(section="Regulatory", claim_name="compliance_status") == "hard"


def test_regulatory_jurisdiction_is_hard():
    assert classify(section="Regulatory", claim_name="jurisdiction_status") == "hard"


def test_historical_incidents_incident_is_hard():
    assert classify(section="Historical Incidents", claim_name="incident") == "hard"


def test_risks_severity_is_hard():
    assert classify(section="Risks", claim_name="risk_severity") == "hard"


def test_key_contracts_address_is_hard():
    assert classify(section="Key Contracts", claim_name="contract_address") == "hard"


def test_mechanism_description_is_soft():
    assert classify(section="Mechanism", claim_name="mechanism_description") == "soft"


def test_mechanism_contract_risk_is_hard():
    assert classify(section="Mechanism", claim_name="contract_risk") == "hard"

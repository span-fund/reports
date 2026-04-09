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

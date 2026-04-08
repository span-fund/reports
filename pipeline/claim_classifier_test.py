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

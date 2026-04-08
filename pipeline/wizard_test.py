"""Tests for wizard input validation.

Wizard asks 4 questions in Claude Code via AskUserQuestion; the validation
logic is extracted into pure functions so it is testable without the UI layer.
"""

import pytest

from pipeline.wizard import WizardError, validate_wizard_input


def test_valid_wizard_input_yields_config():
    config = validate_wizard_input(
        target_type="protocol",
        domain="ethena.fi",
        chain="ethereum",
        jurisdiction="us",
        tier="lite",
        soft_cap_usd=2.0,
    )

    assert config.target_type == "protocol"
    assert config.domain == "ethena.fi"
    assert config.chain == "ethereum"
    assert config.jurisdiction == "us"
    assert config.tier == "lite"
    assert config.soft_cap_usd == 2.0
    assert config.slug == "ethena-fi"


def test_invalid_target_type_rejected():
    with pytest.raises(WizardError, match="target_type"):
        validate_wizard_input(
            target_type="nft-thing",
            domain="ethena.fi",
            chain="ethereum",
            jurisdiction="us",
            tier="lite",
            soft_cap_usd=2.0,
        )


def test_invalid_tier_rejected():
    with pytest.raises(WizardError, match="tier"):
        validate_wizard_input(
            target_type="protocol",
            domain="ethena.fi",
            chain="ethereum",
            jurisdiction="us",
            tier="diamond",
            soft_cap_usd=2.0,
        )


def test_domain_without_dot_rejected():
    with pytest.raises(WizardError, match="domain"):
        validate_wizard_input(
            target_type="protocol",
            domain="ethena",
            chain="ethereum",
            jurisdiction="us",
            tier="lite",
            soft_cap_usd=2.0,
        )


def test_nonpositive_soft_cap_rejected():
    with pytest.raises(WizardError, match="soft_cap"):
        validate_wizard_input(
            target_type="protocol",
            domain="ethena.fi",
            chain="ethereum",
            jurisdiction="us",
            tier="lite",
            soft_cap_usd=0,
        )

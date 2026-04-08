"""Wizard input validation.

Pure validation logic — the Claude Code AskUserQuestion UI lives in the skill
orchestration layer. Extracted so we can test the rules without the UI.
"""

from dataclasses import dataclass

VALID_TARGET_TYPES = {"protocol", "company", "combined"}
VALID_TIERS = {"lite", "base", "pro", "ultra"}


class WizardError(ValueError):
    """Raised when wizard input fails validation."""


@dataclass(frozen=True)
class TargetConfig:
    target_type: str
    domain: str
    chain: str
    jurisdiction: str
    tier: str
    soft_cap_usd: float
    slug: str
    # Minimum Parallel confidence required to auto-pass a soft claim with a
    # clean STRICT ✅. Hard claims always go to manual review regardless.
    confidence_threshold: float = 0.7


def _slugify(domain: str) -> str:
    return domain.replace(".", "-").lower()


def validate_wizard_input(
    *,
    target_type: str,
    domain: str,
    chain: str,
    jurisdiction: str,
    tier: str,
    soft_cap_usd: float,
) -> TargetConfig:
    if target_type not in VALID_TARGET_TYPES:
        raise WizardError(
            f"target_type must be one of {sorted(VALID_TARGET_TYPES)}, got {target_type!r}"
        )
    if "." not in domain:
        raise WizardError(f"domain must look like a real domain (got {domain!r})")
    if tier not in VALID_TIERS:
        raise WizardError(f"tier must be one of {sorted(VALID_TIERS)}, got {tier!r}")
    if soft_cap_usd <= 0:
        raise WizardError(f"soft_cap_usd must be > 0, got {soft_cap_usd}")
    return TargetConfig(
        target_type=target_type,
        domain=domain,
        chain=chain,
        jurisdiction=jurisdiction,
        tier=tier,
        soft_cap_usd=soft_cap_usd,
        slug=_slugify(domain),
    )

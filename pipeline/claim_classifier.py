"""Claim classifier: declarative hard/soft taxonomy per report section.

Hard claims (numbers that drive invest decisions, ownership, regulatory
status, team credentials, smart-contract risks) always go through manual
review — Parallel confidence is a signal, not a shortcut. Soft claims
(mechanism narrative, ecosystem context) can be auto-tagged when STRICT
cross-check passes and confidence clears the threshold.

Rules are data, not code. Adding a new section means extending the dict.
"""

# Per-section claim kind rules. Default for anything not listed is "soft".
_RULES: dict[str, dict[str, str]] = {
    "Overview": {
        "totalSupply": "hard",
    },
}


def classify(*, section: str, claim_name: str) -> str:
    """Return "hard" or "soft" for a given section/claim pair."""
    return _RULES.get(section, {}).get(claim_name, "soft")

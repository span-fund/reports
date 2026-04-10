"""Generic section claim manifest loader.

Covers all sections beyond Overview and Team: Mechanism, Collateral, Revenue,
Governance, Regulatory, Historical Incidents, Risks, Key Contracts. Each
manifest is plain JSON with a section name and a claims array — same
convention as overview_claims and team_claims.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SectionClaim:
    name: str
    kind: str  # "hard" | "soft"
    display_label: str
    parallel_field: str
    severity: str | None = None


def load_section_claims(path: Path) -> tuple[str, list[SectionClaim]]:
    """Load a section manifest, returning (section_name, claims)."""
    data = json.loads(path.read_text())
    section_name = data["section"]
    claims = [
        SectionClaim(
            name=raw["name"],
            kind=raw["kind"],
            display_label=raw["display_label"],
            parallel_field=raw["parallel_field"],
            severity=raw.get("severity"),
        )
        for raw in data["claims"]
    ]
    return section_name, claims

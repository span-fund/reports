"""Team claim manifest loader.

Sibling of overview_claims for the Team section. The manifest is plain JSON
co-located with a target's config — adding a new claim means editing JSON,
not Python. Each entry can flag itself as `legal_expected`, which the
verdict engine reads to require a registry-confirmation source before it
will award a clean ✅.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TeamClaim:
    name: str
    kind: str  # "hard" | "soft"
    display_label: str
    parallel_field: str
    legal_expected: bool = False


def load_team_claims(path: Path) -> list[TeamClaim]:
    data = json.loads(path.read_text())
    out: list[TeamClaim] = []
    for raw in data["claims"]:
        out.append(
            TeamClaim(
                name=raw["name"],
                kind=raw["kind"],
                display_label=raw["display_label"],
                parallel_field=raw["parallel_field"],
                legal_expected=bool(raw.get("legal_expected", False)),
            )
        )
    return out

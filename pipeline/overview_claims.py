"""Overview claim manifest loader.

The manifest is plain JSON co-located with a target's config.json. Each entry
binds a Parallel schema field to an optional on-chain fetcher spec. Manifest
is data, not code — adding a new claim or target means editing JSON. The
orchestrator iterates this list to build Parallel requests and on-chain
cross-checks uniformly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OnchainSpec:
    fetcher: str  # "total_supply" | "contract_read" | "token_balance"
    contract: str
    decimals: int
    # e.g. "ethereum", "base", "arbitrum" — used both for on-chain RPC routing
    # and Parallel prompt hints (issue #13).
    chain: str
    selector: str | None = None
    holder: str | None = None


@dataclass(frozen=True)
class OverviewClaim:
    name: str
    kind: str  # "hard" | "soft"
    display_label: str
    parallel_field: str
    onchain: OnchainSpec | None


def load_overview_claims(path: Path) -> list[OverviewClaim]:
    data = json.loads(path.read_text())
    out: list[OverviewClaim] = []
    for raw in data["claims"]:
        onchain_raw = raw.get("onchain")
        onchain = (
            OnchainSpec(
                fetcher=onchain_raw["fetcher"],
                contract=onchain_raw["contract"],
                decimals=onchain_raw["decimals"],
                chain=onchain_raw["chain"],
                selector=onchain_raw.get("selector"),
                holder=onchain_raw.get("holder"),
            )
            if onchain_raw is not None
            else None
        )
        out.append(
            OverviewClaim(
                name=raw["name"],
                kind=raw["kind"],
                display_label=raw["display_label"],
                parallel_field=raw["parallel_field"],
                onchain=onchain,
            )
        )
    return out

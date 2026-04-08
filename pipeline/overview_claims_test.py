"""Tests for the Overview claim manifest loader.

The manifest is plain JSON — one per target, co-located with config.json.
It lists the Overview claims for that target, each binding a Parallel schema
field to an optional on-chain fetcher spec. Manifest is data, not code: adding
a new claim means editing JSON, not Python.
"""

import json
from pathlib import Path

from pipeline.overview_claims import load_overview_claims


def test_load_overview_claims_parses_all_fetcher_kinds(tmp_path: Path):
    manifest = {
        "claims": [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "frxUSD total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xabc",
                    "decimals": 18,
                },
            },
            {
                "name": "sfrxusd_total_assets",
                "kind": "hard",
                "display_label": "sfrxUSD totalAssets",
                "parallel_field": "sfrxusd_total_assets",
                "onchain": {
                    "fetcher": "contract_read",
                    "contract": "0xdef",
                    "selector": "0x01e1d114",
                    "decimals": 18,
                },
            },
            {
                "name": "mechanism_summary",
                "kind": "soft",
                "display_label": "Mechanism one-liner",
                "parallel_field": "mechanism_summary",
                "onchain": None,
            },
        ]
    }
    path = tmp_path / "overview_claims.json"
    path.write_text(json.dumps(manifest))

    claims = load_overview_claims(path)

    assert [c.name for c in claims] == [
        "frxusd_supply",
        "sfrxusd_total_assets",
        "mechanism_summary",
    ]

    supply = claims[0]
    assert supply.kind == "hard"
    assert supply.parallel_field == "frxusd_supply"
    assert supply.onchain is not None
    assert supply.onchain.fetcher == "total_supply"
    assert supply.onchain.contract == "0xabc"
    assert supply.onchain.decimals == 18

    total_assets = claims[1]
    assert total_assets.onchain is not None
    assert total_assets.onchain.fetcher == "contract_read"
    assert total_assets.onchain.selector == "0x01e1d114"

    # Soft claim with no on-chain verifier (Parallel-only)
    mechanism = claims[2]
    assert mechanism.kind == "soft"
    assert mechanism.onchain is None

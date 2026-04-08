"""Etherscan V2 wrapper.

Thin adapter that calls Etherscan V2 (chainid-aware) and returns Findings
shaped identically to Parallel/legal/browser sources so verdict-engine can
consume them uniformly. HTTP is injected so tests mock at the boundary.
"""

from collections.abc import Callable
from datetime import date
from typing import Protocol

from pipeline.verdict_engine import Finding

V2_ENDPOINT = "https://api.etherscan.io/v2/api"


class HttpGet(Protocol):
    def __call__(self, url: str, params: dict) -> dict: ...


def fetch_total_supply(
    chain_id: int,
    token_address: str,
    decimals: int,
    http_get: Callable[[str, dict], dict],
    api_key: str,
) -> Finding:
    params = {
        "chainid": chain_id,
        "module": "stats",
        "action": "tokensupply",
        "contractaddress": token_address,
        "apikey": api_key,
    }
    response = http_get(V2_ENDPOINT, params)
    raw = int(response["result"])
    scaled = raw // (10**decimals)
    return Finding(
        claim="totalSupply",
        value=str(scaled),
        source="etherscan",
        source_kind="onchain",
        evidence_url=f"https://etherscan.io/token/{token_address}",
        evidence_date=date.today().isoformat(),
    )

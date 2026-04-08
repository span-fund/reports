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


def fetch_token_balance(
    *,
    chain_id: int,
    holder_address: str,
    token_address: str,
    decimals: int,
    claim_name: str,
    http_get: Callable[[str, dict], dict],
    api_key: str,
) -> Finding:
    """Read a specific holder's balance of an ERC-20 via V2 account/tokenbalance.

    Used e.g. for PSM collateral checks (`holder_address` = PSM pocket,
    `token_address` = USDC). Scales by `decimals` and tags the Finding with
    the caller's `claim_name`.
    """
    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "tokenbalance",
        "contractaddress": token_address,
        "address": holder_address,
        "tag": "latest",
        "apikey": api_key,
    }
    response = http_get(V2_ENDPOINT, params)
    raw = int(response["result"])
    scaled = raw // (10**decimals) if decimals else raw
    return Finding(
        claim=claim_name,
        value=str(scaled),
        source="etherscan",
        source_kind="onchain",
        evidence_url=f"https://etherscan.io/address/{holder_address}",
        evidence_date=date.today().isoformat(),
    )


def fetch_contract_read(
    *,
    chain_id: int,
    contract: str,
    selector: str,
    decimals: int,
    claim_name: str,
    http_get: Callable[[str, dict], dict],
    api_key: str,
) -> Finding:
    """Generic ERC getter via Etherscan V2 proxy/eth_call.

    Reads an arbitrary 4-byte selector (e.g. `totalAssets()`, `owner()`, `chi()`)
    against `contract` on `chain_id`, decodes the hex uint256 result, and scales
    by `decimals`. `claim_name` is threaded through so multiple selectors can
    share this one entry point and land as distinct claims in the verdict.
    """
    params = {
        "chainid": chain_id,
        "module": "proxy",
        "action": "eth_call",
        "to": contract,
        "data": selector,
        "tag": "latest",
        "apikey": api_key,
    }
    response = http_get(V2_ENDPOINT, params)
    raw = int(response["result"], 16)
    scaled = raw // (10**decimals) if decimals else raw
    return Finding(
        claim=claim_name,
        value=str(scaled),
        source="etherscan",
        source_kind="onchain",
        evidence_url=f"https://etherscan.io/address/{contract}",
        evidence_date=date.today().isoformat(),
    )

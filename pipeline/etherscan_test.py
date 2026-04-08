"""Tests for Etherscan V2 wrapper.

HTTP is mocked at the boundary — we pass in a fake http_get callable. The
wrapper parses the Etherscan V2 response shape into a Finding with proper
source_kind='onchain' and evidence URL pointing at the block explorer.
"""

from pipeline.etherscan import (
    fetch_contract_read,
    fetch_token_balance,
    fetch_total_supply,
)


def test_fetch_total_supply_returns_finding_from_etherscan_response():
    calls: list[dict] = []

    def fake_http_get(url: str, params: dict) -> dict:
        calls.append({"url": url, "params": params})
        return {"status": "1", "message": "OK", "result": "1000000000000000000000000"}

    finding = fetch_total_supply(
        chain_id=1,
        token_address="0xabc",
        decimals=18,
        http_get=fake_http_get,
        api_key="test-key",
    )

    # Wrapper passed the right V2 query params
    assert calls[0]["params"]["chainid"] == 1
    assert calls[0]["params"]["module"] == "stats"
    assert calls[0]["params"]["action"] == "tokensupply"
    assert calls[0]["params"]["contractaddress"] == "0xabc"
    assert calls[0]["params"]["apikey"] == "test-key"

    # Finding shape + scaled value
    assert finding.claim == "totalSupply"
    assert finding.value == "1000000"  # 1e24 raw / 1e18 decimals
    assert finding.source_kind == "onchain"
    assert finding.source == "etherscan"
    assert "etherscan.io" in finding.evidence_url
    assert "0xabc" in finding.evidence_url


def test_fetch_contract_read_decodes_eth_call_uint256():
    """Generic eth_call wrapper: reads an arbitrary getter (e.g. ERC-4626
    totalAssets()), decodes the hex uint256 result, scales by decimals, and
    returns a Finding tagged with the caller-supplied claim name."""
    calls: list[dict] = []

    def fake_http_get(url: str, params: dict) -> dict:
        calls.append({"url": url, "params": params})
        # 1_000_000 * 10**18 = 10**24 = 0xd3c21bcecceda1000000
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000",
        }

    finding = fetch_contract_read(
        chain_id=1,
        contract="0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD",
        selector="0x01e1d114",  # totalAssets()
        decimals=18,
        claim_name="totalAssets",
        http_get=fake_http_get,
        api_key="test-key",
    )

    # V2 proxy/eth_call params
    params = calls[0]["params"]
    assert params["chainid"] == 1
    assert params["module"] == "proxy"
    assert params["action"] == "eth_call"
    assert params["to"] == "0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD"
    assert params["data"] == "0x01e1d114"
    assert params["tag"] == "latest"
    assert params["apikey"] == "test-key"

    # Finding shape + scaled value
    assert finding.claim == "totalAssets"
    assert finding.value == "1000000"
    assert finding.source == "etherscan"
    assert finding.source_kind == "onchain"
    assert "0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD" in finding.evidence_url


def test_fetch_token_balance_returns_finding_for_holder():
    """Read a specific holder's token balance (e.g. PSM USDC balance) via
    V2 account/tokenbalance. Evidence URL points at the holder address."""
    calls: list[dict] = []

    def fake_http_get(url: str, params: dict) -> dict:
        calls.append({"url": url, "params": params})
        # 4_303_767_363 USDC raw (6 decimals) = 4303767363 * 10**6
        return {"status": "1", "message": "OK", "result": "4303767363000000"}

    finding = fetch_token_balance(
        chain_id=1,
        holder_address="0x37305B1cD40574E4C5Ce33f8e8306Be057fD7341",
        token_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        decimals=6,
        claim_name="psm_usdc_balance",
        http_get=fake_http_get,
        api_key="test-key",
    )

    params = calls[0]["params"]
    assert params["chainid"] == 1
    assert params["module"] == "account"
    assert params["action"] == "tokenbalance"
    assert params["address"] == "0x37305B1cD40574E4C5Ce33f8e8306Be057fD7341"
    assert params["contractaddress"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert params["tag"] == "latest"
    assert params["apikey"] == "test-key"

    assert finding.claim == "psm_usdc_balance"
    assert finding.value == "4303767363"
    assert finding.source == "etherscan"
    assert finding.source_kind == "onchain"
    assert "0x37305B1cD40574E4C5Ce33f8e8306Be057fD7341" in finding.evidence_url

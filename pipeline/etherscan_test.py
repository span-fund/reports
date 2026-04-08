"""Tests for Etherscan V2 wrapper.

HTTP is mocked at the boundary — we pass in a fake http_get callable. The
wrapper parses the Etherscan V2 response shape into a Finding with proper
source_kind='onchain' and evidence URL pointing at the block explorer.
"""

from pipeline.etherscan import fetch_total_supply


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

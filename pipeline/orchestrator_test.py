"""End-to-end tests for the skill orchestrator: `run_dd_new`.

Phase 3: Overview grows to a multi-claim manifest driven by
`overview_claims.json`. The orchestrator fans out one wide Parallel call plus
N on-chain calls (one per claim with an onchain spec), cross-checks each
claim through the verdict engine, and renders the section. Failures on
individual on-chain fetchers land in the founder-questions section without
crashing the rest of the report.

Mocks only at real system boundaries (Parallel SDK, HTTP for Etherscan). Real
filesystem via tmp_path, real verdict-engine, real renderer, real cache, real
audit log.
"""

import json
from pathlib import Path

from pipeline.orchestrator import run_dd_new
from pipeline.parallel_test import FakeParallelClient
from pipeline.wizard import TargetConfig


def _write_manifest(path: Path, claims: list[dict]) -> Path:
    path.write_text(json.dumps({"claims": claims}))
    return path


def _frx_config() -> TargetConfig:
    return TargetConfig(
        target_type="protocol",
        domain="frax.com",
        chain="ethereum",
        jurisdiction="us",
        tier="lite",
        soft_cap_usd=2.0,
        slug="frax-com",
        confidence_threshold=0.7,
    )


def _env() -> dict[str, str]:
    return {"PARALLEL_API_KEY": "p-xxx", "ETHERSCAN_API_KEY": "e-yyy"}


# 1M * 10**18 raw — shared fixture for both Etherscan shapes:
#   tokensupply returns the decimal string, eth_call returns the hex literal.
_ONEM_E18_DEC = "1000000000000000000000000"
_ONEM_E18_HEX = "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000"


def test_multi_claim_overview_crosschecks_each_claim(tmp_path):
    """Manifest with two hard claims — one backed by an on-chain total_supply
    fetcher, one by a contract_read. Parallel returns a wide response covering
    both. Verdict engine cross-checks each independently; both should land
    green and both should carry the hard-claim manual-review flag.
    """
    manifest = _write_manifest(
        tmp_path / "overview_claims.json",
        [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "frxUSD total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xFRX",
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
                    "contract": "0xSFRX",
                    "selector": "0x01e1d114",
                    "decimals": 18,
                },
            },
        ],
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 1.25,
            "output": {
                "frxusd_supply": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/stats",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.92,
                },
                "sfrxusd_total_assets": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/vault",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
            },
        }
    )

    def fake_http_get(url, params):
        if params.get("action") == "tokensupply":
            return {"status": "1", "result": _ONEM_E18_DEC}
        if params.get("action") == "eth_call":
            return {"jsonrpc": "2.0", "id": 1, "result": _ONEM_E18_HEX}
        raise AssertionError(f"unexpected http_get params {params}")

    result = run_dd_new(
        config=_frx_config(),
        overview_claims_path=manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=parallel_client,
        http_get=fake_http_get,
    )

    target_dir = tmp_path / "frax-com"
    last_run = json.loads((target_dir / "last_run.json").read_text())

    # Both claims got cross-checked and greenlit.
    assert last_run["verdicts"]["frxusd_supply"]["tag"] == "✅"
    assert last_run["verdicts"]["sfrxusd_total_assets"]["tag"] == "✅"
    # Both are hard → manual review required regardless.
    assert last_run["claims"]["frxusd_supply"]["kind"] == "hard"
    assert last_run["claims"]["frxusd_supply"]["requires_manual_review"] is True
    assert last_run["claims"]["sfrxusd_total_assets"]["requires_manual_review"] is True

    # README uses the table format with display labels.
    readme = (target_dir / "README.md").read_text()
    assert "| Metric | Value | Source |" in readme
    assert "frxUSD total supply" in readme
    assert "sfrxUSD totalAssets" in readme
    assert readme.count("[MANUAL REVIEW NEEDED]") == 2

    # Exactly one Parallel call for the whole section.
    assert len(parallel_client.calls) == 1
    # One audit line.
    audit_lines = (target_dir / "parallel-runs.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1

    # Skill return surface
    assert set(result.manual_review_claims) == {"frxusd_supply", "sfrxusd_total_assets"}
    assert result.verdict_tag in {"✅", "⚠️"}


def test_onchain_failure_lands_in_founder_questions_without_crash(tmp_path):
    """When the on-chain fetcher for one claim raises, the orchestrator keeps
    rendering the rest of the section: the failing claim collects only the
    Parallel finding, verdict engine flags it ❌ (insufficient sources) and
    it surfaces under `## Pytania do founders`. The healthy claim still lands
    in the metric table.
    """
    manifest = _write_manifest(
        tmp_path / "overview_claims.json",
        [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "frxUSD total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xFRX",
                    "decimals": 18,
                },
            },
            {
                "name": "top_holders",
                "kind": "hard",
                "display_label": "Top token holders",
                "parallel_field": "top_holders",
                "onchain": {
                    "fetcher": "contract_read",
                    "contract": "0xBROKEN",
                    "selector": "0xdeadbeef",
                    "decimals": 0,
                },
            },
        ],
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-xyz",
            "cost_usd": 1.0,
            "output": {
                "frxusd_supply": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/stats",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
                "top_holders": {
                    "value": "0xA,0xB,0xC",
                    "evidence_url": "https://frax.com/holders",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.8,
                },
            },
        }
    )

    def fake_http_get(url, params):
        if params.get("action") == "tokensupply":
            return {"status": "1", "result": _ONEM_E18_DEC}
        if params.get("action") == "eth_call":
            # Simulate a selector that isn't supported by this custom contract.
            raise RuntimeError("eth_call reverted: unknown selector")
        raise AssertionError(f"unexpected http_get params {params}")

    result = run_dd_new(
        config=_frx_config(),
        overview_claims_path=manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=parallel_client,
        http_get=fake_http_get,
    )

    target_dir = tmp_path / "frax-com"
    last_run = json.loads((target_dir / "last_run.json").read_text())

    # Healthy claim cross-checked normally.
    assert last_run["verdicts"]["frxusd_supply"]["tag"] == "✅"
    # Broken claim fell back to Parallel-only → ❌ per STRICT policy.
    assert last_run["verdicts"]["top_holders"]["tag"] == "❌"

    # README keeps healthy claim in metrics table and puts broken claim
    # under founder-questions — the rest of the section did NOT crash.
    readme = (target_dir / "README.md").read_text()
    assert "| Metric | Value | Source |" in readme
    assert "frxUSD total supply" in readme
    assert "## Pytania do founders" in readme
    assert "Top token holders" in readme

    # Skill return: broken claim shows up in both manual-review and warnings.
    assert "top_holders" in result.manual_review_claims
    assert any("top_holders" in w for w in result.warnings)


def test_onchain_cache_key_is_per_contract_and_selector(tmp_path):
    """Two claims against the same target must not collide in the on-chain
    cache: the cache key has to factor in (contract, selector). First run
    hits the HTTP layer twice (once per distinct selector); second run with
    the same manifest uses cached values and makes zero new HTTP calls.
    """
    manifest = _write_manifest(
        tmp_path / "overview_claims.json",
        [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "frxUSD total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xFRX",
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
                    "contract": "0xSFRX",
                    "selector": "0x01e1d114",
                    "decimals": 18,
                },
            },
        ],
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 1.0,
            "output": {
                "frxusd_supply": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/s",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
                "sfrxusd_total_assets": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/v",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.9,
                },
            },
        }
    )

    http_calls: list[dict] = []

    def fake_http_get(url, params):
        http_calls.append(dict(params))
        if params.get("action") == "tokensupply":
            return {"status": "1", "result": _ONEM_E18_DEC}
        return {"jsonrpc": "2.0", "id": 1, "result": _ONEM_E18_HEX}

    kwargs = dict(
        config=_frx_config(),
        overview_claims_path=manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=parallel_client,
        http_get=fake_http_get,
        cache_root=tmp_path / "_cache",
    )

    run_dd_new(**kwargs)
    # First run: 2 distinct on-chain calls (tokensupply + eth_call).
    assert len(http_calls) == 2

    run_dd_new(**kwargs)
    # Second run: both served from cache — no new HTTP calls, no new
    # Parallel call either.
    assert len(http_calls) == 2
    assert len(parallel_client.calls) == 1


def test_low_confidence_on_hard_claim_emits_warning(tmp_path):
    """Low Parallel confidence on a hard claim still surfaces an explicit
    warning — Parallel confidence never replaces manual review but a weak
    signal is worth flagging loudly."""
    manifest = _write_manifest(
        tmp_path / "overview_claims.json",
        [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "frxUSD total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xFRX",
                    "decimals": 18,
                },
            },
        ],
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 0.4,
            "output": {
                "frxusd_supply": {
                    "value": "1000000",
                    "evidence_url": "https://frax.com/s",
                    "evidence_date": "2026-04-08",
                    "confidence": 0.3,
                },
            },
        }
    )

    def fake_http_get(url, params):
        return {"status": "1", "result": _ONEM_E18_DEC}

    result = run_dd_new(
        config=_frx_config(),
        overview_claims_path=manifest,
        cost_preview_usd=0.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=parallel_client,
        http_get=fake_http_get,
    )

    assert "frxusd_supply" in result.manual_review_claims
    assert any("frxusd_supply" in w for w in result.warnings)
    assert any("confidence" in w.lower() for w in result.warnings)

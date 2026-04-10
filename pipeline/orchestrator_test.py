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

from pipeline.legal_matching import LegalRegistryResult
from pipeline.orchestrator import run_dd_new
from pipeline.parallel_test import FakeParallelClient
from pipeline.verdict_engine import Finding
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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
                    "chain": "ethereum",
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


def _combined_pl_config() -> TargetConfig:
    return TargetConfig(
        target_type="combined",
        domain="foo.pl",
        chain="ethereum",
        jurisdiction="PL",
        tier="lite",
        soft_cap_usd=2.0,
        slug="foo-pl",
        confidence_threshold=0.7,
    )


def test_combined_target_runs_team_section_after_overview(tmp_path):
    """For combined / company targets the orchestrator runs the Team flow
    after Overview: appends Team markdown to README, merges Team verdicts/
    findings into last_run.json, and surfaces team manual-review claims in
    the skill return value.
    """
    overview_manifest = _write_manifest(
        tmp_path / "overview_claims.json",
        [
            {
                "name": "frxusd_supply",
                "kind": "hard",
                "display_label": "Foo total supply",
                "parallel_field": "frxusd_supply",
                "onchain": {
                    "fetcher": "total_supply",
                    "contract": "0xFRX",
                    "decimals": 18,
                    "chain": "ethereum",
                },
            }
        ],
    )
    team_manifest_path = tmp_path / "team-claims.json"
    team_manifest_path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "name": "officer:Jan Kowalski",
                        "kind": "hard",
                        "display_label": "Jan Kowalski",
                        "parallel_field": "officer_jan_kowalski",
                        "legal_expected": True,
                    }
                ]
            }
        )
    )

    # Two-call FakeParallelClient: overview call returns frxusd_supply,
    # team call returns officer_jan_kowalski. Use a tiny script-style fake.
    class ScriptedClient:
        def __init__(self):
            self.calls: list[dict] = []
            self.responses = [
                {
                    "task_id": "overview-1",
                    "cost_usd": 1.0,
                    "output": {
                        "frxusd_supply": {
                            "value": "1000000",
                            "evidence_url": "https://foo.pl/stats",
                            "evidence_date": "2026-04-09",
                            "confidence": 0.9,
                        }
                    },
                },
                {
                    "task_id": "team-1",
                    "cost_usd": 0.5,
                    "output": {
                        "officer_jan_kowalski": {
                            "value": "Prezes Zarządu",
                            "evidence_url": "https://foo.pl/team",
                            "evidence_date": "2026-04-09",
                            "confidence": 0.9,
                        }
                    },
                },
            ]

        def run_task(self, *, processor, schema, prompt):
            self.calls.append({"processor": processor, "schema": schema, "prompt": prompt})
            return self.responses.pop(0)

    parallel_client = ScriptedClient()

    def fake_http_get(url, params):
        if params.get("action") == "tokensupply":
            return {"status": "1", "result": _ONEM_E18_DEC}
        raise AssertionError(f"unexpected http_get {params}")

    def legal_adapter():
        return LegalRegistryResult(
            findings=[
                Finding(
                    claim="officer:Jan Kowalski",
                    value="Prezes Zarządu",
                    source="krs",
                    source_kind="legal",
                    evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
                    evidence_date="2026-04-09",
                )
            ]
        )

    result = run_dd_new(
        config=_combined_pl_config(),
        overview_claims_path=overview_manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env={"PARALLEL_API_KEY": "p", "ETHERSCAN_API_KEY": "e"},
        parallel_client=parallel_client,
        http_get=fake_http_get,
        team_claims_path=team_manifest_path,
        legal_adapter=legal_adapter,
    )

    target_dir = tmp_path / "foo-pl"
    readme = (target_dir / "README.md").read_text()
    last_run = json.loads((target_dir / "last_run.json").read_text())

    # Both sections in the README
    assert "# Overview — foo-pl" in readme
    assert "# Team — foo-pl" in readme
    assert "Jan Kowalski" in readme

    # Team verdict merged into last_run.json
    assert last_run["verdicts"]["officer:Jan Kowalski"]["tag"] == "✅"
    assert last_run["claims"]["officer:Jan Kowalski"]["kind"] == "hard"
    # Overview verdict still there
    assert last_run["verdicts"]["frxusd_supply"]["tag"] == "✅"

    # Skill return surfaces team manual-review claim
    assert "officer:Jan Kowalski" in result.manual_review_claims
    assert "frxusd_supply" in result.manual_review_claims

    # Two parallel calls (one per section)
    assert len(parallel_client.calls) == 2

    # Audit log contains both runs
    audit_lines = (target_dir / "parallel-runs.jsonl").read_text().splitlines()
    assert len(audit_lines) == 2


def test_protocol_target_skips_team_section(tmp_path):
    """A pure protocol target (no company) must not invoke the Team flow even
    when team_claims_path is None — the orchestrator just renders Overview."""
    overview_manifest = _write_manifest(
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
                    "chain": "ethereum",
                },
            }
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
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                }
            },
        }
    )

    def fake_http_get(url, params):
        return {"status": "1", "result": _ONEM_E18_DEC}

    result = run_dd_new(
        config=_frx_config(),  # protocol type
        overview_claims_path=overview_manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=parallel_client,
        http_get=fake_http_get,
    )

    readme = (tmp_path / "frax-com" / "README.md").read_text()
    assert "# Overview" in readme
    assert "# Team" not in readme
    assert result.verdict_tag in {"✅", "⚠️", "❌"}


def test_full_report_includes_generic_sections(tmp_path):
    """Phase 5: orchestrator accepts section_manifests for generic sections
    (Mechanism, Revenue, etc.) and appends their rendered markdown to the
    README after Overview + Team."""
    overview_manifest = _write_manifest(
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
                    "chain": "ethereum",
                },
            }
        ],
    )

    # Generic section manifests
    mechanism_manifest = tmp_path / "mechanism_claims.json"
    mechanism_manifest.write_text(
        json.dumps(
            {
                "section": "Mechanism",
                "claims": [
                    {
                        "name": "mechanism_description",
                        "kind": "soft",
                        "display_label": "How the protocol works",
                        "parallel_field": "mechanism_description",
                    },
                ],
            }
        )
    )
    risks_manifest = tmp_path / "risks_claims.json"
    risks_manifest.write_text(
        json.dumps(
            {
                "section": "Risks",
                "claims": [
                    {
                        "name": "governance_centralization",
                        "kind": "hard",
                        "display_label": "Governance centralization",
                        "parallel_field": "governance_centralization",
                        "severity": "High",
                    },
                ],
            }
        )
    )

    call_count = 0

    class MultiClient:
        def __init__(self):
            self.calls: list[dict] = []

        def run_task(self, *, processor, schema, prompt):
            self.calls.append({"processor": processor, "prompt": prompt})
            nonlocal call_count
            call_count += 1
            # Return different outputs based on section detected in prompt
            if "Overview" in prompt or "frxusd_supply" in prompt:
                return {
                    "task_id": f"t-{call_count}",
                    "cost_usd": 0.5,
                    "output": {
                        "frxusd_supply": {
                            "value": "1000000",
                            "evidence_url": "https://frax.com/s",
                            "evidence_date": "2026-04-10",
                            "confidence": 0.9,
                        },
                    },
                }
            if "Mechanism" in prompt:
                return {
                    "task_id": f"t-{call_count}",
                    "cost_usd": 0.3,
                    "output": {
                        "mechanism_description": {
                            "value": "Delta-neutral position: short ETH perp + long staked ETH",
                            "evidence_url": "https://ethena.fi/docs",
                            "evidence_date": "2026-04-10",
                            "confidence": 0.95,
                        },
                    },
                }
            if "Risks" in prompt:
                return {
                    "task_id": f"t-{call_count}",
                    "cost_usd": 0.3,
                    "output": {
                        "governance_centralization": {
                            "value": "S&P B-, ECB paper confirms whale dominance",
                            "evidence_url": "https://spglobal.com/sky",
                            "evidence_date": "2026-04-10",
                            "confidence": 0.92,
                        },
                    },
                }
            raise AssertionError(f"unexpected prompt: {prompt[:80]}")

    client = MultiClient()

    def fake_http_get(url, params):
        return {"status": "1", "result": _ONEM_E18_DEC}

    run_dd_new(
        config=_frx_config(),
        overview_claims_path=overview_manifest,
        cost_preview_usd=1.5,
        targets_root=tmp_path,
        env=_env(),
        parallel_client=client,
        http_get=fake_http_get,
        section_manifests=[mechanism_manifest, risks_manifest],
    )

    target_dir = tmp_path / "frax-com"
    readme = (target_dir / "README.md").read_text()

    # All sections present in README
    assert "# Overview" in readme
    assert "# Mechanism" in readme
    assert "# Risks" in readme
    # STRICT with 1 source → ❌ → claims in Pytania (rationale visible)
    assert "How the protocol works" in readme
    assert "Governance centralization" in readme

    # last_run.json contains all verdicts
    last_run = json.loads((target_dir / "last_run.json").read_text())
    assert "frxusd_supply" in last_run["verdicts"]
    assert "mechanism_description" in last_run["verdicts"]
    assert "governance_centralization" in last_run["verdicts"]

    # 3 Parallel calls: Overview + Mechanism + Risks
    assert len(client.calls) == 3

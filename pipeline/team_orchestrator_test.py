"""End-to-end tests for `run_team_section` — the Team companion to run_dd_new.

Drives a wide Parallel call for the Team manifest, calls the injected
legal-registry adapter, merges findings per claim, decides verdicts (with
the requires_legal flag for ownership claims), renders the Team markdown,
caches the legal response under namespace "legal" with TTL 30d, and returns
findings/verdicts ready for the orchestrator to merge into last_run.json.

Mocks only at boundaries: Parallel SDK + legal adapter callable. Real
verdict-engine, real renderer, real cache, real filesystem (tmp_path).
"""

import json
from pathlib import Path

from pipeline.cache import Cache
from pipeline.legal_matching import LegalRegistryResult, MaskedPerson
from pipeline.parallel_test import FakeParallelClient
from pipeline.team_orchestrator import run_team_section
from pipeline.verdict_engine import Finding
from pipeline.wizard import TargetConfig


def _config() -> TargetConfig:
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


def _write_team_manifest(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "name": "officer:Jan Kowalski",
                        "kind": "hard",
                        "display_label": "Jan Kowalski",
                        "parallel_field": "officer_jan_kowalski",
                        "legal_expected": True,
                    },
                    {
                        "name": "owner:Anna Nowak",
                        "kind": "hard",
                        "display_label": "Anna Nowak",
                        "parallel_field": "owner_anna_nowak",
                        "legal_expected": True,
                    },
                ]
            }
        )
    )
    return path


def _legal_finding(claim: str, value: str) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source="krs",
        source_kind="legal",
        evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
        evidence_date="2026-04-09",
    )


def _bound_legal_result(*findings: Finding) -> LegalRegistryResult:
    """Helper for tests that already-bind legal findings (analogous to
    OpenCorporates with full names). Wraps in a LegalRegistryResult."""
    return LegalRegistryResult(findings=list(findings), candidates=[])


def test_run_team_section_merges_parallel_and_legal_into_green_verdicts(tmp_path):
    manifest = _write_team_manifest(tmp_path / "team-claims.json")
    parallel_client = FakeParallelClient(
        response={
            "task_id": "team-task-1",
            "cost_usd": 0.5,
            "output": {
                "officer_jan_kowalski": {
                    "value": "Prezes Zarządu",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                },
                "owner_anna_nowak": {
                    "value": "50 udziałów",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.85,
                },
            },
        }
    )

    legal_calls: list[dict] = []

    def legal_adapter() -> LegalRegistryResult:
        legal_calls.append({})
        return _bound_legal_result(
            _legal_finding("officer:Jan Kowalski", "Prezes Zarządu"),
            _legal_finding("owner:Anna Nowak", "50 udziałów"),
        )

    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400, "legal": 30 * 86400})
    target_dir = tmp_path / "foo-pl"
    target_dir.mkdir()

    result = run_team_section(
        config=_config(),
        team_claims_path=manifest,
        cache=cache,
        parallel_client=parallel_client,
        legal_adapter=legal_adapter,
        target_dir=target_dir,
    )

    # Both ownership claims have parallel + legal → ✅
    assert result.verdicts["officer:Jan Kowalski"]["tag"] == "✅"
    assert result.verdicts["owner:Anna Nowak"]["tag"] == "✅"
    # Both hard → manual review required
    assert result.claims["officer:Jan Kowalski"]["requires_manual_review"] is True
    # Markdown rendered with the team layout
    assert "# Team — foo-pl" in result.markdown
    assert "## Zarząd" in result.markdown
    assert "## Wspólnicy" in result.markdown
    assert "Jan Kowalski" in result.markdown
    assert "Anna Nowak" in result.markdown
    # Single Parallel call for the whole section
    assert len(parallel_client.calls) == 1
    # Legal adapter called exactly once on the first run
    assert len(legal_calls) == 1


def test_run_team_section_warns_when_legal_missing(tmp_path):
    """Ownership claim with parallel only (legal adapter returns nothing) →
    verdict ⚠️ via requires_legal, AND surfaces under Open questions."""
    manifest = _write_team_manifest(tmp_path / "team-claims.json")
    parallel_client = FakeParallelClient(
        response={
            "task_id": "team-task-2",
            "cost_usd": 0.5,
            "output": {
                "officer_jan_kowalski": {
                    "value": "Prezes",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                },
                "owner_anna_nowak": {
                    "value": "50%",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                },
            },
        }
    )

    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400, "legal": 30 * 86400})
    target_dir = tmp_path / "foo-pl"
    target_dir.mkdir()

    result = run_team_section(
        config=_config(),
        team_claims_path=manifest,
        cache=cache,
        parallel_client=parallel_client,
        legal_adapter=lambda: LegalRegistryResult(),  # registry returned nothing
        target_dir=target_dir,
    )

    # Ownership claims downgraded to ⚠️ because no legal source confirmed them
    assert result.verdicts["officer:Jan Kowalski"]["tag"] == "⚠️"
    assert result.verdicts["owner:Anna Nowak"]["tag"] == "⚠️"
    # Open questions section surfaces both
    assert "## Open questions" in result.markdown
    assert "## Pytania do founders" in result.markdown


def test_run_team_section_caches_legal_response(tmp_path):
    """Second call within TTL must hit the legal cache, not re-invoke the
    adapter. Cache namespace is `legal` with TTL 30d."""
    manifest = _write_team_manifest(tmp_path / "team-claims.json")

    def make_client():
        return FakeParallelClient(
            response={
                "task_id": "team-task-cache",
                "cost_usd": 0.5,
                "output": {
                    "officer_jan_kowalski": {
                        "value": "Prezes",
                        "evidence_url": "https://foo.pl/team",
                        "evidence_date": "2026-04-09",
                        "confidence": 0.9,
                    },
                    "owner_anna_nowak": {
                        "value": "50%",
                        "evidence_url": "https://foo.pl/team",
                        "evidence_date": "2026-04-09",
                        "confidence": 0.9,
                    },
                },
            }
        )

    legal_call_count = [0]

    def legal_adapter() -> LegalRegistryResult:
        legal_call_count[0] += 1
        return _bound_legal_result(
            _legal_finding("officer:Jan Kowalski", "Prezes"),
            _legal_finding("owner:Anna Nowak", "50%"),
        )

    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400, "legal": 30 * 86400})
    target_dir = tmp_path / "foo-pl"
    target_dir.mkdir()

    run_team_section(
        config=_config(),
        team_claims_path=manifest,
        cache=cache,
        parallel_client=make_client(),
        legal_adapter=legal_adapter,
        target_dir=target_dir,
    )
    run_team_section(
        config=_config(),
        team_claims_path=manifest,
        cache=cache,
        parallel_client=make_client(),
        legal_adapter=legal_adapter,
        target_dir=target_dir,
    )

    assert legal_call_count[0] == 1  # second run hit the cache


def test_run_team_section_binds_masked_krs_candidates_to_parallel_names(tmp_path):
    """KRS public JSON returns PII-masked candidates (no full names).
    The orchestrator must call match_candidates between parallel fetch
    and verdict to bind candidates to parallel claims, otherwise the
    legal source can never satisfy the cross-check for masked registries.
    This is the Stablewatch / Czarnecki real-world case."""
    manifest = _write_team_manifest(tmp_path / "team-claims.json")

    parallel_client = FakeParallelClient(
        response={
            "task_id": "team-task-masked",
            "cost_usd": 0.5,
            "output": {
                "officer_jan_kowalski": {
                    "value": "Prezes Zarządu",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                },
                "owner_anna_nowak": {
                    "value": "50 udziałów",
                    "evidence_url": "https://foo.pl/team",
                    "evidence_date": "2026-04-09",
                    "confidence": 0.9,
                },
            },
        }
    )

    def legal_adapter() -> LegalRegistryResult:
        return LegalRegistryResult(
            findings=[],
            candidates=[
                MaskedPerson(
                    surname_mask="K*******",  # Kowalski (8 chars)
                    given_names_mask=["J**"],  # Jan (3 chars)
                    evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
                    evidence_date="2026-04-09",
                    role="PREZES ZARZĄDU",
                ),
                MaskedPerson(
                    surname_mask="N****",  # Nowak (5 chars)
                    given_names_mask=["A***"],  # Anna (4 chars)
                    evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
                    evidence_date="2026-04-09",
                    shares_text="50 UDZIAŁÓW O ŁĄCZNEJ WARTOŚCI 5 000,00 ZŁ",
                ),
            ],
        )

    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400, "legal": 30 * 86400})
    target_dir = tmp_path / "foo-pl"
    target_dir.mkdir()

    result = run_team_section(
        config=_config(),
        team_claims_path=manifest,
        cache=cache,
        parallel_client=parallel_client,
        legal_adapter=legal_adapter,
        target_dir=target_dir,
    )

    # Both ownership claims got rebound from masked candidates → ✅
    assert result.verdicts["officer:Jan Kowalski"]["tag"] == "✅"
    assert result.verdicts["owner:Anna Nowak"]["tag"] == "✅"

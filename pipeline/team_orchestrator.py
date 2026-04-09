"""Team section orchestrator — Phase 4 companion to run_dd_new.

Composes the Team flow:
    team manifest loader → wide Parallel call (cached 7d) → legal-registry
    adapter (cached 30d) → verdict engine (with requires_legal flag) →
    section renderer.

System-boundary collaborators (Parallel client, legal adapter callable,
filesystem) are injected so the function is testable end-to-end without
real network calls.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.audit_log import append_parallel_run
from pipeline.cache import Cache
from pipeline.parallel import ParallelClient, fetch_team_claims
from pipeline.section_renderer import render_team
from pipeline.team_claims import TeamClaim, load_team_claims
from pipeline.verdict_engine import Finding, decide
from pipeline.wizard import TargetConfig


@dataclass(frozen=True)
class TeamSectionResult:
    markdown: str
    findings: list[Finding]
    verdicts: dict[str, dict[str, str]]
    claims: dict[str, dict[str, Any]]
    manual_review_claims: list[str]


def run_team_section(
    *,
    config: TargetConfig,
    team_claims_path: Path,
    cache: Cache,
    parallel_client: ParallelClient,
    legal_adapter: Callable[[], list[Finding]],
    target_dir: Path,
) -> TeamSectionResult:
    claims = load_team_claims(team_claims_path)

    parallel_findings = _fetch_parallel_findings_cached(
        cache=cache,
        config=config,
        claims=claims,
        client=parallel_client,
        target_dir=target_dir,
    )
    legal_findings = _fetch_legal_findings_cached(
        cache=cache,
        config=config,
        claims=claims,
        legal_adapter=legal_adapter,
    )

    parallel_by_claim: dict[str, Finding] = {f.claim: f for f in parallel_findings}
    legal_by_claim: dict[str, list[Finding]] = {}
    for f in legal_findings:
        legal_by_claim.setdefault(f.claim, []).append(f)

    rendered_claims: list[dict[str, Any]] = []
    verdicts_out: dict[str, dict[str, str]] = {}
    claims_out: dict[str, dict[str, Any]] = {}
    manual_review: list[str] = []

    for claim in claims:
        findings: list[Finding] = []
        if claim.name in parallel_by_claim:
            findings.append(parallel_by_claim[claim.name])
        findings.extend(legal_by_claim.get(claim.name, []))

        verdict = decide(
            claim=claim.name,
            findings=findings,
            kind=claim.kind,
            confidence_threshold=config.confidence_threshold,
            requires_legal=claim.legal_expected,
        )

        rendered_claims.append(
            {
                "name": claim.name,
                "display_label": claim.display_label,
                "kind": claim.kind,
                "verdict": verdict,
                "findings": findings,
            }
        )
        verdicts_out[claim.name] = {
            "tag": verdict.tag,
            "rationale": verdict.rationale,
        }
        claims_out[claim.name] = {
            "kind": claim.kind,
            "requires_manual_review": verdict.requires_manual_review,
            "legal_expected": claim.legal_expected,
        }
        if verdict.requires_manual_review:
            manual_review.append(claim.name)

    section = {"target_name": config.slug, "claims": rendered_claims}
    markdown = render_team(section)

    all_findings = [f for c in rendered_claims for f in c["findings"]]
    return TeamSectionResult(
        markdown=markdown,
        findings=all_findings,
        verdicts=verdicts_out,
        claims=claims_out,
        manual_review_claims=manual_review,
    )


def _parallel_cache_key(config: TargetConfig, claims: list[TeamClaim]) -> str:
    fields = ",".join(sorted(c.parallel_field for c in claims))
    return f"team:{config.slug}:{config.tier}:{fields}"


def _legal_cache_key(config: TargetConfig) -> str:
    return f"team-legal:{config.slug}:{config.jurisdiction.lower()}"


def _fetch_parallel_findings_cached(
    *,
    cache: Cache,
    config: TargetConfig,
    claims: list[TeamClaim],
    client: ParallelClient,
    target_dir: Path,
) -> list[Finding]:
    key = _parallel_cache_key(config, claims)
    cached = cache.get(config.slug, "parallel", key)
    if cached is not None:
        return [_finding_from_dict(d) for d in cached]
    findings, audit = fetch_team_claims(
        target_name=config.slug,
        target_domain=config.domain,
        tier=config.tier,
        claims=claims,
        client=client,
    )
    cache.set(
        config.slug,
        "parallel",
        key,
        [_finding_to_dict(f) for f in findings],
    )
    append_parallel_run(target_dir / "parallel-runs.jsonl", audit)
    return findings


def _fetch_legal_findings_cached(
    *,
    cache: Cache,
    config: TargetConfig,
    claims: list[TeamClaim],
    legal_adapter: Callable[[], list[Finding]],
) -> list[Finding]:
    # Skip the registry call entirely if no claim asked for legal confirmation.
    if not any(c.legal_expected for c in claims):
        return []
    key = _legal_cache_key(config)
    cached = cache.get(config.slug, "legal", key)
    if cached is not None:
        return [_finding_from_dict(d) for d in cached]
    findings = legal_adapter()
    cache.set(
        config.slug,
        "legal",
        key,
        [_finding_to_dict(f) for f in findings],
    )
    return findings


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    return {
        "claim": f.claim,
        "value": f.value,
        "source": f.source,
        "source_kind": f.source_kind,
        "evidence_url": f.evidence_url,
        "evidence_date": f.evidence_date,
        "confidence": f.confidence,
    }


def _finding_from_dict(d: dict[str, Any]) -> Finding:
    return Finding(
        claim=d["claim"],
        value=d["value"],
        source=d["source"],
        source_kind=d["source_kind"],
        evidence_url=d["evidence_url"],
        evidence_date=d["evidence_date"],
        confidence=d.get("confidence"),
    )

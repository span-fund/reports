"""Generic section orchestrator (Phase 5).

Runs N generic sections through the pipeline:
    manifest loader → Parallel fetch (cached) → verdict engine → renderer.

Each section gets its own Parallel call. A failing section produces an error
result but does not block other sections (graceful degradation).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.audit_log import append_parallel_run
from pipeline.cache import Cache
from pipeline.parallel import ParallelClient, fetch_section_claims
from pipeline.section_claims import SectionClaim, load_section_claims
from pipeline.section_renderer import render_section
from pipeline.verdict_engine import Finding, decide
from pipeline.wizard import TargetConfig

# Section name → render_style mapping
_RENDER_STYLES: dict[str, str] = {
    "Mechanism": "narrative",
    "Collateral": "metric_table",
    "Revenue": "metric_table",
    "Governance": "narrative",
    "Regulatory": "narrative",
    "Historical Incidents": "incident_table",
    "Risks": "risk_table",
    "Key Contracts": "metric_table",
}


@dataclass(frozen=True)
class SectionResult:
    section_name: str
    markdown: str
    findings: list[Finding]
    verdicts: dict[str, dict[str, str]]
    claims: dict[str, dict[str, Any]]
    manual_review_claims: list[str]
    error: str | None = None


def run_sections(
    *,
    config: TargetConfig,
    section_manifests: list[Path],
    parallel_client: ParallelClient,
    cache: Cache,
    target_dir: Path,
) -> list[SectionResult]:
    """Run all generic sections, returning one SectionResult per manifest."""
    results: list[SectionResult] = []
    for manifest_path in section_manifests:
        result = _run_single_section(
            config=config,
            manifest_path=manifest_path,
            parallel_client=parallel_client,
            cache=cache,
            target_dir=target_dir,
        )
        results.append(result)
    return results


def _run_single_section(
    *,
    config: TargetConfig,
    manifest_path: Path,
    parallel_client: ParallelClient,
    cache: Cache,
    target_dir: Path,
) -> SectionResult:
    section_name, claims = load_section_claims(manifest_path)

    try:
        parallel_findings = _fetch_cached(
            config=config,
            section_name=section_name,
            claims=claims,
            client=parallel_client,
            cache=cache,
            target_dir=target_dir,
        )
    except Exception as exc:
        return SectionResult(
            section_name=section_name,
            markdown="",
            findings=[],
            verdicts={},
            claims={},
            manual_review_claims=[],
            error=str(exc),
        )

    parallel_by_claim = {f.claim: f for f in parallel_findings}

    rendered_claims: list[dict[str, Any]] = []
    verdicts_out: dict[str, dict[str, str]] = {}
    claims_out: dict[str, dict[str, Any]] = {}
    manual_review: list[str] = []

    for claim in claims:
        findings: list[Finding] = []
        pf = parallel_by_claim.get(claim.name)
        if pf is not None:
            findings.append(pf)

        verdict = decide(
            claim=claim.name,
            findings=findings,
            kind=claim.kind,
            confidence_threshold=config.confidence_threshold,
        )

        rendered_claims.append(
            {
                "name": claim.name,
                "display_label": claim.display_label,
                "kind": claim.kind,
                "severity": claim.severity,
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
        }
        if verdict.requires_manual_review:
            manual_review.append(claim.name)

    render_style = _RENDER_STYLES.get(section_name, "metric_table")
    section_data = {
        "section_name": section_name,
        "target_name": config.slug,
        "render_style": render_style,
        "claims": rendered_claims,
    }
    markdown = render_section(section_data)

    all_findings = [f for c in rendered_claims for f in c["findings"]]
    return SectionResult(
        section_name=section_name,
        markdown=markdown,
        findings=all_findings,
        verdicts=verdicts_out,
        claims=claims_out,
        manual_review_claims=manual_review,
    )


def _cache_key(config: TargetConfig, section_name: str, claims: list[SectionClaim]) -> str:
    fields = ",".join(sorted(c.parallel_field for c in claims))
    return f"{section_name.lower().replace(' ', '_')}:{config.slug}:{config.tier}:{fields}"


def _fetch_cached(
    *,
    config: TargetConfig,
    section_name: str,
    claims: list[SectionClaim],
    client: ParallelClient,
    cache: Cache,
    target_dir: Path,
) -> list[Finding]:
    key = _cache_key(config, section_name, claims)
    cached = cache.get(config.slug, "parallel", key)
    if cached is not None:
        return [_finding_from_dict(d) for d in cached]

    findings, audit = fetch_section_claims(
        section_name=section_name,
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
    target_dir.mkdir(parents=True, exist_ok=True)
    append_parallel_run(target_dir / "parallel-runs.jsonl", audit)
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

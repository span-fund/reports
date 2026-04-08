"""DD-research skill orchestrator — the thin glue layer for `dd-research new`.

Phase 3: Overview runs off a declarative claim manifest (one JSON per target).
Composition:
    wizard config → env check → cost guard → manifest loader →
    Parallel wide fetch → per-claim on-chain fetch → verdict engine →
    section renderer → audit log → last_run.json.

All system-boundary collaborators (Parallel client, HTTP fetcher, env dict,
filesystem root) are injected so the orchestrator itself stays pure enough to
test end-to-end with no real network.
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipeline.audit_log import append_parallel_run
from pipeline.cache import Cache
from pipeline.cost_guard import check_cost
from pipeline.env_check import require_env_vars
from pipeline.etherscan import fetch_contract_read, fetch_token_balance, fetch_total_supply
from pipeline.overview_claims import OnchainSpec, OverviewClaim, load_overview_claims
from pipeline.parallel import ParallelClient, fetch_overview_claims
from pipeline.section_renderer import render_overview
from pipeline.verdict_engine import Finding, Verdict, decide
from pipeline.wizard import TargetConfig

REQUIRED_ENV = ["PARALLEL_API_KEY", "ETHERSCAN_API_KEY"]

# TTLs per cache namespace — see plans/dd-research-implementation.md
CACHE_TTLS = {
    "parallel": 7 * 86400,  # 7 days
    "onchain": 3600,  # 1 hour
}


@dataclass(frozen=True)
class DDRunResult:
    target_dir: Path
    verdict_tag: str
    manual_review_claims: list[str]
    warnings: list[str]


def run_dd_new(
    *,
    config: TargetConfig,
    overview_claims_path: Path,
    cost_preview_usd: float,
    targets_root: Path,
    env: Mapping[str, str],
    parallel_client: ParallelClient,
    http_get: Callable[[str, dict], dict],
    cache_root: Path | None = None,
    chain_id: int = 1,
) -> DDRunResult:
    # 1. Fail-fast on missing env vars
    require_env_vars(env, REQUIRED_ENV)

    # 2. Cost pre-flight — abort before first Parallel call if over soft cap
    check_cost(preview_usd=cost_preview_usd, soft_cap_usd=config.soft_cap_usd)

    # 3. Target dir scaffold + persist config
    target_dir = targets_root / config.slug
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "config.json").write_text(_json_dumps(asdict(config)))

    # 4. Load the Overview claim manifest (data, not code)
    claims = load_overview_claims(overview_claims_path)

    # 5. Parallel wide fetch — one call for the whole section, cached 7d
    cache = Cache(root=cache_root or targets_root / "_cache", ttls=CACHE_TTLS)
    parallel_cache_key = _parallel_cache_key(config, claims)
    cached = cache.get(config.slug, "parallel", parallel_cache_key)
    if cached is not None:
        parallel_findings = [_finding_from_dict(d) for d in cached]
    else:
        parallel_findings, audit = fetch_overview_claims(
            target_name=config.slug,
            target_domain=config.domain,
            tier=config.tier,
            claims=claims,
            client=parallel_client,
        )
        cache.set(
            config.slug,
            "parallel",
            parallel_cache_key,
            [_finding_to_dict(f) for f in parallel_findings],
        )
        append_parallel_run(target_dir / "parallel-runs.jsonl", audit)

    parallel_by_claim = {f.claim: f for f in parallel_findings}

    # 6. Per-claim on-chain fetch (cached 1h per contract+selector) with
    #    graceful degradation: a failing fetcher drops its finding so the
    #    verdict falls back to ❌ via STRICT policy, but the section still
    #    renders.
    rendered_claims: list[dict[str, Any]] = []
    verdicts_out: dict[str, dict[str, str]] = {}
    claims_out: dict[str, dict[str, Any]] = {}
    manual_review: list[str] = []
    warnings: list[str] = []

    for claim in claims:
        findings: list[Finding] = []
        parallel_finding = parallel_by_claim.get(claim.name)
        if parallel_finding is not None:
            findings.append(parallel_finding)

        if claim.onchain is not None:
            onchain_finding = _fetch_onchain_cached(
                cache=cache,
                target_slug=config.slug,
                claim=claim,
                http_get=http_get,
                api_key=env["ETHERSCAN_API_KEY"],
                chain_id=chain_id,
            )
            if onchain_finding is not None:
                findings.append(onchain_finding)

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

        _collect_warnings(warnings, claim, parallel_finding, verdict, config)

    # 7. Render Overview
    section = {"target_name": config.slug, "claims": rendered_claims}
    (target_dir / "README.md").write_text(render_overview(section))

    # 8. Persist last_run.json — deterministic ground truth
    last_run: dict[str, Any] = {
        "config": asdict(config),
        "findings": [_finding_to_dict(f) for c in rendered_claims for f in c["findings"]],
        "verdicts": verdicts_out,
        "claims": claims_out,
    }
    (target_dir / "last_run.json").write_text(_json_dumps(last_run))

    section_tag = _section_tag(rendered_claims)
    return DDRunResult(
        target_dir=target_dir,
        verdict_tag=section_tag,
        manual_review_claims=manual_review,
        warnings=warnings,
    )


def _parallel_cache_key(config: TargetConfig, claims: list[OverviewClaim]) -> str:
    fields = ",".join(sorted(c.parallel_field for c in claims))
    return f"overview:{config.slug}:{config.tier}:{fields}"


def _onchain_cache_key(claim: OverviewClaim) -> str:
    spec = claim.onchain
    assert spec is not None
    return f"{spec.contract}:{spec.fetcher}:{spec.selector or ''}:{spec.holder or ''}"


def _fetch_onchain_cached(
    *,
    cache: Cache,
    target_slug: str,
    claim: OverviewClaim,
    http_get: Callable[[str, dict], dict],
    api_key: str,
    chain_id: int,
) -> Finding | None:
    key = _onchain_cache_key(claim)
    cached = cache.get(target_slug, "onchain", key)
    if cached is not None:
        return _finding_from_dict(cached)
    try:
        finding = _dispatch_onchain(
            claim=claim,
            http_get=http_get,
            api_key=api_key,
            chain_id=chain_id,
        )
    except Exception:
        return None
    cache.set(target_slug, "onchain", key, _finding_to_dict(finding))
    return finding


def _dispatch_onchain(
    *,
    claim: OverviewClaim,
    http_get: Callable[[str, dict], dict],
    api_key: str,
    chain_id: int,
) -> Finding:
    spec: OnchainSpec = claim.onchain  # type: ignore[assignment]
    if spec.fetcher == "total_supply":
        raw = fetch_total_supply(
            chain_id=chain_id,
            token_address=spec.contract,
            decimals=spec.decimals,
            http_get=http_get,
            api_key=api_key,
        )
        # fetch_total_supply hard-codes the claim name to "totalSupply";
        # rename it to match the manifest so verdict-engine sees a coherent
        # set of findings for the same claim.
        return Finding(
            claim=claim.name,
            value=raw.value,
            source=raw.source,
            source_kind=raw.source_kind,
            evidence_url=raw.evidence_url,
            evidence_date=raw.evidence_date,
            confidence=raw.confidence,
        )
    if spec.fetcher == "contract_read":
        if spec.selector is None:
            raise ValueError(f"contract_read on {claim.name} requires selector")
        return fetch_contract_read(
            chain_id=chain_id,
            contract=spec.contract,
            selector=spec.selector,
            decimals=spec.decimals,
            claim_name=claim.name,
            http_get=http_get,
            api_key=api_key,
        )
    if spec.fetcher == "token_balance":
        if spec.holder is None:
            raise ValueError(f"token_balance on {claim.name} requires holder")
        return fetch_token_balance(
            chain_id=chain_id,
            holder_address=spec.holder,
            token_address=spec.contract,
            decimals=spec.decimals,
            claim_name=claim.name,
            http_get=http_get,
            api_key=api_key,
        )
    raise ValueError(f"unknown onchain fetcher {spec.fetcher!r} for {claim.name}")


def _collect_warnings(
    warnings: list[str],
    claim: OverviewClaim,
    parallel_finding: Finding | None,
    verdict: Verdict,
    config: TargetConfig,
) -> None:
    if claim.kind == "hard" and parallel_finding is not None:
        pc = parallel_finding.confidence
        if pc is not None and pc < config.confidence_threshold:
            warnings.append(
                f"low Parallel confidence on hard claim {claim.name}: "
                f"{pc:.2f} < threshold {config.confidence_threshold:.2f}"
            )
    if verdict.tag == "❌":
        warnings.append(f"claim {claim.name} failed STRICT cross-check: {verdict.rationale}")


def _section_tag(rendered_claims: list[dict[str, Any]]) -> str:
    """Coarse section-level tag for the skill return value: ❌ if any claim
    failed, ⚠️ if any disagree, else ✅."""
    tags = {c["verdict"].tag for c in rendered_claims}
    if "❌" in tags:
        return "❌"
    if "⚠️" in tags:
        return "⚠️"
    return "✅"


def _finding_to_dict(f: Any) -> dict[str, Any]:
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


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)

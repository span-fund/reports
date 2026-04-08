"""DD-research skill orchestrator — the thin glue layer for `dd-research new`.

Composes wizard config + env check + cost guard + Parallel wrapper + Etherscan
wrapper + verdict engine + section renderer + audit log + last_run.json. All
system-boundary collaborators (Parallel client, HTTP fetcher, env dict,
filesystem root) are injected so the orchestrator itself stays pure enough to
test end-to-end with no real network.
"""

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pipeline.audit_log import append_parallel_run
from pipeline.cache import Cache
from pipeline.claim_classifier import classify
from pipeline.cost_guard import check_cost
from pipeline.env_check import require_env_vars
from pipeline.etherscan import fetch_total_supply
from pipeline.parallel import ParallelClient, fetch_overview_total_supply
from pipeline.section_renderer import render_overview
from pipeline.verdict_engine import Finding, decide
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
    token_address: str,
    token_decimals: int,
    cost_preview_usd: float,
    targets_root: Path,
    env: Mapping[str, str],
    parallel_client: ParallelClient,
    http_get: Callable[[str, dict], dict],
    cache_root: Path | None = None,
) -> DDRunResult:
    # 1. Fail-fast on missing env vars
    require_env_vars(env, REQUIRED_ENV)

    # 2. Cost pre-flight — abort before first Parallel call if over soft cap
    check_cost(preview_usd=cost_preview_usd, soft_cap_usd=config.soft_cap_usd)

    # 3. Target dir scaffold
    target_dir = targets_root / config.slug
    target_dir.mkdir(parents=True, exist_ok=True)

    # 4. Persist config
    (target_dir / "config.json").write_text(_json_dumps(asdict(config)))

    # 5. Parallel (cache-aware) + Etherscan
    cache = Cache(root=cache_root or targets_root / "_cache", ttls=CACHE_TTLS)
    parallel_cache_key = f"overview:totalSupply:{config.slug}:{config.tier}"
    cached = cache.get(config.slug, "parallel", parallel_cache_key)
    if cached is not None:
        parallel_finding = _finding_from_dict(cached)
    else:
        parallel_finding, audit = fetch_overview_total_supply(
            target_name=config.slug,
            target_domain=config.domain,
            tier=config.tier,
            client=parallel_client,
        )
        cache.set(config.slug, "parallel", parallel_cache_key, _finding_to_dict(parallel_finding))
        append_parallel_run(target_dir / "parallel-runs.jsonl", audit)

    onchain_finding = fetch_total_supply(
        chain_id=1,  # ethereum mainnet for tracer
        token_address=token_address,
        decimals=token_decimals,
        http_get=http_get,
        api_key=env["ETHERSCAN_API_KEY"],
    )

    # 6. Classify claim + verdict with Phase 2 hard/soft taxonomy
    findings = [parallel_finding, onchain_finding]
    kind = classify(section="Overview", claim_name="totalSupply")
    verdict = decide(
        claim="totalSupply",
        findings=findings,
        kind=kind,
        confidence_threshold=config.confidence_threshold,
    )

    # 7. Render Overview section
    section = {
        "target_name": config.slug,
        "claims": [
            {
                "name": "totalSupply",
                "kind": kind,
                "verdict": verdict,
                "findings": findings,
            }
        ],
    }
    readme = render_overview(section)
    (target_dir / "README.md").write_text(readme)

    # 8. Collect manual-review list + warnings for the skill layer
    manual_review_claims = ["totalSupply"] if verdict.requires_manual_review else []
    warnings: list[str] = []
    if kind == "hard":
        parallel_confidence = parallel_finding.confidence
        if parallel_confidence is not None and parallel_confidence < config.confidence_threshold:
            warnings.append(
                f"low Parallel confidence on hard claim totalSupply: "
                f"{parallel_confidence:.2f} < threshold {config.confidence_threshold:.2f}"
            )

    # 9. Persist last_run.json — the deterministic ground truth for refresh/section modes
    last_run: dict[str, Any] = {
        "config": asdict(config),
        "findings": [_finding_to_dict(f) for f in findings],
        "verdicts": {"totalSupply": {"tag": verdict.tag, "rationale": verdict.rationale}},
        "claims": {
            "totalSupply": {
                "kind": kind,
                "requires_manual_review": verdict.requires_manual_review,
            }
        },
    }
    (target_dir / "last_run.json").write_text(_json_dumps(last_run))

    return DDRunResult(
        target_dir=target_dir,
        verdict_tag=verdict.tag,
        manual_review_claims=manual_review_claims,
        warnings=warnings,
    )


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

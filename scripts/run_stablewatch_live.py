"""Live HITL E2E runner for stablewatch — Phase 4 Team section.

Real Parallel.ai call for the Team manifest, real KRS lookup via the
public Polish Krajowy Rejestr Sądowy JSON API (no key required), no
Etherscan (Stablewatch has no token). The orchestrator's Team flow is
called directly via run_team_section so we don't need an Overview
manifest for a pure-company target.

This is the Czarnecki case in action: Parallel will likely find Jacek
Czarnecki listed as a Stablewatch co-founder on LinkedIn / company
materials, but KRS Odpis Aktualny no longer lists him as a current
shareholder (removed 2025-12-29). The verdict-engine should downgrade
the ownership claim about him to ⚠️ with "no registry confirmation".

Usage: uv run python scripts/run_stablewatch_live.py
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from parallel import Parallel

from pipeline.cache import Cache
from pipeline.env_check import require_env_vars
from pipeline.krs import fetch_legal_findings_krs
from pipeline.legal_matching import LegalRegistryResult
from pipeline.parallel_pricing import lookup_task_cost
from pipeline.team_orchestrator import run_team_section
from pipeline.wizard import TargetConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
STABLEWATCH_KRS = "0001174918"


def _load_env() -> None:
    path = REPO_ROOT / ".env"
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _http_get_json(url: str, params: dict) -> dict:
    """Generic JSON GET — works for both Etherscan-style and KRS-style endpoints
    since both put their args in the query string."""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": "dd-research/0.1 (github.com/span-fund/reports)"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class ParallelAdapter:
    """Same shape as scripts/run_frax_live.py — adapts the real `parallel`
    SDK to the narrow ParallelClient protocol the orchestrator expects."""

    def __init__(self, client: Parallel):
        self._client = client

    def run_task(self, *, processor: str, schema: dict, prompt: str) -> dict[str, Any]:
        task = self._client.task_run.create(
            input=prompt,
            processor=processor,
            task_spec={
                "output_schema": {
                    "type": "json",
                    "json_schema": schema,
                }
            },
        )
        result = self._client.task_run.result(run_id=task.run_id)
        cost_usd, cost_source = lookup_task_cost(processor)
        output = result.output
        content = getattr(output, "content", output)
        if isinstance(content, str):
            content = json.loads(content)
        return {
            "task_id": task.run_id,
            "cost_usd": cost_usd,
            "cost_source": cost_source,
            "output": content,
        }


def make_krs_adapter(krs_number: str):
    """Build the zero-arg legal_adapter callable that run_team_section
    expects. Returns a LegalRegistryResult — KRS public JSON masks PII so
    the result carries candidates (not bound findings); the orchestrator's
    match_candidates step rebinds them to parallel claims by initial+length.
    """

    def adapter() -> LegalRegistryResult:
        return fetch_legal_findings_krs(krs_number=krs_number, http_get=_http_get_json)

    return adapter


def main() -> None:
    _load_env()
    require_env_vars(os.environ, ["PARALLEL_API_KEY"])

    config_path = REPO_ROOT / "targets" / "stablewatch" / "config.json"
    raw = json.loads(config_path.read_text())
    config = TargetConfig(
        target_type=raw["target_type"],
        domain=raw["domain"],
        chain=raw["chain"],
        jurisdiction=raw["jurisdiction"],
        tier=raw["tier"],
        soft_cap_usd=raw["soft_cap_usd"],
        slug=raw["slug"],
        confidence_threshold=raw.get("confidence_threshold", 0.7),
    )

    team_manifest = REPO_ROOT / "targets" / "stablewatch" / "team-claims.json"
    if not team_manifest.exists():
        raise FileNotFoundError(f"team manifest missing: {team_manifest}")

    target_dir = REPO_ROOT / "targets" / config.slug
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "config.json").write_text(json.dumps(asdict(config), indent=2))

    cache = Cache(
        root=REPO_ROOT / "targets" / "_cache",
        ttls={"parallel": 7 * 86400, "legal": 30 * 86400},
    )

    parallel_client = ParallelAdapter(Parallel(api_key=os.environ["PARALLEL_API_KEY"]))
    legal_adapter = make_krs_adapter(STABLEWATCH_KRS)

    print(f"=> target: {config.slug} ({config.domain}), jurisdiction={config.jurisdiction}")
    print(f"=> team manifest: {team_manifest}")
    print(f"=> KRS number: {STABLEWATCH_KRS}")
    print()

    result = run_team_section(
        config=config,
        team_claims_path=team_manifest,
        cache=cache,
        parallel_client=parallel_client,
        legal_adapter=legal_adapter,
        target_dir=target_dir,
    )

    # Persist the team markdown to README.md (this target has no Overview).
    (target_dir / "README.md").write_text(result.markdown)

    # Persist a minimal last_run.json for the Team section so future
    # refresh / compare modes can read it.
    last_run = {
        "config": asdict(config),
        "findings": [
            {
                "claim": f.claim,
                "value": f.value,
                "source": f.source,
                "source_kind": f.source_kind,
                "evidence_url": f.evidence_url,
                "evidence_date": f.evidence_date,
                "confidence": f.confidence,
            }
            for f in result.findings
        ],
        "verdicts": result.verdicts,
        "claims": result.claims,
    }
    (target_dir / "last_run.json").write_text(json.dumps(last_run, indent=2, default=str))

    print(f"=> target dir: {target_dir}")
    print("=> verdicts:")
    for claim, v in result.verdicts.items():
        print(f"     {v['tag']} {claim}")
        print(f"        — {v['rationale']}")
    print(f"=> manual review claims ({len(result.manual_review_claims)}):")
    for c in result.manual_review_claims:
        print(f"     - {c}")
    print()
    print("=> README.md preview:")
    print("---")
    print(result.markdown)
    print("---")


if __name__ == "__main__":
    main()

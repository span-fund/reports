"""Live HITL E2E runner for frax-com Phase 3 Overview.

Reads .env, instantiates the real Parallel SDK client, wraps it in the
ParallelClient protocol the orchestrator expects, and calls run_dd_new
with targets/frax-com/overview_claims.json.

Usage: uv run python scripts/run_frax_live.py
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from parallel import Parallel

from pipeline.orchestrator import run_dd_new
from pipeline.parallel_pricing import lookup_task_cost
from pipeline.wizard import TargetConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    path = REPO_ROOT / ".env"
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _http_get(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": "dd-research/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class ParallelAdapter:
    """Adapts the real `parallel` SDK to the narrow ParallelClient protocol
    the orchestrator / pipeline/parallel.py depends on.

    Cost accounting (issue #12)
    ---------------------------
    The parallel-web Python SDK does NOT expose billed cost on `TaskRun` or
    `TaskRunResult`. Verified against parallel-web/parallel-sdk-python:
    `TaskRun` fields are {created_at, modified_at, processor, run_id, status,
    metadata, warnings, interaction_id, task_group_id} — `metadata` is a
    user-supplied dict, not pricing. Only the beta `extract`/`search` endpoints
    carry a `usage: List[UsageItem]` list, and that reports SKU counts, not
    dollars.

    We therefore derive `cost_usd` from a local pricing table keyed by
    processor (`pipeline.parallel_pricing.lookup_task_cost`) and stamp the
    audit record with `cost_source="estimated"`. If/when the SDK starts to
    expose billed cost, swap in "actual" and the existing audit schema will
    continue to work unchanged.
    """

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
        # JSON output exposes .content; text output exposes .content too.
        content = getattr(output, "content", output)
        if isinstance(content, str):
            content = json.loads(content)
        return {
            "task_id": task.run_id,
            "cost_usd": cost_usd,
            "cost_source": cost_source,
            "output": content,
        }


def main() -> None:
    _load_env()

    # Load config.json written by Phase 1/2 wizard (already on disk for frax-com).
    config_path = REPO_ROOT / "targets" / "frax-com" / "config.json"
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

    manifest_path = REPO_ROOT / "targets" / "frax-com" / "overview_claims.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest missing: {manifest_path}")

    parallel_client = ParallelAdapter(Parallel(api_key=os.environ["PARALLEL_API_KEY"]))

    print(f"=> target: {config.slug} ({config.domain}), tier={config.tier}, cap=${config.soft_cap_usd}")
    print(f"=> manifest: {manifest_path}")

    result = run_dd_new(
        config=config,
        overview_claims_path=manifest_path,
        cost_preview_usd=2.0,  # conservative preview under $5 cap
        targets_root=REPO_ROOT / "targets",
        env=os.environ,
        parallel_client=parallel_client,
        http_get=_http_get,
    )

    print()
    print(f"=> section verdict: {result.verdict_tag}")
    print(f"=> target dir: {result.target_dir}")
    print(f"=> manual review claims ({len(result.manual_review_claims)}):")
    for c in result.manual_review_claims:
        print(f"     - {c}")
    if result.warnings:
        print(f"=> warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"     ! {w}")
    else:
        print("=> no warnings")


if __name__ == "__main__":
    main()

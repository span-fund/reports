"""Parallel.ai processor pricing lookup.

Background
----------
The Parallel Python SDK (parallel-web) does not expose billed cost on the
`TaskRun` or `TaskRunResult` models. Verified against the upstream SDK source
at parallel-web/parallel-sdk-python: `TaskRun` carries `metadata` (user
supplied), `status`, `run_id`, and timestamps — but no `cost`, `usage`, or
`billing` fields. Only the beta `extract` / `search` responses carry a
`usage: List[UsageItem]` list, and even that reports SKU counts, not dollars.

Because of that, we fall back to a local pricing table keyed by processor
name and tag the emitted cost with `cost_source="estimated"` so downstream
cost reports, soft caps, and quality gates can distinguish estimates from a
future "actual" path (if/when the SDK begins to expose billed cost).

Pricing source: https://docs.parallel.ai/getting-started/pricing (per 1K
Task Runs, converted to USD per task). `-fast` variants share the same
price as their base processor.
"""

from typing import Literal

CostSource = Literal["estimated", "unknown"]

PROCESSOR_PRICE_USD: dict[str, float] = {
    "lite": 0.005,
    "base": 0.010,
    "core": 0.025,
    "core2x": 0.050,
    "pro": 0.100,
    "ultra": 0.300,
    "ultra2x": 0.600,
    "ultra4x": 1.200,
    "ultra8x": 2.400,
}


def lookup_task_cost(processor: str) -> tuple[float, CostSource]:
    """Return (cost_usd, cost_source) for a single task run on `processor`.

    Known processors → (price, "estimated"). Unknown → (0.0, "unknown") so
    the caller can warn/flag without crashing the audit log. `-fast` variants
    share the price of their base processor.
    """
    base = processor[: -len("-fast")] if processor.endswith("-fast") else processor
    price = PROCESSOR_PRICE_USD.get(base)
    if price is None:
        return (0.0, "unknown")
    return (price, "estimated")

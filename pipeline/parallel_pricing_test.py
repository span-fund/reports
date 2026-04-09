"""Tests for the Parallel.ai processor pricing lookup.

The Parallel Python SDK does not expose billed cost on `TaskRun` or
`TaskRunResult` (verified against parallel-web/parallel-sdk-python). We
therefore fall back to a local pricing table keyed by processor name and
return an explicit `cost_source` so downstream cost reports can distinguish
estimated from actual cost.
"""

from pipeline.parallel_pricing import lookup_task_cost


def test_lookup_task_cost_lite_returns_estimated_price():
    cost, source = lookup_task_cost("lite")
    assert cost == 0.005
    assert source == "estimated"


def test_lookup_task_cost_covers_full_processor_ladder():
    # Prices pulled from docs.parallel.ai/getting-started/pricing (per task).
    expected = {
        "base": 0.010,
        "core": 0.025,
        "core2x": 0.050,
        "pro": 0.100,
        "ultra": 0.300,
        "ultra2x": 0.600,
        "ultra4x": 1.200,
        "ultra8x": 2.400,
    }
    for processor, price in expected.items():
        cost, source = lookup_task_cost(processor)
        assert cost == price, f"{processor} priced wrong"
        assert source == "estimated"


def test_lookup_task_cost_fast_suffix_resolves_to_base_price():
    # `-fast` variants are billed at the same rate as their base processor
    # (docs.parallel.ai/getting-started/pricing).
    assert lookup_task_cost("lite-fast") == (0.005, "estimated")
    assert lookup_task_cost("core-fast") == (0.025, "estimated")
    assert lookup_task_cost("ultra4x-fast") == (1.200, "estimated")


def test_lookup_task_cost_unknown_processor_is_flagged():
    # Unknown processors must not crash the pipeline — return 0.0 with an
    # explicit "unknown" source so downstream can warn but continue.
    cost, source = lookup_task_cost("imaginary-tier-9000")
    assert cost == 0.0
    assert source == "unknown"

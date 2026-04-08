"""Tests for cost-guard: pre-flight gate that aborts if Parallel preview > soft cap."""

import pytest

from pipeline.cost_guard import CostCapExceeded, check_cost


def test_preview_within_cap_passes():
    # Tier Lite, preview $1.20, soft cap $2 → pass.
    check_cost(preview_usd=1.20, soft_cap_usd=2.00)  # does not raise


def test_preview_over_cap_aborts_with_explicit_message():
    with pytest.raises(CostCapExceeded) as exc:
        check_cost(preview_usd=5.50, soft_cap_usd=2.00)

    msg = str(exc.value)
    assert "5.5" in msg
    assert "2.0" in msg
    assert "cap" in msg.lower()

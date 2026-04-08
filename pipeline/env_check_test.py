"""Tests for env-var fail-fast check.

The skill must verify PARALLEL_API_KEY and ETHERSCAN_API_KEY exist on startup
and fail cleanly with an explicit message if any are missing.
"""

import pytest

from pipeline.env_check import MissingEnvVars, require_env_vars


def test_all_required_vars_present_passes():
    env = {"PARALLEL_API_KEY": "p-xxx", "ETHERSCAN_API_KEY": "e-yyy", "HOME": "/tmp"}
    require_env_vars(env, ["PARALLEL_API_KEY", "ETHERSCAN_API_KEY"])


def test_missing_vars_raise_with_all_names_listed():
    env = {"ETHERSCAN_API_KEY": "e-yyy"}
    with pytest.raises(MissingEnvVars) as exc:
        require_env_vars(env, ["PARALLEL_API_KEY", "ETHERSCAN_API_KEY"])
    assert "PARALLEL_API_KEY" in str(exc.value)
    assert "ETHERSCAN_API_KEY" not in str(exc.value)


def test_empty_string_counts_as_missing():
    env = {"PARALLEL_API_KEY": "", "ETHERSCAN_API_KEY": "e-yyy"}
    with pytest.raises(MissingEnvVars, match="PARALLEL_API_KEY"):
        require_env_vars(env, ["PARALLEL_API_KEY", "ETHERSCAN_API_KEY"])

"""End-to-end test for the skill orchestrator: `run_dd_new`.

Mocks only at real system boundaries (Parallel SDK, HTTP for Etherscan). Real
filesystem via tmp_path, real verdict-engine, real renderer, real cache, real
audit log. This is the tracer bullet end-to-end proving all modules compose.
"""

import json

from pipeline.orchestrator import run_dd_new
from pipeline.parallel_test import FakeParallelClient
from pipeline.wizard import TargetConfig


def test_run_dd_new_produces_full_target_directory(tmp_path):
    config = TargetConfig(
        target_type="protocol",
        domain="ethena.fi",
        chain="ethereum",
        jurisdiction="us",
        tier="lite",
        soft_cap_usd=2.0,
        slug="ethena-fi",
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 0.42,
            "output": {
                "totalSupply": "1000000",
                "evidence_url": "https://ethena.fi/stats",
                "evidence_date": "2026-04-08",
            },
        }
    )

    def fake_http_get(url, params):
        return {"status": "1", "result": "1000000000000000000000000"}  # 1e24 raw

    env = {"PARALLEL_API_KEY": "p-xxx", "ETHERSCAN_API_KEY": "e-yyy"}

    result = run_dd_new(
        config=config,
        token_address="0xabc",
        token_decimals=18,
        cost_preview_usd=0.50,
        targets_root=tmp_path,
        env=env,
        parallel_client=parallel_client,
        http_get=fake_http_get,
    )

    target_dir = tmp_path / "ethena-fi"

    # All required artifacts present
    assert (target_dir / "config.json").exists()
    assert (target_dir / "last_run.json").exists()
    assert (target_dir / "parallel-runs.jsonl").exists()
    assert (target_dir / "README.md").exists()

    # Verdict is ✅ because Parallel and Etherscan agree on 1000000
    last_run = json.loads((target_dir / "last_run.json").read_text())
    assert last_run["verdicts"]["totalSupply"]["tag"] == "✅"

    # README renders both citations
    readme = (target_dir / "README.md").read_text()
    assert "✅" in readme
    assert "https://ethena.fi/stats" in readme
    assert "etherscan.io" in readme
    assert "1000000" in readme

    # Audit log has one line for the Parallel call
    audit_lines = (target_dir / "parallel-runs.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1
    assert json.loads(audit_lines[0])["task_id"] == "task-abc"

    # Config persisted
    saved_config = json.loads((target_dir / "config.json").read_text())
    assert saved_config["domain"] == "ethena.fi"
    assert saved_config["tier"] == "lite"

    # Return value is useful to the skill layer
    assert result.verdict_tag == "✅"
    assert result.target_dir == target_dir


def test_rerun_same_day_uses_parallel_cache(tmp_path):
    # Re-running the same DD the same day must NOT call Parallel again — the
    # cached response is served and no second audit line is appended.
    config = TargetConfig(
        target_type="protocol",
        domain="ethena.fi",
        chain="ethereum",
        jurisdiction="us",
        tier="lite",
        soft_cap_usd=2.0,
        slug="ethena-fi",
    )

    parallel_client = FakeParallelClient(
        response={
            "task_id": "task-abc",
            "cost_usd": 0.42,
            "output": {
                "totalSupply": "1000000",
                "evidence_url": "https://ethena.fi/stats",
                "evidence_date": "2026-04-08",
            },
        }
    )

    def fake_http_get(url, params):
        return {"status": "1", "result": "1000000000000000000000000"}

    env = {"PARALLEL_API_KEY": "p-xxx", "ETHERSCAN_API_KEY": "e-yyy"}

    kwargs = dict(
        config=config,
        token_address="0xabc",
        token_decimals=18,
        cost_preview_usd=0.50,
        targets_root=tmp_path,
        env=env,
        parallel_client=parallel_client,
        http_get=fake_http_get,
        cache_root=tmp_path / "_cache",
    )

    run_dd_new(**kwargs)
    assert len(parallel_client.calls) == 1

    run_dd_new(**kwargs)
    # Second run hit the cache — no new Parallel call.
    assert len(parallel_client.calls) == 1

    # Audit log still has a single line (cached calls are not re-audited).
    target_dir = tmp_path / "ethena-fi"
    audit_lines = (target_dir / "parallel-runs.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1

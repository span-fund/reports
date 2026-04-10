"""Tests for the generic section orchestrator (Phase 5).

The section orchestrator runs N generic sections (Mechanism, Collateral, etc.)
through the Parallel → verdict-engine → renderer pipeline. Each section gets
its own Parallel call. A failing section does not block others (graceful
degradation).
"""

import json
from pathlib import Path

from pipeline.cache import Cache
from pipeline.section_orchestrator import run_sections
from pipeline.wizard import TargetConfig


class FakeParallelClient:
    """Returns canned responses keyed by section name detected in the prompt."""

    def __init__(self, responses: dict[str, dict]):
        self._responses = responses
        self.calls: list[dict] = []

    def run_task(self, *, processor: str, schema: dict, prompt: str) -> dict:
        self.calls.append({"processor": processor, "schema": schema, "prompt": prompt})
        for section_name, response in self._responses.items():
            if section_name in prompt:
                return response
        raise RuntimeError(f"No canned response for prompt: {prompt[:80]}")


def _config() -> TargetConfig:
    return TargetConfig(
        target_type="protocol",
        domain="sky.money",
        chain="ethereum",
        jurisdiction="skip",
        tier="base",
        soft_cap_usd=5.0,
        slug="sky-protocol",
        confidence_threshold=0.7,
    )


def _write_manifest(tmp_path: Path, section: str, claims: list[dict]) -> Path:
    path = tmp_path / f"{section.lower().replace(' ', '_')}_claims.json"
    path.write_text(json.dumps({"section": section, "claims": claims}))
    return path


def test_run_sections_single_section_produces_markdown_and_verdicts(tmp_path: Path):
    manifest = _write_manifest(
        tmp_path,
        "Revenue",
        [
            {
                "name": "annual_revenue",
                "kind": "hard",
                "display_label": "Annualized revenue",
                "parallel_field": "annual_revenue",
            },
        ],
    )
    client = FakeParallelClient(
        {
            "Revenue": {
                "task_id": "t-rev-1",
                "cost_usd": 0.30,
                "output": {
                    "annual_revenue": {
                        "value": "$411M",
                        "evidence_url": "https://info.skyeco.com",
                        "evidence_date": "2026-04-10",
                        "confidence": 0.92,
                    },
                },
            },
        }
    )
    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400})

    results = run_sections(
        config=_config(),
        section_manifests=[manifest],
        parallel_client=client,
        cache=cache,
        target_dir=tmp_path / "sky-protocol",
    )

    assert len(results) == 1
    r = results[0]
    assert r.section_name == "Revenue"
    assert "Revenue" in r.markdown
    # STRICT policy: only 1 source (Parallel) → ❌ → lands in Pytania
    assert "Pytania do founders" in r.markdown
    assert len(r.findings) == 1
    assert r.findings[0].claim == "annual_revenue"
    assert "annual_revenue" in r.verdicts
    assert r.verdicts["annual_revenue"]["tag"] == "❌"


def test_run_sections_multiple_sections_each_get_own_parallel_call(tmp_path: Path):
    manifests = [
        _write_manifest(
            tmp_path,
            "Revenue",
            [
                {
                    "name": "annual_revenue",
                    "kind": "hard",
                    "display_label": "Revenue",
                    "parallel_field": "annual_revenue",
                },
            ],
        ),
        _write_manifest(
            tmp_path,
            "Governance",
            [
                {
                    "name": "governance_centralization",
                    "kind": "hard",
                    "display_label": "Gov centralization",
                    "parallel_field": "governance_centralization",
                },
            ],
        ),
    ]
    client = FakeParallelClient(
        {
            "Revenue": {
                "task_id": "t-rev",
                "cost_usd": 0.30,
                "output": {
                    "annual_revenue": {
                        "value": "$411M",
                        "evidence_url": "https://a",
                        "evidence_date": "2026-04-10",
                        "confidence": 0.9,
                    }
                },
            },
            "Governance": {
                "task_id": "t-gov",
                "cost_usd": 0.25,
                "output": {
                    "governance_centralization": {
                        "value": "S&P B-",
                        "evidence_url": "https://b",
                        "evidence_date": "2026-04-10",
                        "confidence": 0.88,
                    }
                },
            },
        }
    )
    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400})

    results = run_sections(
        config=_config(),
        section_manifests=manifests,
        parallel_client=client,
        cache=cache,
        target_dir=tmp_path / "sky-protocol",
    )

    assert len(results) == 2
    assert {r.section_name for r in results} == {"Revenue", "Governance"}
    # Each section triggers its own Parallel call
    assert len(client.calls) == 2


def test_run_sections_failed_section_does_not_block_others(tmp_path: Path):
    """Graceful degradation: if one section's Parallel call raises, the other
    sections still complete. The failed section returns an error result."""
    manifests = [
        _write_manifest(
            tmp_path,
            "Revenue",
            [
                {
                    "name": "annual_revenue",
                    "kind": "hard",
                    "display_label": "Revenue",
                    "parallel_field": "annual_revenue",
                },
            ],
        ),
        _write_manifest(
            tmp_path,
            "Mechanism",
            [
                {
                    "name": "mechanism_description",
                    "kind": "soft",
                    "display_label": "Mechanism",
                    "parallel_field": "mechanism_description",
                },
            ],
        ),
    ]
    # Only Revenue has a response — Mechanism will raise RuntimeError
    client = FakeParallelClient(
        {
            "Revenue": {
                "task_id": "t-rev",
                "cost_usd": 0.30,
                "output": {
                    "annual_revenue": {
                        "value": "$411M",
                        "evidence_url": "https://a",
                        "evidence_date": "2026-04-10",
                        "confidence": 0.9,
                    }
                },
            },
        }
    )
    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400})

    results = run_sections(
        config=_config(),
        section_manifests=manifests,
        parallel_client=client,
        cache=cache,
        target_dir=tmp_path / "sky-protocol",
    )

    assert len(results) == 2
    by_name = {r.section_name: r for r in results}
    # Revenue succeeded (STRICT ❌ with 1 source is expected, but no crash)
    assert by_name["Revenue"].error is None
    assert "Revenue" in by_name["Revenue"].markdown
    # Mechanism failed gracefully
    assert by_name["Mechanism"].error is not None
    assert by_name["Mechanism"].markdown == ""
    assert by_name["Mechanism"].findings == []


def test_run_sections_caches_parallel_results(tmp_path: Path):
    manifest = _write_manifest(
        tmp_path,
        "Revenue",
        [
            {
                "name": "annual_revenue",
                "kind": "hard",
                "display_label": "Revenue",
                "parallel_field": "annual_revenue",
            },
        ],
    )
    client = FakeParallelClient(
        {
            "Revenue": {
                "task_id": "t-rev",
                "cost_usd": 0.30,
                "output": {
                    "annual_revenue": {
                        "value": "$411M",
                        "evidence_url": "https://a",
                        "evidence_date": "2026-04-10",
                        "confidence": 0.9,
                    }
                },
            },
        }
    )
    cache = Cache(root=tmp_path / "_cache", ttls={"parallel": 7 * 86400})
    target_dir = tmp_path / "sky-protocol"

    # First run — hits Parallel
    run_sections(
        config=_config(),
        section_manifests=[manifest],
        parallel_client=client,
        cache=cache,
        target_dir=target_dir,
    )
    assert len(client.calls) == 1

    # Second run — cache hit, no new Parallel call
    run_sections(
        config=_config(),
        section_manifests=[manifest],
        parallel_client=client,
        cache=cache,
        target_dir=target_dir,
    )
    assert len(client.calls) == 1  # still 1

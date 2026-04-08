"""Tests for verdict-engine: the deep module that encodes STRICT cross-check policy.

Public interface under test: `decide(findings, claim) -> Verdict`.

Tests describe behaviour a user of the pipeline cares about — they should survive
internal refactors that rename modules, split files, or swap data structures.
"""

from pipeline.verdict_engine import Finding, decide


def test_agreeing_parallel_and_nonparallel_sources_yield_green_verdict():
    # Two independent sources agree on the same totalSupply value.
    # STRICT policy: >=2 sources, >=1 non-Parallel -> ✅.
    findings = [
        Finding(
            claim="totalSupply",
            value="1000000",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="totalSupply",
            value="1000000",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="totalSupply", findings=findings)

    assert verdict.tag == "✅"
    assert verdict.rationale  # non-empty human-readable reason


def test_conflicting_sources_yield_warning_verdict():
    # Parallel says one number, Etherscan says another — conflict.
    # STRICT policy: any disagreement -> ⚠️ regardless of confidence.
    findings = [
        Finding(
            claim="totalSupply",
            value="1000000",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="totalSupply",
            value="2500000",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="totalSupply", findings=findings)

    assert verdict.tag == "⚠️"
    assert "conflict" in verdict.rationale.lower()


def test_only_one_source_yields_red_verdict():
    # STRICT policy: need >=2 independent sources. One source alone -> ❌.
    # Models the "one verifier path crashed" case — caller omits the dead source.
    findings = [
        Finding(
            claim="totalSupply",
            value="1000000",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="totalSupply", findings=findings)

    assert verdict.tag == "❌"
    assert "source" in verdict.rationale.lower()


def test_two_parallel_sources_without_independent_verifier_yield_red():
    # STRICT policy: >=1 non-Parallel source required even if Parallel gives two
    # agreeing findings. Parallel can't cross-check itself.
    findings = [
        Finding(
            claim="totalSupply",
            value="1000000",
            source="parallel-task-1",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="totalSupply",
            value="1000000",
            source="parallel-task-2",
            source_kind="parallel",
            evidence_url="https://example.com/whitepaper",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="totalSupply", findings=findings)

    assert verdict.tag == "❌"
    assert "non-parallel" in verdict.rationale.lower()


def test_hard_claim_always_requires_manual_review_even_when_sources_agree():
    # Hard claims (numbers, ownership, regulatory) are the invest-decision
    # drivers. Even a clean ✅ with high Parallel confidence must go through
    # human review before the DD is trusted.
    findings = [
        Finding(
            claim="totalSupply",
            value="1000000",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
            confidence=0.95,
        ),
        Finding(
            claim="totalSupply",
            value="1000000",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="totalSupply", findings=findings, kind="hard")

    assert verdict.tag == "✅"
    assert verdict.requires_manual_review is True


def test_soft_claim_with_high_confidence_and_strict_pass_auto_greens():
    # Soft ✅ + Parallel confidence above threshold -> analyst can skip review.
    findings = [
        Finding(
            claim="mechanism_summary",
            value="yield-bearing stablecoin backed by delta-neutral strategy",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
            confidence=0.9,
        ),
        Finding(
            claim="mechanism_summary",
            value="yield-bearing stablecoin backed by delta-neutral strategy",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(
        claim="mechanism_summary",
        findings=findings,
        kind="soft",
        confidence_threshold=0.7,
    )

    assert verdict.tag == "✅"
    assert verdict.requires_manual_review is False


def test_soft_claim_with_low_confidence_still_requires_manual_review():
    # Clean STRICT ✅ but Parallel confidence is below threshold — analyst
    # should take a second look even though the tag is green.
    findings = [
        Finding(
            claim="mechanism_summary",
            value="yield-bearing stablecoin",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
            confidence=0.4,
        ),
        Finding(
            claim="mechanism_summary",
            value="yield-bearing stablecoin",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(
        claim="mechanism_summary",
        findings=findings,
        kind="soft",
        confidence_threshold=0.7,
    )

    assert verdict.tag == "✅"
    assert verdict.requires_manual_review is True

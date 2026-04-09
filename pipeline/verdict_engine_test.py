"""Tests for verdict-engine: the deep module that encodes STRICT cross-check policy.

Public interface under test: `decide(findings, claim) -> Verdict`.

Tests describe behaviour a user of the pipeline cares about — they should survive
internal refactors that rename modules, split files, or swap data structures.
"""

from pipeline.verdict_engine import Finding, _normalize_numeric, decide


def _legal_finding(claim: str, value: str) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source="krs",
        source_kind="legal",
        evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0000123456",
        evidence_date="2026-04-09",
    )


def _parallel_finding(claim: str, value: str, confidence: float = 0.95) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source="parallel",
        source_kind="parallel",
        evidence_url="https://example.com/about",
        evidence_date="2026-04-09",
        confidence=confidence,
    )


def _onchain_finding(claim: str, value: str) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source="etherscan",
        source_kind="onchain",
        evidence_url="https://etherscan.io/address/0xabc",
        evidence_date="2026-04-09",
    )


def test_requires_legal_yields_warning_when_no_legal_source_present():
    """Ownership claims must be cross-checked against a registry. Even with a
    clean parallel+onchain agreement, missing legal source must downgrade
    the verdict to ⚠️ so the analyst sees the open question."""
    findings = [
        _parallel_finding("owner:Anna Nowak", "50%"),
        _onchain_finding("owner:Anna Nowak", "50%"),
    ]
    verdict = decide(
        claim="owner:Anna Nowak",
        findings=findings,
        kind="hard",
        requires_legal=True,
    )
    assert verdict.tag == "⚠️"
    assert "registry" in verdict.rationale.lower()
    assert verdict.requires_manual_review is True


def test_requires_legal_passes_when_legal_source_confirms():
    findings = [
        _parallel_finding("officer:Jan Kowalski", "Prezes Zarządu"),
        _legal_finding("officer:Jan Kowalski", "Prezes Zarządu"),
    ]
    verdict = decide(
        claim="officer:Jan Kowalski",
        findings=findings,
        kind="hard",
        requires_legal=True,
    )
    assert verdict.tag == "✅"
    # Hard claim still flips manual_review on regardless
    assert verdict.requires_manual_review is True


def test_requires_legal_default_false_preserves_existing_behaviour():
    """Existing Overview claims (totalSupply etc.) must keep working — the
    new flag defaults to off and parallel+onchain alone still passes."""
    findings = [
        _parallel_finding("totalSupply", "1000000"),
        _onchain_finding("totalSupply", "1000000"),
    ]
    verdict = decide(claim="totalSupply", findings=findings, kind="hard")
    assert verdict.tag == "✅"


def test_normalize_parses_million_suffix():
    # Parallel returns "130 Million FRXUSD" while on-chain gives raw int.
    # Normalizer must strip the token symbol and expand the Million suffix.
    assert _normalize_numeric("130 Million FRXUSD") == 130_000_000


def test_normalize_parses_decimal_m_suffix():
    # Short form "33.26M" — decimal times million, token symbol tacked on.
    assert _normalize_numeric("33.26M SFRXUSD") == 33_260_000


def test_normalize_parses_dollar_and_commas():
    # Parallel frequently formats dollar totals with $ prefix and thousand-commas.
    assert _normalize_numeric("$12,028,517") == 12_028_517


def test_normalize_parses_plain_integer():
    # On-chain fetchers return raw scaled integers — must round-trip unchanged.
    assert _normalize_numeric("118645616") == 118_645_616


def test_normalize_parses_all_scale_suffixes():
    # Full suffix alphabet: thousand / billion / trillion.
    assert _normalize_numeric("500k") == 500_000
    assert _normalize_numeric("2.5B") == 2_500_000_000
    assert _normalize_numeric("1T") == 1_000_000_000_000
    assert _normalize_numeric("3 billion") == 3_000_000_000
    assert _normalize_numeric("1.2 trillion") == 1_200_000_000_000


def test_normalize_returns_none_for_missing_values():
    # Parallel returns "Not found" when it can't locate a figure; fetchers may
    # return empty strings. These must surface as None, not accidentally parse
    # into noise digits.
    assert _normalize_numeric("Not found") is None
    assert _normalize_numeric("") is None
    assert _normalize_numeric("N/A") is None
    assert _normalize_numeric("none") is None


def test_normalize_returns_none_for_non_numeric_prose():
    # Soft claims ("mechanism_summary") must not accidentally parse to an int
    # — the normalizer falls back to None so string equality takes over.
    assert _normalize_numeric("yield-bearing stablecoin") is None


def test_numeric_claims_within_tolerance_yield_green_verdict():
    # The frax-com live-run scenario: Parallel returns a formatted phrase,
    # on-chain returns a raw int. They agree within the default 2% tolerance
    # and should yield ✅ instead of the old string-equality ⚠️.
    findings = [
        Finding(
            claim="frxusd_supply",
            value="130 Million FRXUSD",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
            confidence=0.9,
        ),
        Finding(
            claim="frxusd_supply",
            value="129500000",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="frxusd_supply", findings=findings, kind="hard")

    assert verdict.tag == "✅"
    # Hard claim → manual review stays True regardless.
    assert verdict.requires_manual_review is True


def test_numeric_claims_outside_tolerance_yield_warning():
    # Inject a 20% delta — well outside the default 2% tolerance. ⚠️ must still
    # fire so real disagreements are not swallowed by the normalizer.
    findings = [
        Finding(
            claim="frxusd_supply",
            value="130 Million FRXUSD",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="frxusd_supply",
            value="104000000",  # 20% lower
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="frxusd_supply", findings=findings, kind="hard")

    assert verdict.tag == "⚠️"
    assert "conflict" in verdict.rationale.lower()


def test_parallel_not_found_on_hard_claim_yields_red_not_warning():
    # Parallel returning "Not found" is a MISSING value, not a conflicting
    # one. Must surface as ❌ ("source could not provide value"), not ⚠️.
    findings = [
        Finding(
            claim="fxs_supply",
            value="Not found",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="fxs_supply",
            value="99681495",
            source="etherscan",
            source_kind="onchain",
            evidence_url="https://etherscan.io/token/0xabc",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="fxs_supply", findings=findings, kind="hard")

    assert verdict.tag == "❌"
    assert "no value" in verdict.rationale.lower()


def test_numeric_tolerance_parameter_is_configurable():
    # 5% delta: default 2% tolerance → ⚠️, caller-supplied 10% tolerance → ✅.
    # Lets callers relax the threshold for noisy metrics (e.g. floating TVL).
    findings = [
        Finding(
            claim="tvl_usd",
            value="100000000",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="tvl_usd",
            value="95000000",  # 5% below
            source="defillama",
            source_kind="onchain",
            evidence_url="https://defillama.com/x",
            evidence_date="2026-04-08",
        ),
    ]

    assert decide(claim="tvl_usd", findings=findings).tag == "⚠️"
    assert decide(claim="tvl_usd", findings=findings, numeric_tolerance=0.10).tag == "✅"


def test_non_numeric_soft_claim_falls_back_to_string_equality():
    # Prose claims with different wording must still conflict — tolerance
    # logic only kicks in when BOTH values parse to numbers.
    findings = [
        Finding(
            claim="mechanism_summary",
            value="yield-bearing stablecoin backed by delta-neutral strategy",
            source="parallel",
            source_kind="parallel",
            evidence_url="https://example.com/docs",
            evidence_date="2026-04-08",
        ),
        Finding(
            claim="mechanism_summary",
            value="algorithmic rebase token",
            source="browser",
            source_kind="browser",
            evidence_url="https://example.com/blog",
            evidence_date="2026-04-08",
        ),
    ]

    verdict = decide(claim="mechanism_summary", findings=findings)

    assert verdict.tag == "⚠️"
    assert "conflict" in verdict.rationale.lower()


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

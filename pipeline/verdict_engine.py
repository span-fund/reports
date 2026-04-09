"""Verdict engine: encodes STRICT cross-check policy + hard/soft taxonomy.

Takes a set of findings (one per source) for a single claim, the claim's kind
(hard or soft — from claim_classifier) and a confidence threshold, and returns
a verdict tag (✅⚠️❌🔄) + rationale + requires_manual_review flag.

Policy:
- STRICT cross-check: >=2 sources total, >=1 non-Parallel. Conflict -> ⚠️.
  Fewer sources or all-Parallel -> ❌.
- Hard claims ALWAYS require manual review regardless of outcome — Parallel
  confidence is a signal, never a shortcut.
- Soft claims with a clean ✅ can auto-pass only when Parallel confidence
  clears the threshold. Missing/low confidence -> manual review flagged even
  though the tag stays ✅.
- Any non-✅ tag also requires manual review (something is wrong).
"""

import re
from dataclasses import dataclass

_MISSING_TOKENS = {"", "not found", "n/a", "none"}
_SCALE = {
    "k": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "billion": 1_000_000_000,
    "t": 1_000_000_000_000,
    "trillion": 1_000_000_000_000,
}
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(trillion|billion|million|k|m|b|t)?", re.IGNORECASE)


def _missing_value(value: str) -> bool:
    return value.strip().lower() in _MISSING_TOKENS


def _canonical(value: str) -> str:
    """Case-folded, whitespace-collapsed canonical form for comparison.
    Used in the non-numeric string-equality fallback so e.g. KRS uppercase
    "PREZES ZARZĄDU" and Parallel mixed-case "Prezes Zarządu" don't trigger
    a spurious cross-check conflict."""
    return " ".join(value.casefold().split())


def _all_numeric(findings: "list[Finding]") -> list[int] | None:
    """Return normalized ints if EVERY finding parses numerically, else None."""
    normalized = [_normalize_numeric(f.value) for f in findings]
    if any(n is None for n in normalized):
        return None
    return [n for n in normalized if n is not None]


def _normalize_numeric(value: str) -> int | None:
    """Parse a formatted numeric string into a raw int.

    Handles: plain ints, decimals, scale suffixes (k/M/B/T + long forms),
    dollar/comma formatting, and trailing token tickers (ignored by the
    regex, so listing every symbol is unnecessary). Returns None for
    missing markers ("Not found", "", "N/A") and non-numeric prose so the
    caller can fall back to string equality.
    """
    s = value.strip().lower()
    if s in _MISSING_TOKENS:
        return None
    s = s.replace("$", "").replace(",", "")
    match = _NUM_RE.search(s)
    if not match:
        return None
    num = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    return int(round(num * _SCALE.get(suffix, 1)))


@dataclass(frozen=True)
class Finding:
    claim: str
    value: str
    source: str
    source_kind: str  # "parallel" | "onchain" | "legal" | "browser" | ...
    evidence_url: str
    evidence_date: str
    confidence: float | None = None  # populated by Parallel; None for other sources


@dataclass(frozen=True)
class Verdict:
    tag: str  # "✅" | "⚠️" | "❌" | "🔄"
    rationale: str
    requires_manual_review: bool = True


def decide(
    *,
    claim: str,
    findings: list[Finding],
    kind: str = "soft",
    confidence_threshold: float = 0.7,
    numeric_tolerance: float = 0.02,
    requires_legal: bool = False,
) -> Verdict:
    tag, rationale = _strict_tag(claim, findings, numeric_tolerance)
    # Ownership / officer claims must be confirmed by a legal registry. Even
    # a clean parallel+onchain ✅ gets downgraded to ⚠️ when no source carries
    # source_kind="legal" — the analyst needs to see the open question
    # explicitly (Czarnecki lesson: registry-confirmed names changed silently
    # while public sources still claimed the old composition).
    if requires_legal and findings and not any(f.source_kind == "legal" for f in findings):
        # The actionable framing for an analyst is "registry didn't confirm
        # this name", regardless of whether STRICT would otherwise have said
        # ✅ (parallel + onchain agreed) or ❌ (parallel only). Both collapse
        # to ⚠️ + the same "no registry confirmation" rationale so the
        # follow-up is consistent — go check KRS / OpenCorporates.
        tag = "⚠️"
        rationale = (
            f"no registry confirmation for {claim}: legal verifier required "
            "but no source_kind=legal finding present"
        )
    requires_review = _needs_manual_review(
        tag=tag,
        kind=kind,
        findings=findings,
        threshold=confidence_threshold,
    )
    return Verdict(tag=tag, rationale=rationale, requires_manual_review=requires_review)


def _strict_tag(claim: str, findings: list[Finding], numeric_tolerance: float) -> tuple[str, str]:
    if len(findings) < 2:
        return (
            "❌",
            f"insufficient sources for {claim}: got {len(findings)}, need >=2",
        )
    if all(f.source_kind == "parallel" for f in findings):
        return (
            "❌",
            (
                f"no non-Parallel verifier for {claim}: STRICT policy requires "
                ">=1 independent non-Parallel source"
            ),
        )
    # Parallel with "Not found" / empty is a missing value, not a conflict.
    if any(f.source_kind == "parallel" and _missing_value(f.value) for f in findings):
        return (
            "❌",
            f"parallel source returned no value for {claim}",
        )
    # Numeric path: if every finding parses to an int, compare with tolerance.
    nums = _all_numeric(findings)
    if nums is not None:
        max_val = max(abs(n) for n in nums)
        min_val = min(abs(n) for n in nums)
        spread = (max_val - min_val) / max_val if max_val > 0 else 0.0
        if spread < numeric_tolerance:
            return (
                "✅",
                f"{len(findings)} sources agree on {claim}≈{max_val} "
                f"(spread {spread:.2%} < tol {numeric_tolerance:.2%})",
            )
        return (
            "⚠️",
            f"conflict on {claim}: sources disagree ({sorted(f.value for f in findings)})",
        )
    # Fallback: case-folded, whitespace-collapsed string equality for
    # non-numeric claims. KRS returns roles in upper case ("PREZES ZARZĄDU")
    # while Parallel typically returns mixed case ("Prezes Zarządu") — both
    # are the same fact and shouldn't trigger a conflict. We compare the
    # canonical form but report the original strings in the rationale so
    # the analyst still sees the raw values.
    canonical = {_canonical(f.value) for f in findings}
    if len(canonical) > 1:
        return (
            "⚠️",
            f"conflict on {claim}: sources disagree ({sorted(f.value for f in findings)})",
        )
    values = {f.value for f in findings}
    return (
        "✅",
        f"{len(findings)} sources agree on {claim}={next(iter(values))}",
    )


def _needs_manual_review(
    *,
    tag: str,
    kind: str,
    findings: list[Finding],
    threshold: float,
) -> bool:
    # Hard claims always go through review.
    if kind == "hard":
        return True
    # Anything other than a clean ✅ needs human eyes.
    if tag != "✅":
        return True
    # Soft ✅ auto-passes only when Parallel confidence clears threshold.
    parallel_confidences = [
        f.confidence for f in findings if f.source_kind == "parallel" and f.confidence is not None
    ]
    if not parallel_confidences:
        return True
    return max(parallel_confidences) < threshold

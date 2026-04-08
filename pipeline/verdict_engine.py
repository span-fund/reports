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

from dataclasses import dataclass


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
) -> Verdict:
    tag, rationale = _strict_tag(claim, findings)
    requires_review = _needs_manual_review(
        tag=tag,
        kind=kind,
        findings=findings,
        threshold=confidence_threshold,
    )
    return Verdict(tag=tag, rationale=rationale, requires_manual_review=requires_review)


def _strict_tag(claim: str, findings: list[Finding]) -> tuple[str, str]:
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
    values = {f.value for f in findings}
    if len(values) > 1:
        return (
            "⚠️",
            f"conflict on {claim}: sources disagree ({sorted(values)})",
        )
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

"""Verdict engine: encodes STRICT cross-check policy.

Takes a set of findings (one per source) for a single claim and returns a verdict
tag (✅⚠️❌🔄) with a human-readable rationale. This is the single place where
cross-check policy lives.
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


@dataclass(frozen=True)
class Verdict:
    tag: str  # "✅" | "⚠️" | "❌" | "🔄"
    rationale: str


def decide(claim: str, findings: list[Finding]) -> Verdict:
    if len(findings) < 2:
        return Verdict(
            tag="❌",
            rationale=f"insufficient sources for {claim}: got {len(findings)}, need >=2",
        )
    if all(f.source_kind == "parallel" for f in findings):
        return Verdict(
            tag="❌",
            rationale=(
                f"no non-Parallel verifier for {claim}: STRICT policy requires "
                ">=1 independent non-Parallel source"
            ),
        )
    values = {f.value for f in findings}
    if len(values) > 1:
        return Verdict(
            tag="⚠️",
            rationale=f"conflict on {claim}: sources disagree ({sorted(values)})",
        )
    return Verdict(
        tag="✅",
        rationale=f"{len(findings)} sources agree on {claim}={next(iter(values))}",
    )

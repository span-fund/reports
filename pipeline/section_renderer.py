"""Section renderers: take a section JSON (claims + verdicts + findings) and
produce markdown. Overview matches sky-protocol/README.md layout: a metrics
table with one row per cross-checked claim, plus a `## Pytania do founders`
section aggregating any ❌ claims so the report still renders when a verifier
is broken.
"""

from typing import Any


def render_overview(section: dict[str, Any]) -> str:
    target = section["target_name"]
    passed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for claim in section["claims"]:
        if claim["verdict"].tag == "❌":
            failed.append(claim)
        else:
            passed.append(claim)

    lines: list[str] = [f"# Overview — {target}", ""]

    if passed:
        lines.append("| Metric | Value | Source |")
        lines.append("|---|---|---|")
        for claim in passed:
            lines.append(_render_metric_row(claim))
        lines.append("")

    if failed:
        lines.append("## Pytania do founders")
        lines.append("")
        for claim in failed:
            label = claim.get("display_label") or claim["name"]
            rationale = claim["verdict"].rationale
            lines.append(f"- **{label}** {claim['verdict'].tag} — {rationale}")
        lines.append("")

    return "\n".join(lines)


def _render_metric_row(claim: dict[str, Any]) -> str:
    label = claim.get("display_label") or claim["name"]
    verdict = claim["verdict"]
    marker = " [MANUAL REVIEW NEEDED]" if verdict.requires_manual_review else ""
    value = claim["findings"][0].value
    sources = ", ".join(
        f"[{f.source}]({f.evidence_url}) {f.evidence_date}" for f in claim["findings"]
    )
    metric_cell = f"{label} {verdict.tag}{marker}".strip()
    return f"| {metric_cell} | {value} | {sources} |"

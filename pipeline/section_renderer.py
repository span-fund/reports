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


def render_team(section: dict[str, Any]) -> str:
    """Render the Team section: Zarząd / Wspólnicy / generic team subsections,
    plus an Open questions block for ⚠️ claims and Pytania do founders for
    anything that needs human attention (⚠️ or ❌).

    Officers and owners are recognised by a `claim["name"]` prefix
    (`officer:` / `owner:`) — that's the contract the legal adapters and the
    orchestrator agree on. Anything else falls into the generic team bucket.
    """
    target = section["target_name"]
    officers: list[dict[str, Any]] = []
    owners: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for claim in section["claims"]:
        verdict = claim["verdict"]
        if verdict.tag == "❌":
            failed.append(claim)
            continue
        if verdict.tag == "⚠️":
            warnings.append(claim)
        name = claim["name"]
        if name.startswith("officer:"):
            officers.append(claim)
        elif name.startswith("owner:"):
            owners.append(claim)
        else:
            others.append(claim)

    lines: list[str] = [f"# Team — {target}", ""]

    if officers:
        lines.append("## Zarząd")
        lines.append("")
        for c in officers:
            lines.append(_render_team_bullet(c))
        lines.append("")
    if owners:
        lines.append("## Wspólnicy")
        lines.append("")
        for c in owners:
            lines.append(_render_team_bullet(c))
        lines.append("")
    if others:
        lines.append("## Team")
        lines.append("")
        for c in others:
            lines.append(_render_team_bullet(c))
        lines.append("")

    if warnings:
        lines.append("## Open questions")
        lines.append("")
        for c in warnings:
            label = c.get("display_label") or c["name"]
            lines.append(f"- **{label}** {c['verdict'].tag} — {c['verdict'].rationale}")
        lines.append("")

    # Pytania do founders aggregates ⚠️ + ❌ — anything an analyst must
    # follow up on with the team. Even ⚠️ ownership claims show up here so
    # the founders meeting checklist is complete in one place.
    pytania = warnings + failed
    if pytania:
        lines.append("## Pytania do founders")
        lines.append("")
        for c in pytania:
            label = c.get("display_label") or c["name"]
            lines.append(f"- **{label}** {c['verdict'].tag} — {c['verdict'].rationale}")
        lines.append("")

    return "\n".join(lines)


def _render_team_bullet(claim: dict[str, Any]) -> str:
    label = claim.get("display_label") or claim["name"]
    verdict = claim["verdict"]
    marker = " [MANUAL REVIEW NEEDED]" if verdict.requires_manual_review else ""
    findings = claim.get("findings") or []
    value = findings[0].value if findings else ""
    sources = ", ".join(f"[{f.source}]({f.evidence_url}) {f.evidence_date}" for f in findings)
    parts = [f"- **{label}** {verdict.tag}{marker}"]
    if value:
        parts.append(f"— {value}")
    if sources:
        parts.append(f"({sources})")
    return " ".join(parts)


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

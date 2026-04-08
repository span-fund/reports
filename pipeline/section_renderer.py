"""Section renderers: take a section JSON (claims + verdicts + findings) and
produce markdown. One renderer per section; Overview is the MVP tracer.
"""

from typing import Any


def render_overview(section: dict[str, Any]) -> str:
    lines: list[str] = [f"# Overview — {section['target_name']}", ""]
    for claim in section["claims"]:
        verdict = claim["verdict"]
        marker = " [MANUAL REVIEW NEEDED]" if verdict.requires_manual_review else ""
        lines.append(f"## {claim['name']} {verdict.tag}{marker}")
        lines.append("")
        # One canonical value (findings agree when verdict is ✅; otherwise still
        # show whatever each source reported so the conflict is auditable).
        first_value = claim["findings"][0].value
        lines.append(f"- **Value**: {first_value}")
        lines.append(f"- **Verdict rationale**: {verdict.rationale}")
        lines.append("")
        lines.append("### Sources")
        for f in claim["findings"]:
            lines.append(
                f"- [{f.source} ({f.source_kind})]({f.evidence_url}) — "
                f"{f.value} ({f.evidence_date})"
            )
        lines.append("")
    return "\n".join(lines)

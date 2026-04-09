"""OpenCorporates adapter — global fallback registry.

OpenCorporates aggregates company-registry data across jurisdictions, so it
covers everything KRS doesn't. Requires an API token (free tier is rate-limited
but enough for DD volume). HTTP is injected so tests mock at the boundary.

Returns one Finding per officer, source_kind="legal" — verdict-engine treats
KRS and OpenCorporates uniformly under the legal tag, the only thing the
caller cares about is that *some* registry confirmed the name.
"""

from collections.abc import Callable
from datetime import date

from pipeline.verdict_engine import Finding

OPENCORPORATES_ENDPOINT = "https://api.opencorporates.com/v0.4/companies"


def fetch_legal_findings_opencorporates(
    *,
    jurisdiction_code: str,
    company_number: str,
    api_key: str,
    http_get: Callable[[str, dict], dict],
) -> list[Finding]:
    url = f"{OPENCORPORATES_ENDPOINT}/{jurisdiction_code}/{company_number}"
    response = http_get(url, {"api_token": api_key})
    company = response.get("results", {}).get("company", {})
    evidence_url = company.get(
        "opencorporates_url",
        f"https://opencorporates.com/companies/{jurisdiction_code}/{company_number}",
    )
    today = date.today().isoformat()

    findings: list[Finding] = []
    for entry in company.get("officers") or []:
        officer = entry.get("officer") or {}
        name = (officer.get("name") or "").strip()
        position = (officer.get("position") or "").strip()
        if not name:
            continue
        findings.append(
            Finding(
                claim=f"officer:{name}",
                value=position,
                source="opencorporates",
                source_kind="legal",
                evidence_url=evidence_url,
                evidence_date=today,
            )
        )
    return findings

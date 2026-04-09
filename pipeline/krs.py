"""KRS (Krajowy Rejestr Sądowy) adapter — public PL company registry.

The Ministerstwo Sprawiedliwości serves Odpis Aktualny payloads as JSON over
HTTPS without an API key. We hit the official endpoint, parse the relevant
slices (zarząd from dział 2, wspólnicy from dział 1), and emit one Finding
per person so verdict-engine can cross-check each name independently against
Parallel's research output.

Findings carry source_kind="legal", which the verdict engine treats as a
non-Parallel source — pairing a Parallel "team" finding with a KRS officer
finding satisfies STRICT cross-check policy for hard ownership claims.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from pipeline.verdict_engine import Finding

KRS_ENDPOINT = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny"


def fetch_legal_findings_krs(
    *,
    krs_number: str,
    http_get: Callable[[str, dict], dict],
) -> list[Finding]:
    url = f"{KRS_ENDPOINT}/{krs_number}"
    params = {"rejestr": "P", "format": "json"}
    response = http_get(url, params)
    odpis = response.get("odpis", {})
    dane = odpis.get("dane", {})
    today = date.today().isoformat()
    evidence_url = f"https://wyszukiwarka-krs.ms.gov.pl/details?krs={krs_number}"

    findings: list[Finding] = []
    findings.extend(_parse_officers(dane, evidence_url, today))
    findings.extend(_parse_owners(dane, evidence_url, today))
    return findings


def _full_name(person: dict[str, Any]) -> str:
    surname = person.get("nazwisko", "").strip()
    imiona = person.get("imiona") or {}
    given = (imiona.get("imie") or "").strip()
    return f"{given} {surname}".strip()


def _parse_officers(dane: dict[str, Any], evidence_url: str, today: str) -> list[Finding]:
    sklad = dane.get("dzial2", {}).get("reprezentacja", {}).get("sklad") or []
    out: list[Finding] = []
    for member in sklad:
        name = _full_name(member)
        role = (member.get("funkcjaWOrganie") or "").strip()
        out.append(
            Finding(
                claim=f"officer:{name}",
                value=role,
                source="krs",
                source_kind="legal",
                evidence_url=evidence_url,
                evidence_date=today,
            )
        )
    return out


def _parse_owners(dane: dict[str, Any], evidence_url: str, today: str) -> list[Finding]:
    wspolnicy = dane.get("dzial1", {}).get("wspolnicy") or []
    out: list[Finding] = []
    for owner in wspolnicy:
        name = _full_name(owner)
        udzialy = owner.get("udzialy") or {}
        liczba = str(udzialy.get("liczba", "")).strip()
        wartosc = str(udzialy.get("wartosc", "")).strip()
        # Encode both count and value so verdict-engine can string-compare;
        # downstream renderers can split on the separator if needed.
        value = f"{liczba} udziałów / {wartosc}" if wartosc else f"{liczba} udziałów"
        out.append(
            Finding(
                claim=f"owner:{name}",
                value=value,
                source="krs",
                source_kind="legal",
                evidence_url=evidence_url,
                evidence_date=today,
            )
        )
    return out

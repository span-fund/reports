"""KRS (Krajowy Rejestr Sądowy) adapter — public PL company registry.

The Ministerstwo Sprawiedliwości serves Odpis Aktualny payloads as JSON
over HTTPS without an API key, BUT the public endpoint redacts personal
data: every officer/owner comes back with names like "P****" / "S*****"
and a masked PESEL. The adapter therefore cannot emit ready-to-cross-
check `Finding` objects keyed by full name. It collects the structural
data into `MaskedPerson` candidates and lets the downstream
`legal_matching.match_candidates` step bind candidates to parallel
findings whose full names are compatible with the masks.

Findings produced by the matcher carry source_kind="legal", which the
verdict engine treats as a non-Parallel source — pairing a Parallel
"team" finding with a KRS-bound legal finding satisfies the strict
cross-check policy for hard ownership claims.

Real KRS JSON shape (verified against KRS 0001174918 = STABLEWATCH SP. Z O.O.):
- Shareholders live under `dzial1.wspolnicySpzoo` (NOT `dzial1.wspolnicy`)
- Each person's surname is nested: `nazwisko.nazwiskoICzlon`
- Given names: `imiona.imie` + `imiona.imieDrugie`
- Shares are a single Polish string: `posiadaneUdzialy`
  e.g. "380 UDZIAŁÓW O ŁĄCZNEJ WARTOŚCI 19 000,00 ZŁ"
- Board members live at `dzial2.reprezentacja.sklad` with `funkcjaWOrganie`
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from pipeline.legal_matching import LegalRegistryResult, MaskedPerson

KRS_ENDPOINT = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny"


def fetch_legal_findings_krs(
    *,
    krs_number: str,
    http_get: Callable[[str, dict], dict],
) -> LegalRegistryResult:
    url = f"{KRS_ENDPOINT}/{krs_number}"
    params = {"rejestr": "P", "format": "json"}
    response = http_get(url, params)
    odpis = response.get("odpis", {})
    dane = odpis.get("dane", {})
    today = date.today().isoformat()
    evidence_url = f"https://wyszukiwarka-krs.ms.gov.pl/details?krs={krs_number}"

    candidates: list[MaskedPerson] = []
    candidates.extend(_parse_officers(dane, evidence_url, today))
    candidates.extend(_parse_owners(dane, evidence_url, today))
    return LegalRegistryResult(findings=[], candidates=candidates)


def _given_names(person: dict[str, Any]) -> list[str]:
    imiona = person.get("imiona") or {}
    out: list[str] = []
    for key in ("imie", "imieDrugie"):
        v = imiona.get(key)
        if v:
            out.append(v.strip())
    return out


def _surname_mask(person: dict[str, Any]) -> str:
    nazwisko = person.get("nazwisko") or {}
    return (nazwisko.get("nazwiskoICzlon") or "").strip()


def _parse_officers(dane: dict[str, Any], evidence_url: str, today: str) -> list[MaskedPerson]:
    sklad = dane.get("dzial2", {}).get("reprezentacja", {}).get("sklad") or []
    out: list[MaskedPerson] = []
    for member in sklad:
        out.append(
            MaskedPerson(
                surname_mask=_surname_mask(member),
                given_names_mask=_given_names(member),
                evidence_url=evidence_url,
                evidence_date=today,
                role=(member.get("funkcjaWOrganie") or "").strip() or None,
            )
        )
    return out


def _parse_owners(dane: dict[str, Any], evidence_url: str, today: str) -> list[MaskedPerson]:
    wspolnicy = dane.get("dzial1", {}).get("wspolnicySpzoo") or []
    out: list[MaskedPerson] = []
    for owner in wspolnicy:
        shares = (owner.get("posiadaneUdzialy") or "").strip() or None
        out.append(
            MaskedPerson(
                surname_mask=_surname_mask(owner),
                given_names_mask=_given_names(owner),
                evidence_url=evidence_url,
                evidence_date=today,
                shares_text=shares,
            )
        )
    return out

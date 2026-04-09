"""Legal-registry matching: bind PII-masked candidates to parallel claims.

The Polish KRS public JSON endpoint redacts personal data — every name
comes back as a mask string like "P****" / "S*****" — so the KRS adapter
cannot produce ready-to-cross-check `Finding` objects keyed by full
name. Instead it emits `MaskedPerson` candidates carrying the structural
clues (initial letter, mask length, role, share text) and a downstream
matching step rebinds candidates to parallel findings whose full names
are compatible with the masks.

OpenCorporates and other unmasked sources skip the matching step
entirely — they go directly into `LegalRegistryResult.findings`.

Both flows funnel into the same `LegalRegistryResult` so the orchestrator
treats every legal source uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.verdict_engine import Finding


@dataclass(frozen=True)
class MaskedPerson:
    surname_mask: str
    given_names_mask: list[str]
    evidence_url: str
    evidence_date: str
    role: str | None = None  # populated for board members
    shares_text: str | None = None  # populated for shareholders


@dataclass(frozen=True)
class LegalRegistryResult:
    """Carries both already-bound findings (e.g. OpenCorporates with full
    names) and PII-masked candidates (e.g. KRS public JSON). The orchestrator
    feeds parallel findings into `match_candidates` to bind candidates, then
    merges the result with `findings`.
    """

    findings: list[Finding] = field(default_factory=list)
    candidates: list[MaskedPerson] = field(default_factory=list)


def _mask_matches_name(mask: str, name: str) -> bool:
    """Check whether a single masked token (e.g. "P****") is compatible with
    a single name token (e.g. "Piotr"): same first letter, same length, and
    every non-leading character is a mask asterisk."""
    if not mask or not name:
        return False
    if len(mask) != len(name):
        return False
    if mask[0].lower() != name[0].lower():
        return False
    # Every char after position 0 in the mask must be a mask placeholder.
    return all(ch == "*" for ch in mask[1:])


def _candidate_matches_full_name(candidate: MaskedPerson, full_name: str) -> bool:
    """A candidate matches a parallel-supplied full name when:
    - the surname mask is compatible with the parallel surname token, AND
    - at least one given-name mask is compatible with one of the parallel
      given-name tokens.

    Polish names typically come as "Piotr Saczuk" or "Piotr Adam Saczuk";
    the surname is the last token. We're conservative: we require the
    surname to align (a strong signal) and only ONE given-name match
    (people drop middle names in casual sources).
    """
    parts = full_name.strip().split()
    if len(parts) < 2:
        return False
    surname = parts[-1]
    given = parts[:-1]
    if not _mask_matches_name(candidate.surname_mask, surname):
        return False
    return any(_mask_matches_name(mask, g) for mask in candidate.given_names_mask for g in given)


def _parallel_full_name_for_claim(claim_key: str) -> str | None:
    """Pull the full name out of a parallel claim key like
    `officer:Piotr Saczuk` or `owner:Anna Nowak`. Returns None if the key
    doesn't follow the convention (e.g. `team_size`)."""
    if ":" not in claim_key:
        return None
    prefix, name = claim_key.split(":", 1)
    if prefix not in {"officer", "owner"}:
        return None
    return name


def match_candidates(
    *,
    parallel_findings: list[Finding],
    candidates: list[MaskedPerson],
) -> list[Finding]:
    """For each parallel ownership claim, find a unique compatible
    candidate and emit a bound legal `Finding` keyed by the parallel
    claim key. Refuses to bind when matching is ambiguous (≥2 candidates
    fit the same parallel name) — the analyst will see ⚠️ "no registry
    confirmation" and follow up manually rather than the pipeline
    silently picking the wrong person.
    """
    out: list[Finding] = []
    for pf in parallel_findings:
        full_name = _parallel_full_name_for_claim(pf.claim)
        if full_name is None:
            continue
        is_owner = pf.claim.startswith("owner:")
        # Filter candidates by claim type so an officer-only candidate
        # doesn't bind to an owner claim and vice versa.
        eligible = [
            c
            for c in candidates
            if (c.shares_text is not None) == is_owner or _candidate_serves_both(c)
        ]
        matches = [c for c in eligible if _candidate_matches_full_name(c, full_name)]
        if len(matches) != 1:
            continue
        c = matches[0]
        value = c.shares_text if is_owner else (c.role or "")
        out.append(
            Finding(
                claim=pf.claim,
                value=value,
                source="krs",
                source_kind="legal",
                evidence_url=c.evidence_url,
                evidence_date=c.evidence_date,
            )
        )
    return out


def _candidate_serves_both(candidate: MaskedPerson) -> bool:
    """A person can be both an officer and a shareholder — typical for
    a Sp. z o.o. founder who is on the board. We treat such candidates
    as eligible for either claim type so the matcher binds them once on
    each side."""
    return candidate.role is not None and candidate.shares_text is not None

"""Tests for legal_matching.match_candidates.

Binds PII-masked KRS candidates to parallel-supplied full names using
initial-letter + token-length compatibility. The matcher is deliberately
conservative — when ≥2 candidates fit the same parallel name, it
refuses to bind so the analyst sees ⚠️ "no registry confirmation" and
follows up manually rather than us silently picking the wrong person.
"""

from pipeline.legal_matching import LegalRegistryResult, MaskedPerson, match_candidates
from pipeline.verdict_engine import Finding


def _parallel(claim: str, value: str) -> Finding:
    return Finding(
        claim=claim,
        value=value,
        source="parallel",
        source_kind="parallel",
        evidence_url="https://example.com/team",
        evidence_date="2026-04-09",
        confidence=0.9,
    )


def _candidate_owner(
    surname: str = "S*****",
    first: str = "P****",
    second: str | None = "A***",
    shares: str = "380 UDZIAŁÓW O ŁĄCZNEJ WARTOŚCI 19 000,00 ZŁ",
) -> MaskedPerson:
    given = [first] + ([second] if second else [])
    return MaskedPerson(
        surname_mask=surname,
        given_names_mask=given,
        evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0001174918",
        evidence_date="2026-04-09",
        shares_text=shares,
    )


def _candidate_officer(
    surname: str = "S*****",
    first: str = "P****",
    role: str = "PREZES ZARZĄDU",
) -> MaskedPerson:
    return MaskedPerson(
        surname_mask=surname,
        given_names_mask=[first],
        evidence_url="https://wyszukiwarka-krs.ms.gov.pl/details?krs=0001174918",
        evidence_date="2026-04-09",
        role=role,
    )


def test_owner_matched_when_initials_and_lengths_align():
    parallel = [_parallel("owner:Piotr Saczuk", "100%")]
    candidates = [_candidate_owner()]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert len(bound) == 1
    f = bound[0]
    assert f.claim == "owner:Piotr Saczuk"
    assert f.source_kind == "legal"
    assert f.source == "krs"
    assert "380" in f.value


def test_officer_matched_with_role_as_value():
    parallel = [_parallel("officer:Piotr Saczuk", "Prezes")]
    candidates = [_candidate_officer()]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert len(bound) == 1
    assert bound[0].claim == "officer:Piotr Saczuk"
    assert bound[0].value == "PREZES ZARZĄDU"


def test_no_match_when_initials_differ():
    """Parallel says Piotr Saczuk; KRS has K***** (Kowalski). Different
    initial → no bind, no finding emitted."""
    parallel = [_parallel("owner:Piotr Saczuk", "100%")]
    candidates = [_candidate_owner(surname="K******")]  # 7 chars, K initial

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_no_match_when_surname_length_differs():
    """Same first letter but wrong length → no bind. Saczuk = 6 chars,
    mask "S******" (7 chars) doesn't fit."""
    parallel = [_parallel("owner:Piotr Saczuk", "100%")]
    candidates = [_candidate_owner(surname="S******")]  # 7 chars

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_ambiguous_candidates_refuse_to_bind():
    """Two candidates whose masks both fit Piotr Saczuk → refuse to bind.
    The verdict-engine will then mark the claim ⚠️ for the right reason."""
    parallel = [_parallel("owner:Piotr Saczuk", "100%")]
    candidates = [
        _candidate_owner(surname="S*****", first="P****"),
        _candidate_owner(surname="S*****", first="P****"),
    ]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_owner_candidate_does_not_bind_to_officer_claim():
    """A candidate that's only a shareholder (no role) must not satisfy
    an officer claim. Pipeline keeps the two distinct."""
    parallel = [_parallel("officer:Piotr Saczuk", "Prezes")]
    candidates = [_candidate_owner()]  # has shares, no role

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_dual_role_candidate_binds_to_both_officer_and_owner():
    """Common Sp. z o.o. case: founder is both Prezes Zarządu AND sole
    shareholder. KRS returns one entry under sklad and one under
    wspolnicySpzoo — but the matcher should bind both parallel claims to
    that person.

    Note that the KRS adapter emits TWO MaskedPerson objects (one per
    section), so the matcher sees two candidates, each one specialised:
    role-only (officer) and shares-only (owner)."""
    parallel = [
        _parallel("officer:Piotr Saczuk", "Prezes"),
        _parallel("owner:Piotr Saczuk", "100%"),
    ]
    candidates = [_candidate_officer(), _candidate_owner()]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    bound_by_claim = {f.claim: f for f in bound}
    assert "officer:Piotr Saczuk" in bound_by_claim
    assert "owner:Piotr Saczuk" in bound_by_claim
    assert bound_by_claim["officer:Piotr Saczuk"].value == "PREZES ZARZĄDU"
    assert "380" in bound_by_claim["owner:Piotr Saczuk"].value


def test_skip_non_person_parallel_claims():
    """A non-person claim like `team_size` should be ignored by the
    matcher — it has no name to compare against."""
    parallel = [_parallel("team_size", "12")]
    candidates = [_candidate_owner()]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_person_with_two_given_names_matches_against_just_first():
    """Parallel often gives `Piotr Saczuk` even when KRS has both `Piotr`
    and `Adam`. As long as ONE given-name mask aligns with the parallel
    given-name token AND the surname matches, we bind."""
    parallel = [_parallel("owner:Piotr Saczuk", "100%")]
    candidates = [_candidate_owner(first="P****", second="A***")]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert len(bound) == 1


def test_no_match_when_parallel_supplies_a_different_first_name():
    """Parallel says Maria; KRS has only P****. Different given-name
    initial, surname matches by accident — still no bind, given names
    must align. (Use a name with no second-name collision.)"""
    parallel = [_parallel("owner:Maria Saczuk", "50%")]
    candidates = [_candidate_owner(first="P****", second=None)]

    bound = match_candidates(parallel_findings=parallel, candidates=candidates)

    assert bound == []


def test_legal_registry_result_dataclass_defaults_to_empty():
    """Sanity: an OpenCorporates-style call (which uses bound findings,
    no candidates) and a KRS-style call (candidates only) both round-trip
    cleanly through the dataclass."""
    r1 = LegalRegistryResult()
    assert r1.findings == []
    assert r1.candidates == []

"""KRS (Krajowy Rejestr Sądowy) adapter — real PII-masked JSON shape.

The public KRS JSON endpoint redacts personal data: every officer/owner
comes back with their first names, surname, and PESEL replaced by mask
strings (e.g. "P****", "S*****", "9**********"). The adapter therefore
emits a `LegalRegistryResult` with NO bound findings (we don't know who
the person actually is) and a list of `MaskedPerson` candidates carrying
the structural data — initials, name lengths, role/share text, evidence
URL. A separate matching step downstream binds candidates to parallel
findings whose full names are compatible with the masks.

HTTP is mocked at the boundary. The fixture below mirrors a real KRS
"OdpisAktualny" payload for a single-shareholder Sp. z o.o. (the same
shape we get from the live API for STABLEWATCH SP. Z O.O., KRS 0001174918).
"""

from pipeline.krs import KRS_ENDPOINT, fetch_legal_findings_krs
from pipeline.legal_matching import LegalRegistryResult, MaskedPerson

# Trimmed slice of a real KRS Odpis Aktualny JSON payload — only the
# fields the adapter actually reads. PII is masked the same way the
# public endpoint masks it.
_FAKE_KRS_RESPONSE = {
    "odpis": {
        "rodzaj": "Aktualny",
        "naglowekA": {"numerKRS": "0001174918"},
        "dane": {
            "dzial1": {
                "wspolnicySpzoo": [
                    {
                        "nazwisko": {"nazwiskoICzlon": "S*****"},
                        "imiona": {"imie": "P****", "imieDrugie": "A***"},
                        "identyfikator": {"pesel": "9**********"},
                        "posiadaneUdzialy": "380 UDZIAŁÓW O ŁĄCZNEJ WARTOŚCI 19 000,00 ZŁ",
                        "czyPosiadaCaloscUdzialow": False,
                    }
                ],
            },
            "dzial2": {
                "reprezentacja": {
                    "nazwaOrganu": "ZARZĄD",
                    "sklad": [
                        {
                            "nazwisko": {"nazwiskoICzlon": "S*****"},
                            "imiona": {"imie": "P****", "imieDrugie": "A***"},
                            "identyfikator": {"pesel": "9**********"},
                            "funkcjaWOrganie": "PREZES ZARZĄDU",
                            "czyZawieszona": False,
                        }
                    ],
                }
            },
        },
    }
}


def test_krs_endpoint_called_with_rejestr_p_and_json_format():
    calls: list[dict] = []

    def fake_http_get(url: str, params: dict) -> dict:
        calls.append({"url": url, "params": params})
        return _FAKE_KRS_RESPONSE

    fetch_legal_findings_krs(krs_number="0001174918", http_get=fake_http_get)

    assert calls[0]["url"].startswith(KRS_ENDPOINT)
    assert "0001174918" in calls[0]["url"]
    assert calls[0]["params"]["rejestr"] == "P"
    assert calls[0]["params"]["format"] == "json"


def test_krs_returns_legal_registry_result_with_no_bound_findings():
    """Because PII is masked, the adapter cannot bind any candidate to a
    real name. It emits an empty findings list and lets the downstream
    matching step bind candidates to parallel claims."""
    result = fetch_legal_findings_krs(
        krs_number="0001174918",
        http_get=lambda url, params: _FAKE_KRS_RESPONSE,
    )

    assert isinstance(result, LegalRegistryResult)
    assert result.findings == []


def test_krs_emits_officer_candidate_with_role_and_initials():
    result = fetch_legal_findings_krs(
        krs_number="0001174918",
        http_get=lambda url, params: _FAKE_KRS_RESPONSE,
    )

    officers = [c for c in result.candidates if c.role is not None]
    assert len(officers) == 1
    o = officers[0]
    assert isinstance(o, MaskedPerson)
    assert o.surname_mask == "S*****"
    assert o.given_names_mask == ["P****", "A***"]
    assert o.role == "PREZES ZARZĄDU"
    assert o.shares_text is None
    # The candidate carries an evidence URL pointing back at the public
    # KRS viewer for the same KRS number.
    assert "0001174918" in o.evidence_url


def test_krs_emits_owner_candidate_with_shares_and_initials():
    result = fetch_legal_findings_krs(
        krs_number="0001174918",
        http_get=lambda url, params: _FAKE_KRS_RESPONSE,
    )

    owners = [c for c in result.candidates if c.shares_text is not None]
    assert len(owners) == 1
    o = owners[0]
    assert o.surname_mask == "S*****"
    assert o.given_names_mask == ["P****", "A***"]
    assert "380" in o.shares_text
    assert o.role is None


def test_krs_handles_missing_optional_sections():
    """A spółka akcyjna may have zarząd but no dział 1 wspólnicySpzoo
    (shareholders are tracked separately for S.A.). Adapter must not
    crash — it simply emits the officer candidate."""
    payload = {
        "odpis": {
            "naglowekA": {"numerKRS": "0000999999"},
            "dane": {
                "dzial2": {
                    "reprezentacja": {
                        "sklad": [
                            {
                                "nazwisko": {"nazwiskoICzlon": "T*****"},
                                "imiona": {"imie": "M****"},
                                "funkcjaWOrganie": "CZŁONEK ZARZĄDU",
                            }
                        ]
                    }
                }
            },
        }
    }
    result = fetch_legal_findings_krs(
        krs_number="0000999999",
        http_get=lambda url, params: payload,
    )

    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.surname_mask == "T*****"
    assert c.given_names_mask == ["M****"]
    assert c.role == "CZŁONEK ZARZĄDU"

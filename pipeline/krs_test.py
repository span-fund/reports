"""KRS (Krajowy Rejestr Sądowy) adapter.

Public PL company registry. No API key required. We hit the official JSON
endpoint and parse the "Odpis Aktualny" payload into Finding objects shaped
identically to Etherscan/Parallel sources, so verdict-engine consumes them
uniformly.

HTTP is mocked at the boundary — the wrapper takes an injected http_get.
One Finding per officer (zarząd) and per owner (wspólnik) so each person
becomes an independent claim the verdict engine can cross-check.
"""

from pipeline.krs import KRS_ENDPOINT, fetch_legal_findings_krs

# Minimal slice of a real KRS "OdpisAktualny" JSON payload — only the fields
# the adapter actually reads.
_FAKE_KRS_RESPONSE = {
    "odpis": {
        "rodzaj": "Aktualny",
        "naglowekA": {"numerKRS": "0000123456", "nazwa": "Foo Sp. z o.o."},
        "dane": {
            "dzial1": {
                "wspolnicy": [
                    {
                        "nazwisko": "Nowak",
                        "imiona": {"imie": "Anna"},
                        "udzialy": {"liczba": "50", "wartosc": "5000.00"},
                    }
                ]
            },
            "dzial2": {
                "reprezentacja": {
                    "sklad": [
                        {
                            "nazwisko": "Kowalski",
                            "imiona": {"imie": "Jan"},
                            "funkcjaWOrganie": "Prezes Zarządu",
                        }
                    ]
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

    fetch_legal_findings_krs(krs_number="0000123456", http_get=fake_http_get)

    assert calls[0]["url"].startswith(KRS_ENDPOINT)
    assert "0000123456" in calls[0]["url"]
    assert calls[0]["params"]["rejestr"] == "P"
    assert calls[0]["params"]["format"] == "json"


def test_krs_returns_finding_per_officer_with_role_as_value():
    findings = fetch_legal_findings_krs(
        krs_number="0000123456",
        http_get=lambda url, params: _FAKE_KRS_RESPONSE,
    )

    officer_findings = [f for f in findings if f.claim.startswith("officer:")]
    assert len(officer_findings) == 1
    f = officer_findings[0]
    assert f.claim == "officer:Jan Kowalski"
    assert f.value == "Prezes Zarządu"
    assert f.source == "krs"
    assert f.source_kind == "legal"
    assert "0000123456" in f.evidence_url


def test_krs_returns_finding_per_owner_with_share_count_as_value():
    findings = fetch_legal_findings_krs(
        krs_number="0000123456",
        http_get=lambda url, params: _FAKE_KRS_RESPONSE,
    )

    owner_findings = [f for f in findings if f.claim.startswith("owner:")]
    assert len(owner_findings) == 1
    f = owner_findings[0]
    assert f.claim == "owner:Anna Nowak"
    # 50 udziałów of value 5000.00 — verdict-engine can parse this numerically
    assert "50" in f.value
    assert f.source == "krs"
    assert f.source_kind == "legal"


def test_krs_handles_missing_optional_sections():
    """A spółka akcyjna has zarząd but no dział 1 wspólnicy. Adapter must not
    crash — it returns only the officer findings."""
    payload = {
        "odpis": {
            "naglowekA": {"numerKRS": "0000999999", "nazwa": "Bar S.A."},
            "dane": {
                "dzial2": {
                    "reprezentacja": {
                        "sklad": [
                            {
                                "nazwisko": "Tester",
                                "imiona": {"imie": "Maria"},
                                "funkcjaWOrganie": "Członek Zarządu",
                            }
                        ]
                    }
                }
            },
        }
    }
    findings = fetch_legal_findings_krs(
        krs_number="0000999999",
        http_get=lambda url, params: payload,
    )
    assert [f.claim for f in findings] == ["officer:Maria Tester"]

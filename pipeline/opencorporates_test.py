"""OpenCorporates adapter — global fallback registry.

OpenCorporates is the cross-jurisdiction registry aggregator we use whenever
KRS doesn't apply (i.e. non-PL companies). API requires a token; the wrapper
takes it as an explicit arg, HTTP injected at the boundary.

Returns Finding objects shaped identically to KRS so the verdict engine
treats both source kinds uniformly under the "legal" tag.
"""

from pipeline.opencorporates import (
    OPENCORPORATES_ENDPOINT,
    fetch_legal_findings_opencorporates,
)

# Trimmed slice of the OpenCorporates company GET response — only the fields
# the adapter actually reads.
_FAKE_OC_RESPONSE = {
    "results": {
        "company": {
            "name": "Acme Inc.",
            "company_number": "12345",
            "jurisdiction_code": "us_de",
            "opencorporates_url": "https://opencorporates.com/companies/us_de/12345",
            "officers": [
                {
                    "officer": {
                        "name": "Jane Doe",
                        "position": "director",
                    }
                },
                {
                    "officer": {
                        "name": "John Roe",
                        "position": "secretary",
                    }
                },
            ],
        }
    }
}


def test_opencorporates_endpoint_called_with_jurisdiction_and_company_number():
    calls: list[dict] = []

    def fake_http_get(url: str, params: dict) -> dict:
        calls.append({"url": url, "params": params})
        return _FAKE_OC_RESPONSE

    fetch_legal_findings_opencorporates(
        jurisdiction_code="us_de",
        company_number="12345",
        api_key="test-key",
        http_get=fake_http_get,
    )

    url = calls[0]["url"]
    assert url.startswith(OPENCORPORATES_ENDPOINT)
    assert "us_de" in url
    assert "12345" in url
    assert calls[0]["params"]["api_token"] == "test-key"


def test_opencorporates_returns_finding_per_officer():
    findings = fetch_legal_findings_opencorporates(
        jurisdiction_code="us_de",
        company_number="12345",
        api_key="test-key",
        http_get=lambda url, params: _FAKE_OC_RESPONSE,
    )

    assert [f.claim for f in findings] == [
        "officer:Jane Doe",
        "officer:John Roe",
    ]
    assert findings[0].value == "director"
    assert findings[0].source == "opencorporates"
    assert findings[0].source_kind == "legal"
    assert "opencorporates.com" in findings[0].evidence_url
    assert "12345" in findings[0].evidence_url

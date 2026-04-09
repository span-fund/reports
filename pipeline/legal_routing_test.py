"""Jurisdiction routing: picks which legal-registry adapter to use.

PL → KRS (public, no key). Anything else → OpenCorporates (global fallback).
"skip" defers the decision to auto-detect downstream, so the router returns
None and the caller is expected to run auto_detect_jurisdiction first.
"""

from pipeline.legal_routing import auto_detect_jurisdiction, route_legal_adapter


def test_pl_routes_to_krs():
    assert route_legal_adapter("PL") == "krs"


def test_pl_is_case_insensitive():
    assert route_legal_adapter("pl") == "krs"


def test_non_pl_routes_to_opencorporates():
    assert route_legal_adapter("US") == "opencorporates"
    assert route_legal_adapter("DE") == "opencorporates"
    assert route_legal_adapter("GB") == "opencorporates"


def test_skip_returns_none_so_caller_auto_detects():
    assert route_legal_adapter("skip") is None


def test_auto_detect_pl_from_tld():
    assert auto_detect_jurisdiction("foo.pl") == "PL"
    assert auto_detect_jurisdiction("https://www.bar.pl/") == "PL"


def test_auto_detect_returns_none_for_non_pl_tld():
    # Non-PL TLDs are ambiguous (a .com company can sit anywhere) — caller
    # falls back to OpenCorporates which doesn't need a jurisdiction hint.
    assert auto_detect_jurisdiction("example.com") is None
    assert auto_detect_jurisdiction("example.io") is None

"""Jurisdiction → legal-registry adapter routing.

Pure dispatch logic. PL is the only jurisdiction with a first-class national
adapter (KRS, public, no key). Everything else falls back to OpenCorporates,
the global registry aggregator. The wizard's "skip" sentinel means the user
deferred jurisdiction selection — the caller is expected to run
auto_detect_jurisdiction() and re-route, hence we return None here rather
than guessing.
"""


def auto_detect_jurisdiction(domain: str) -> str | None:
    """Best-effort jurisdiction guess from a domain TLD.

    Only returns a value when the TLD is a country-code we trust as a strong
    signal. Generic TLDs (.com/.io/.xyz) are deliberately not guessed —
    OpenCorporates doesn't need a jurisdiction hint to look a company up,
    and a wrong PL guess would silently route to KRS and produce empty
    findings.
    """
    cleaned = domain.strip().lower().rstrip("/")
    # Strip scheme + path so "https://www.foo.pl/about" → "foo.pl".
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    cleaned = cleaned.split("/", 1)[0]
    if cleaned.endswith(".pl"):
        return "PL"
    return None


def route_legal_adapter(jurisdiction: str) -> str | None:
    j = jurisdiction.strip().lower()
    if j == "skip":
        return None
    if j == "pl":
        return "krs"
    return "opencorporates"

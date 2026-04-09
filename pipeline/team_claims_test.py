"""Team claim manifest loader.

Mirror of overview_claims but for the Team section. Each entry binds a
Parallel field name to an optional `legal_expected` flag — when true, the
verdict engine downgrades the verdict to ⚠️ if no legal-registry source is
present, even at high parallel confidence.
"""

import json
from pathlib import Path

from pipeline.team_claims import load_team_claims


def test_load_team_claims_parses_legal_expected_flag(tmp_path: Path):
    manifest = {
        "claims": [
            {
                "name": "ownership_structure",
                "kind": "hard",
                "display_label": "Ownership structure",
                "parallel_field": "ownership",
                "legal_expected": True,
            },
            {
                "name": "founder_bio",
                "kind": "soft",
                "display_label": "Founder bio",
                "parallel_field": "founder_bio",
                "legal_expected": False,
            },
        ]
    }
    path = tmp_path / "team-claims.json"
    path.write_text(json.dumps(manifest))

    claims = load_team_claims(path)

    assert len(claims) == 2
    assert claims[0].name == "ownership_structure"
    assert claims[0].kind == "hard"
    assert claims[0].parallel_field == "ownership"
    assert claims[0].legal_expected is True
    assert claims[1].name == "founder_bio"
    assert claims[1].legal_expected is False


def test_legal_expected_defaults_to_false_when_omitted(tmp_path: Path):
    manifest = {
        "claims": [
            {
                "name": "team_size",
                "kind": "soft",
                "display_label": "Team size",
                "parallel_field": "team_size",
            }
        ]
    }
    path = tmp_path / "team-claims.json"
    path.write_text(json.dumps(manifest))

    claims = load_team_claims(path)

    assert claims[0].legal_expected is False

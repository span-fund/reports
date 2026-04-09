# Due Diligence Reports

[![CI](https://github.com/span-fund/reports/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/span-fund/reports/actions/workflows/ci.yml)

An open-source due-diligence research pipeline that produces structured,
reproducible reports on stablecoin issuers, DeFi protocols, and the
companies behind them. Every factual claim about a target is cross-checked
across multiple independent sources — AI web research, direct on-chain
reads, and legal-registry adapters — under a strict policy: no claim is
marked verified unless ≥2 sources agree, including ≥1 non-AI source.
Reports are published here as both rendered markdown and structured JSON
findings, with full source attribution for every claim.

Intended audience: independent crypto researchers, journalists covering
DeFi / stablecoins, and OSS developers building due-diligence tooling.

## Reports

### Pipeline-generated (via `dd-research`)

Structured outputs from live runs of the `pipeline/` code. Each target
folder contains `README.md` (rendered report), `last_run.json` (structured
findings with source attribution per claim), `parallel-runs.jsonl` (audit
log of external API calls), and `config.json` (wizard inputs).

| Report | Subject | Phase | Section | Verdict summary |
|---|---|---|---|---|
| [targets/frax-com/](targets/frax-com/README.md) | Frax Finance — frxUSD / sfrxUSD / FXS | 3 | Overview | 3 ⚠️ + 5 ❌ (live E2E on 8-claim manifest) |
| [targets/stablewatch/](targets/stablewatch/README.md) | Stablewatch sp. z o.o. — ownership & board (KRS 0001174918) | 4 | Team | 3 ⚠️ — incl. automatic detection of the Czarnecki / Idea Bank case |

**Highlight — the Czarnecki detection.** The `targets/stablewatch/` run
flagged `owner:Jacek Czarnecki` as ⚠️ "no registry confirmation": Parallel
found him still listed as co-founder on public sources (his own Twitter
bio), but KRS Odpis Aktualny no longer has a matching candidate — he was
removed as a shareholder on 2025-12-29, three months before Stablewatch
announced joining the Sky Ecosystem. This is the exact failure mode
Phase 4 was designed to catch: public narrative lagging the registry.

### Legacy (hand-written)

Authored by hand before the pipeline existed. Kept as ground-truth
reference for pipeline validation — the hand-written Stablewatch DD
independently reached the same conclusion about the Czarnecki ownership
change that the pipeline now detects automatically.

| Report | Subject | Date |
|---|---|---|
| [sky-protocol/](sky-protocol/README.md) | Sky Protocol (formerly MakerDAO) — sUSDS, collateral, governance, risks | 2026-04-06 |
| [stablewatch/](stablewatch/README.md) | Stablewatch sp. z o.o. — team, products, Sky relationship, KRS findings | 2026-04-06 |

## Methodology

The pipeline composes evidence from four independent verifier layers and
feeds them through a strict cross-check engine before anything is marked
verified:

1. **Parallel.ai** — AI-driven web research with self-assessed confidence
   scores, cited per finding with a source URL and publication date.
2. **On-chain reads** — Etherscan V2 (chainid-aware) for token supply,
   ERC-4626 vault accounting, PSM balances, and arbitrary contract reads
   via `eth_call`.
3. **Legal registries** — KRS (Polish Krajowy Rejestr Sądowy, public JSON
   API, no key) for Polish targets; OpenCorporates as global fallback for
   non-Polish jurisdictions (API key pending — see
   [OCESD-60476](https://opencorporates.com)).
4. **Dashboard / agent-browser** *(planned Phase 5)* — live screenshot
   evidence for info.skyeco.com, stablewatch.io/analytics, etc.

Every claim passes through three pieces of deep-module machinery:

- **Claim classifier** — declarative hard / soft taxonomy per report
  section. Hard claims (numbers, ownership, regulatory status, team
  credentials) always go through manual review regardless of confidence.
  Soft claims (narrative, ecosystem context) can auto-pass when the
  STRICT policy holds.
- **Verdict engine** — applies the cross-check policy per claim, with
  numeric tolerance for value comparison, case-folded string equality as
  fallback, and a `requires_legal` flag that downgrades ownership claims
  to ⚠️ when no registry source confirms them even at high Parallel
  confidence.
- **Legal matching** — binds PII-masked KRS candidates (the public JSON
  endpoint redacts names to `"P****"` / `"S*****"`) to parallel-supplied
  full names by initial-letter + token-length compatibility. Refuses to
  bind on ambiguity so ⚠️ only fires for real registry gaps.

Verdict tags in the rendered report:

- ✅ — ≥2 sources agree, STRICT policy satisfied
- ⚠️ — sources disagree or registry confirmation missing
- ❌ — insufficient sources (e.g. fetcher failed, Parallel returned "Not
  found")
- `[MANUAL REVIEW NEEDED]` — hard claim, analyst must confirm regardless
  of tag

Full architectural decisions and phased implementation plan live in
[`plans/dd-research-implementation.md`](plans/dd-research-implementation.md).

## Repo structure

```
pipeline/          — dd-research skill implementation (Python, uv)
scripts/           — live runners that hit real APIs (run_frax_live.py,
                     run_stablewatch_live.py)
targets/           — pipeline-generated DD artefacts (one folder per target)
  <slug>/
    config.json           wizard inputs
    overview_claims.json  Overview section manifest
    team-claims.json      Team section manifest (Phase 4+)
    README.md             rendered report
    last_run.json         structured findings + verdicts
    parallel-runs.jsonl   audit log of Parallel API calls
  _cache/          TTL-scoped cache (parallel 7d, onchain 1h, legal 30d)
plans/             architectural decisions + phased implementation plan
skills/            Claude Code skill wrapper
sky-protocol/      legacy hand-written DD report
stablewatch/       legacy hand-written DD report
```

## Development setup

```
uv sync
uv run pre-commit install
```

This installs dev dependencies and activates the pre-commit hook that
runs `ruff check`, `ruff format --check`, and `pytest` against
`pipeline/` and `scripts/` on every commit. CI mirrors the hook exactly
(see `.github/workflows/ci.yml`).

Required env vars (see `.env.example`):

- `PARALLEL_API_KEY` — Parallel.ai SDK/CLI
- `ETHERSCAN_API_KEY` — Etherscan V2 (chainid-aware)

Copy `.env.example` to `.env` and fill in real values. `.env` is
gitignored and never committed.

### Running the test suite

```
uv run pytest pipeline/
```

### Running a live DD

Live runners under `scripts/` instantiate the real Parallel SDK and
call real external APIs against an existing target config. They leave
a clean diff in `targets/<slug>/` for review — nothing is committed
automatically.

```
# Phase 3 Overview E2E on Frax Finance (needs PARALLEL_API_KEY + ETHERSCAN_API_KEY)
PYTHONPATH=. uv run python scripts/run_frax_live.py

# Phase 4 Team E2E on Stablewatch (needs PARALLEL_API_KEY only — KRS is public)
PYTHONPATH=. uv run python scripts/run_stablewatch_live.py
```

## Licence

Dual-licensed:

- **Source code** (everything under `pipeline/`, `scripts/`, `skills/`, plus build configuration) — [MIT](LICENSE).
- **Report content** (`<target>/README.md`, `<target>/last_run.json`, `<target>/parallel-runs.jsonl`, prose under `plans/` and `targets/`) — [Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](LICENSE-content).

Third-party data sources retain their own licence terms — see `LICENSE-content` for the full attribution list.

# Due Diligence Reports

## Reports

| Report | Subject | Date | Status |
|---|---|---|---|
| [sky-protocol/](sky-protocol/README.md) | Sky Protocol (formerly MakerDAO) — sUSDS, collateral, governance, risks | April 6, 2026 | Draft |
| [stablewatch/](stablewatch/README.md) | Stablewatch sp. z o.o. — team, products, Sky relationship, KRS findings | April 6, 2026 | Draft |

## Methodology

- On-chain data verified via Etherscan API V2 (direct `eth_call` and `tokenbalance` queries)
- Dashboard data captured from info.skyeco.com and stablewatch.io/analytics
- Legal data from Polish National Court Register (KRS) via ekrs.ms.gov.pl
- Smart contract code reviewed from [github.com/sky-ecosystem/sdai](https://github.com/sky-ecosystem/sdai)
- Governance data from [vote.makerdao.com](https://vote.makerdao.com)
- Regulatory sources: GENIUS Act (Greenberg Traurig, Latham & Watkins), MiCA (21 Analytics)
- Credit rating: S&P Global Ratings

All claims marked as verified have at least one primary source (on-chain data, official documentation, or legal registry). Claims that could not be independently verified are excluded or explicitly flagged.

## Development setup

The `pipeline/` directory contains the `dd-research` skill implementation (Python, uv). After cloning:

```
uv sync
uv run pre-commit install
```

This installs dev dependencies and activates the pre-commit hook that runs `ruff` and `pytest` against `pipeline/` on every commit.

Required env vars (see `.env.example`):

- `PARALLEL_API_KEY` — Parallel.ai SDK/CLI
- `ETHERSCAN_API_KEY` — Etherscan V2 (chainid-aware)

Copy `.env.example` to `.env` and fill in real values. `.env` is gitignored.

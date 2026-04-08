# Plan: Generic DD Methodology + Pipeline dla span-fund/reports

## Plan storage

Ten plan zostanie zapisany jako pierwszy artefakt do repo:
- **Lokalizacja:** `span-fund/reports/plans/dd-methodology-rollout.md`
- **Powód:** widoczność, możliwość review przez zespół, traceability decyzji projektowych
- **Jako pierwszy krok implementacji:** `mkdir -p plans && cp <ten plan> plans/dd-methodology-rollout.md`

## Context

Zakończyliśmy pełny due diligence dla pary Sky Protocol (DeFi protokół) + Stablewatch (krypto-spółka stojąca za risk advisory). Wynik to dwa interlinkowane raporty w `span-fund/reports`, oparte na on-chain data (Etherscan API V2), live dashboardach (info.skyeco.com, stablewatch.io), polskim rejestrze KRS, kodzie smart kontraktów (sky-ecosystem/sdai) i wielu źródłach third-party.

W trakcie pracy wyszło kilka kluczowych lessons learned:
- **Etherscan API V1 jest deprecated** — trzeba V2 z `chainid` parameter
- **Legal registry > LinkedIn** — KRS ujawnił że Czarnecki został wykreślony jako wspólnik 29.12.2025, czego LinkedIn nie pokazuje (nadal "Co-Founder")
- **Live on-chain data > raporty third-party** — wcześniejsze claimy o $1.64B USDC w PSM były błędne, on-chain pokazał $4.30B (2.6× więcej)
- **"Annualized run-rate" ≠ revenue** — $435M to point-in-time, faktyczny przychód 2025 = $338M
- **"Coming Soon" = nie w produkcji** — Sky Sentinel ogłoszony, ale nie działa
- **Single-source third-party analyses są słabe** — większość claimów o rozbiciu przychodów Sky pochodzi z jednego artykułu PANews
- **Browser automation > scraping** — Cloudflare/captcha/JS-rendered content wymagają prawdziwej przeglądarki
- **Parallel agents oszczędzają godziny** — research, weryfikacja i ekstrakcja danych równolegle vs sekwencyjnie

User chce powtarzać ten proces dla kilku innych projektów. Decyzje:
- **Lokalizacja:** METHODOLOGY.md + pipeline w `span-fund/reports` repo (versionable, reviewable)
- **Zakres:** DeFi protokoły, krypto-spółki, oraz pary protokół+spółka (NIE tradycyjne tech/fintech)
- **Poziom automatyzacji:** Zautomatyzowany pipeline — driver dostaje target i generuje draft

## Architektura

```
span-fund/reports/
├── README.md                          # (istnieje) Index raportów
├── METHODOLOGY.md                     # NEW — runbook dla człowieka
├── LESSONS-LEARNED.md                 # NEW — pułapki i workarounds z DD #1
│
├── plans/                             # NEW — plany implementacji (review trail)
│   └── dd-methodology-rollout.md      # Ten plan (Phase 0)
│
├── pipeline/                          # NEW — narzędzia DD
│   ├── README.md                      # Jak używać pipeline
│   ├── init.sh                        # Bootstrap nowego DD: tworzy strukturę katalogów
│   ├── config.example.yaml            # Schema konfiguracji target
│   │
│   ├── research/
│   │   ├── prompts/
│   │   │   ├── 01-protocol-overview.md       # Prompt dla research agenta (faza 1)
│   │   │   ├── 02-company-overview.md
│   │   │   ├── 03-mechanism-deep-dive.md
│   │   │   ├── 04-team-verification.md
│   │   │   ├── 05-risks-non-obvious.md
│   │   │   └── 06-source-verification.md
│   │   └── orchestrator.sh             # Wrapper uruchamiający równoległe agenty
│   │
│   ├── onchain/
│   │   ├── etherscan.sh                # V2 API wrapper (chainid, common selectors)
│   │   ├── selectors.md                # Lista funkcji ERC-20/4626/Vat z hex selectors
│   │   └── decoders.js                 # BigInt decoder dla hex returns
│   │
│   ├── legal/
│   │   ├── README.md                   # Adapters per jurisdiction
│   │   ├── krs-pl.sh                   # Polish KRS (wyszukiwarka + odpis pełny PDF)
│   │   ├── companies-house-uk.sh       # UK Companies House API
│   │   ├── opencorporates.sh           # Global fallback (OpenCorporates API)
│   │   └── jurisdiction-detector.sh    # Heuristic: domain, address → jurisdiction
│   │
│   ├── browser/
│   │   ├── snapshot.sh                 # agent-browser wrapper z full screenshot
│   │   ├── live-dashboard.sh           # Capture data z JS-rendered dashboardów
│   │   └── governance-forum.sh         # Search forum.{protocol}.com / Snapshot
│   │
│   └── verdict/
│       ├── tagger.md                    # Schema verdyktów (✅⚠️❌🔄)
│       └── sources.md                   # Hierarchia siły źródeł
│
├── templates/                          # NEW — szablony raportów
│   ├── protocol-report.template.md     # Dla protokołów (jak sky-protocol/)
│   ├── company-report.template.md      # Dla spółek (jak stablewatch/)
│   ├── combined-index.template.md      # Dla par protokół+spółka (root README)
│   └── placeholders.md                 # Lista zmiennych do podstawienia
│
├── examples/                           # NEW — link/copy istniejących raportów jako reference
│   ├── sky-protocol -> ../sky-protocol
│   └── stablewatch -> ../stablewatch
│
├── sky-protocol/                       # (istnieje) Sky DD
└── stablewatch/                        # (istnieje) Stablewatch DD
```

## Co zawiera każda część

### METHODOLOGY.md (główny runbook, ~300-500 linii)

Sekcje:
1. **Cele i zakres** — co to jest DD, czego dotyczy
2. **Klasyfikacja targetu** — protokół / spółka / para. Decyzja na początku.
3. **6 faz pipeline:**
   - **Faza 0: Scope** — config, jurisdiction detection, chains
   - **Faza 1: Parallel research** — 3-5 agentów z `prompts/`
   - **Faza 2: On-chain verification** — Etherscan V2, contract reads
   - **Faza 3: Live data** — browser automation dashboardów
   - **Faza 4: Legal/registry** — adapters per jurisdiction
   - **Faza 5: Cross-reference & verdict tagging** — każdy claim → ✅⚠️❌🔄
   - **Faza 6: Report compilation** — templates → finalne markdown
4. **Hierarchia źródeł** — on-chain > legal registry > official docs > news (multi-source) > third-party (single source)
5. **Verdict schema** — jak tagować claimy
6. **Quality gates** — checklisty przed publikacją

### LESSONS-LEARNED.md (pułapki z DD #1, ~100-200 linii)

Konkretne traps które wpadliśmy/uniknęliśmy:
- Etherscan V1 deprecated → V2 z chainid
- "Annualized run-rate" ≠ "revenue"
- LinkedIn titles lag behind legal reality (Czarnecki case)
- Single-source third-party = weak (PANews case)
- Cloudflare blokuje scraping → agent-browser z headless Chrome
- "Coming Soon" pages = produkt nie istnieje
- Marketing claimy ("$10B advisory") wymagają niezależnej weryfikacji
- makerburn.com zamknięty — info.skyeco.com to nowy źródłowy dashboard
- BigInt parsing dla hex returns (Node.js, nie Python)
- KRS PDF jest scrollowalnym dokumentem — pełny odpis ma 7 stron z historią zmian (kluczowe dla wykrywania zmian własnościowych)

### pipeline/init.sh

```bash
# Usage: pipeline/init.sh <target-slug> [protocol|company|combined]
# Tworzy: <target-slug>/{README.md, screenshots/, legal/, on-chain/, sources/}
# Kopiuje template + tworzy config.yaml
```

### pipeline/research/prompts/*.md

Pre-written prompts dla research agentów. Każdy ma:
- Kontekst (kim jest target)
- Jakie pytania zadać
- Jakie źródła sprawdzić
- Format outputu (claim → źródło → verdict)

Przykład `01-protocol-overview.md`:
```
You are researching {{TARGET_NAME}}, a DeFi protocol on {{CHAIN}}.

Find:
1. Core mechanism (lending? AMM? stablecoin issuer? yield aggregator?)
2. Native token(s) — addresses, supplies
3. Total Value Locked (sources: protocol's own dashboard, DeFiLlama, on-chain)
4. Revenue model — how does the protocol generate value?
5. Governance structure — token-based? multisig? foundation?
6. Recent (last 12 months) governance proposals or controversies

For each finding: SOURCE URL + DATE.
Mark unverifiable claims as NOT VERIFIABLE.
Use Exa MCP tools (mcp__exa__web_search_exa, mcp__exa__crawling_exa).
```

### pipeline/onchain/etherscan.sh

```bash
# Wrapper dla Etherscan API V2 z popularnymi metodami:
# Usage:
#   etherscan.sh balance 0xTOKEN 0xADDR
#   etherscan.sh totalsupply 0xTOKEN
#   etherscan.sh call 0xCONTRACT 0xSELECTOR
#   etherscan.sh decode hex 18    # decode hex with 18 decimals
# Wymaga ETHERSCAN_API_KEY w env (NIE w repo)
```

### pipeline/legal/krs-pl.sh

```bash
# Polish KRS via ekrs.ms.gov.pl
# Usage: krs-pl.sh <KRS_NUMBER>
# Output: PDF pełnego odpisu + JSON z danymi (wspólnicy, zarząd, historia zmian)
# Używa agent-browser dla nawigacji + download
```

### pipeline/legal/opencorporates.sh

Globalny fallback dla jurysdykcji bez własnego adaptera. OpenCorporates pokrywa 100M+ firm w 130+ krajach.

### templates/protocol-report.template.md

Markdown z placeholderami `{{LIKE_THIS}}`. Generator (init.sh) podstawia. Sekcje identyczne jak `sky-protocol/README.md`:
1. Protocol Overview (z tabelą metryk + live dashboard screenshot)
2. Core Mechanism (z linkami do GitHub i Etherscan kontraktów)
3. On-chain State (totalSupply, totalAssets, etc.)
4. Collateral / TVL Composition
5. Revenue
6. Governance Risks
7. Regulatory Status
8. Historical Incidents
9. Key Contracts (tabela z linkami Etherscan)
10. Risk Summary

### templates/company-report.template.md

Sekcje jak `stablewatch/README.md`:
1. Company Overview (legal entity, registration)
2. Ownership (z historią zmian z legal registry — KRYTYCZNE)
3. Team (LinkedIn verified)
4. Products (z statusem produkcyjnym)
5. Relationships (z linkami do related protocol DD)
6. Competitive Context
7. Transparency Assessment
8. Questions for Founders
9. Files (linki do screenshots, legal docs, sources)

### Verdict tagger schema

Każdy claim w finalnym raporcie taguje się:
- ✅ **Verified** — primary source (on-chain, legal registry, smart contract code)
- ⚠️ **Partially verified** — single source third-party lub self-reported
- ❌ **Not verifiable** — szukaliśmy, brak źródła
- 🔄 **Corrected** — pierwotny claim okazał się błędny, podajemy poprawkę

Tylko ✅ trafia do final summary. ⚠️ jest w treści ale flagowane. ❌ wymienia się w "Open questions". 🔄 dokumentuje się jako lesson learned.

## Pliki które trzeba stworzyć

| Plik | Typ | Linie | Priorytet |
|---|---|---|---|
| `METHODOLOGY.md` | docs | 300-500 | P0 |
| `LESSONS-LEARNED.md` | docs | 150-250 | P0 |
| `pipeline/README.md` | docs | 100-150 | P0 |
| `pipeline/init.sh` | shell | 80-120 | P0 |
| `pipeline/config.example.yaml` | config | 30-50 | P0 |
| `pipeline/research/prompts/01-protocol-overview.md` | prompt | 40-60 | P1 |
| `pipeline/research/prompts/02-company-overview.md` | prompt | 40-60 | P1 |
| `pipeline/research/prompts/03-mechanism-deep-dive.md` | prompt | 50-80 | P1 |
| `pipeline/research/prompts/04-team-verification.md` | prompt | 40-60 | P1 |
| `pipeline/research/prompts/05-risks-non-obvious.md` | prompt | 50-80 | P1 |
| `pipeline/research/prompts/06-source-verification.md` | prompt | 60-100 | P1 |
| `pipeline/research/orchestrator.sh` | shell | 100-150 | P1 |
| `pipeline/onchain/etherscan.sh` | shell | 150-200 | P0 |
| `pipeline/onchain/selectors.md` | docs | 50-80 | P0 |
| `pipeline/onchain/decoders.js` | js | 80-120 | P0 |
| `pipeline/legal/README.md` | docs | 50-80 | P1 |
| `pipeline/legal/krs-pl.sh` | shell | 100-150 | P1 |
| `pipeline/legal/companies-house-uk.sh` | shell | 80-120 | P2 |
| `pipeline/legal/opencorporates.sh` | shell | 80-120 | P1 |
| `pipeline/legal/jurisdiction-detector.sh` | shell | 50-80 | P2 |
| `pipeline/browser/snapshot.sh` | shell | 60-100 | P1 |
| `pipeline/browser/live-dashboard.sh` | shell | 60-100 | P1 |
| `pipeline/browser/governance-forum.sh` | shell | 60-100 | P2 |
| `pipeline/verdict/tagger.md` | docs | 80-120 | P0 |
| `pipeline/verdict/sources.md` | docs | 60-100 | P0 |
| `templates/protocol-report.template.md` | template | 200-300 | P0 |
| `templates/company-report.template.md` | template | 150-250 | P0 |
| `templates/combined-index.template.md` | template | 50-80 | P1 |
| `templates/placeholders.md` | docs | 50-80 | P1 |
| `examples/README.md` | docs | 30-50 | P2 |

**Total: ~30 plików, ~2500-3500 linii**

## Implementation phases (kolejność wdrażania)

**Phase 0 — Plan w repo (najpierw):**
- `mkdir -p span-fund/reports/plans/`
- Skopiuj ten plan jako `plans/dd-methodology-rollout.md`
- Commit + push (osobny commit przed jakimkolwiek kodem)

**Phase A — Core docs + templates (P0):**
- METHODOLOGY.md, LESSONS-LEARNED.md
- templates/protocol-report.template.md, templates/company-report.template.md
- pipeline/verdict/tagger.md, pipeline/verdict/sources.md

Po Phase A można już ręcznie reużywać metodologię nawet bez automatyzacji.

**Phase B — On-chain & init (P0):**
- pipeline/init.sh, pipeline/config.example.yaml
- pipeline/onchain/etherscan.sh, selectors.md, decoders.js
- pipeline/README.md

Po Phase B można bootstrap'ować nowe DD i odpytywać on-chain.

**Phase C — Research & legal (P1):**
- pipeline/research/prompts/* (6 plików)
- pipeline/research/orchestrator.sh
- pipeline/legal/krs-pl.sh, opencorporates.sh
- pipeline/browser/snapshot.sh, live-dashboard.sh

Po Phase C pipeline jest funkcjonalny end-to-end dla większości jurysdykcji.

**Phase D — Extensions (P2):**
- pipeline/legal/companies-house-uk.sh
- pipeline/legal/jurisdiction-detector.sh
- pipeline/browser/governance-forum.sh
- examples/, templates/combined-index.template.md

## Reused / istniejące zasoby

Z aktualnego DD wyciągamy do reuse:
- **`/Users/tkowalczyk/Library/Mobile Documents/.../stablewatch/ANALIZA_STABLEWATCH_SKY_DUE_DILIGENCE.md`** — źródło struktury raportu
- **`/Users/tkowalczyk/Library/Mobile Documents/.../stablewatch/WERYFIKACJA_ZRODLOWA.md`** — źródło verdict tagging schema
- **`/tmp/span-fund-reports/sky-protocol/README.md`** — base dla `templates/protocol-report.template.md`
- **`/tmp/span-fund-reports/stablewatch/README.md`** — base dla `templates/company-report.template.md`
- **agent-browser CLI** (`/Users/tkowalczyk/.claude/skills/agent-browser/SKILL.md`) — referencja dla browser scripts
- **Etherscan API V2** — testy z curl + Node BigInt już zwalidowane na sUSDS, USDS, DAI, SKY, USDC w PSM

## Verification — jak zweryfikować że pipeline działa

Test end-to-end na nowym targecie (np. **Ethena Labs** + **USDe** jako para):

1. `cd /tmp/span-fund-reports && pipeline/init.sh ethena combined`
2. Wypełnić `ethena/config.yaml`:
   ```yaml
   target_name: "Ethena"
   target_type: "combined"
   protocol:
     name: "Ethena Protocol"
     chains: ["ethereum"]
     contracts:
       USDe: "0x4c9EDD5852cd905f086C759E8383e09bff1E68B3"
       sUSDe: "0x9D39A5DE30e57443BfF2A8307A4256c8797A3497"
   company:
     name: "Ethena Labs"
     jurisdiction: "VG"  # British Virgin Islands
     domain: "ethena.fi"
   ```
3. `pipeline/research/orchestrator.sh ethena` — uruchamia 5 równoległych research agentów
4. `pipeline/onchain/etherscan.sh totalsupply 0x4c9EDD5852cd905f086C759E8383e09bff1E68B3 > ethena/on-chain/usde-supply.json`
5. `pipeline/legal/opencorporates.sh ethena-labs > ethena/legal/opencorporates.json`
6. `pipeline/browser/live-dashboard.sh https://app.ethena.fi/dashboards > ethena/screenshots/dashboard.png`
7. Manual: `cp templates/company-report.template.md ethena/README.md` i podstawienie placeholderów
8. Review + verdict tagging
9. `git add ethena/ && git commit -m "Add Ethena DD"`

Quality gates przed publikacją:
- [ ] Wszystkie ✅ claimy mają primary source
- [ ] Wszystkie ⚠️ claimy mają explicit warning
- [ ] On-chain numbers świeższe niż 24h
- [ ] Legal registry sprawdzony (jeśli dotyczy)
- [ ] Cross-references działają (jeśli combined report)
- [ ] Brak API keys w commitach
- [ ] Screenshots w odpowiednich katalogach
- [ ] Lista pytań do founders (jeśli company)

## Krytyczne pliki istniejącego DD do skopiowania jako base

| Source | Destination | Co przenieść |
|---|---|---|
| `/tmp/span-fund-reports/sky-protocol/README.md` | `templates/protocol-report.template.md` | Cała struktura, zamienić nazwy własne na placeholdery |
| `/tmp/span-fund-reports/stablewatch/README.md` | `templates/company-report.template.md` | j.w. |
| `/Users/tkowalczyk/.../WERYFIKACJA_ZRODLOWA.md` (sekcja 0) | `pipeline/onchain/selectors.md` | Lista hex selectors + decoded values |
| Konwersacja DD (parallel agents pattern) | `pipeline/research/prompts/*.md` | Prompty z Faz 1-5 |
| Konwersacja DD (browser automation) | `pipeline/browser/*.sh` | Konkretne komendy agent-browser |

## Open questions / decyzje do dopytania w trakcie implementacji

Poniżej rzeczy które mogą wymagać decyzji w trakcie pisania kodu (NIE blokują startu):
- Czy `init.sh` ma być w bash czy Python? (bash = zero deps; Python = łatwiejszy parsing YAML/JSON)
- Czy używać `gh` CLI do auto-commitów po każdym DD czy zostawić to manual?
- Czy `opencorporates.sh` wymaga API keya (free tier ma limit)? Jeśli tak, dodać `.env.example`
- Czy templates używają Jinja2-style `{{var}}` czy bash `${var}` substitution?

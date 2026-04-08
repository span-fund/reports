# Plan: `dd-research` skill — implementacja vertical slices

> Source PRD: `plans/dd-research-skill-prd.md`
> Source plan: `plans/dd-methodology-rollout.md` (architektura repo, lista plików, fazy A/B/C/D)
> Output: phased tracer-bullet plan, każda faza demoable end-to-end na realnym targecie.

## Architectural decisions

Durable decisions które obowiązują we wszystkich fazach:

- **Architecture style**: monolityczny lokalny pipeline pod Claude Code skill. Bez serwera, bez globalnego stanu, bez współdzielonego cache.
- **Storage**: plain JSON files na dysku — config, last_run, cache, audit log. Zero external storage deps.
- **Key entities**:
  - `target` — jeden DD subject (`<slug>/`); typ ∈ {protocol, company, combined}
  - `config` — output wizarda, persisted jako `<slug>/config.json`
  - `section` — jednostka raportu (Overview, Mechanism, Team, …); każda ma własny schema, renderer, reguły hard/soft
  - `claim` — jednostka informacji w sekcji; zawsze przechodzi przez claim-classifier (hard/soft) i verdict-engine
  - `finding` — uzasadnienie claimu z konkretnego źródła (Parallel | on-chain | legal registry | browser)
  - `verdict` — tag (✅ ⚠️ ❌ 🔄) + rationale, output verdict-engine
  - `last_run` — normalized state DD (`<slug>/last_run.json`): config + findings + verdicts + rendered_sections
  - `audit_entry` — log każdego Parallel call'a (`<slug>/parallel-runs.jsonl`)
- **Verifier topology**: Parallel.ai zawsze działa równolegle z ≥1 niezależnym source'em (Etherscan / legal registry / agent-browser). Parallel jest jedną z N warstw, nigdy jedyną.
- **Cross-check policy**: STRICT — claim ✅ tylko gdy ≥2 niezależne źródła potwierdzają, w tym ≥1 non-Parallel. Konflikt → ⚠️. Brak źródeł → ❌. Polityka zaszyta w jednym deep module (verdict-engine).
- **Hard/soft taxonomy**: deklaratywna, per sekcja raportu. Hard = wszystko co decyduje o invest (liczby, ownership, regulatory, team credentials, smart-contract risks, red flags). Soft = mechanism narrative, ecosystem context. Hard zawsze flagowane do manual review niezależnie od confidence Parallel'a.
- **Output schema**: structured JSON per sekcja → markdown przez section renderery. Section JSON jest ground truth, markdown jest derived.
- **Entry point**: Claude Code skill (`dd-research`). CLI tool poza scope MVP.
- **Parallel access**: SDK/CLI bezpośrednio. NIE przez MCP plugin.
- **Budżet**: soft cap manual w wizardzie (tier Lite/Base/Pro/Ultra). Cost-guard abortuje przed pierwszym call'em jeśli preview > cap. Brak auto-eskalacji w trakcie.
- **Cache**: plain JSON files, key = `(target, namespace, hash)`. TTL per namespace: Parallel sections 7d / on-chain 1h / legal registry 30d / browser 7d.
- **Reproducibility**: każdy DD musi mieć `last_run.json` + `parallel-runs.jsonl` + `config.json` w katalogu targetu, commitable razem z README.md. Każdy mode (refresh / section / compare) startuje deterministycznie z last_run.json.
- **Secrets**: API keys w `.env` (gitignored), nigdy w repo. Skill weryfikuje obecność wymaganych env vars na starcie.
- **Quality gates**: skill zawsze zostawia clean diff do review, nie commituje automatycznie.

---

## Phase 1: Tracer bullet — Hello DD z prawdziwym Parallel call'em

**User stories**: 1, 2, 3, 4, 9, 10, 11, 12, 20, 21, 22, 25, 26, 29, 31, 33, 34, 35

### What to build

Najcieńszy end-to-end slice z prawdziwą integracją Parallel.ai. Skill `dd-research new` startuje, prosi przez wizard o 4 inputy (typ, domena, chain+jurisdiction, tier), tworzy strukturę katalogu targetu z `config.json`, weryfikuje wymagane env vars (PARALLEL_API_KEY, ETHERSCAN_API_KEY) i fail'uje czysto jeśli brakuje.

Następnie pipeline odpala równolegle dwie ścieżki dla **jednej sekcji raportu (Overview)** z **jednym claimem** (totalSupply primary tokena):

1. **Parallel ścieżka**: cost-guard pokazuje preview kosztu vs soft cap z wizarda; po acceptcie task-group-builder buduje minimal Parallel Task Group z jedną sekcją Overview i Pydantic-style schema; SDK/CLI call do Parallel'a; response cache'owany na dysku z TTL 7d; każde wywołanie logowane do `parallel-runs.jsonl` z task_id, processor, kosztem, timestampem.
2. **Manual ścieżka**: bezpośredni call do Etherscan V2 wrapper'a (z planu) o `totalSupply` primary tokena z konfiguracji wizarda; response cache'owany z TTL 1h.

Verdict-engine bierze oba findingsy, aplikuje STRICT policy (≥2 źródła, ≥1 non-Parallel — spełnione bo Etherscan jest non-Parallel) i zwraca verdict (✅ jeśli liczby się zgadzają, ⚠️ przy konflikcie, ❌ jeśli któraś ścieżka padła). Section-renderer dla Overview generuje minimalny markdown z claimem + verdict tagiem + cytatem URL+date dla Parallel + linkiem Etherscan dla on-chain.

Skill zapisuje `<slug>/{config.json, last_run.json, parallel-runs.jsonl, README.md}` i kończy bez commitowania, zostawiając clean diff do review.

### Acceptance criteria

- [ ] `dd-research new` w Claude Code uruchamia wizard, zadaje 4 pytania, validuje inputs
- [ ] Skill weryfikuje obecność `PARALLEL_API_KEY` i `ETHERSCAN_API_KEY` na starcie i fail'uje czysto z explicit komunikatem przy braku
- [ ] Cost preview pokazuje analitykowi szacowany koszt PRZED pierwszym Parallel call'em; abort jeśli preview > soft cap
- [ ] Pipeline wykonuje równolegle Parallel call dla Overview + Etherscan call dla totalSupply
- [ ] Parallel response cache'owany w plain JSON z TTL 7d; re-run w tym samym dniu nie generuje nowego API call'a
- [ ] Każdy Parallel call zalogowany w `<slug>/parallel-runs.jsonl` z (task_id, processor, koszt, timestamp)
- [ ] Verdict-engine zwraca ✅ gdy oba źródła zgadzają się, ⚠️ przy konflikcie, ❌ gdy któraś ścieżka padła
- [ ] Section-renderer dla Overview generuje markdown z claimem, verdict tagiem i cytatami obu źródeł (URL+date dla Parallel, link Etherscan dla on-chain)
- [ ] Skill produkuje `<slug>/{config.json, last_run.json, parallel-runs.jsonl, README.md}` po zakończeniu
- [ ] Skill nie commituje automatycznie — clean working tree zmieniony, do review
- [ ] E2E demo: realne uruchomienie na wybranym małym targecie (np. tier Lite, soft cap $2) zwraca poprawny verdict dla totalSupply primary tokena

---

## Phase 2: Hard claims + manual review flag

**User stories**: 5, 6, 7, 27, 32

### What to build

Wprowadza taxonomy hard/soft do pipeline'u. Claim-classifier dostaje deklaratywną listę reguł dla sekcji Overview (na razie tylko jednej): liczby (TVL, supply, revenue) → hard, opisowe tło → soft. Verdict-engine zaczyna rozróżniać oba typy:

- **Hard claim** zawsze otrzymuje dodatkowy flag `requires_manual_review = true` niezależnie od wyniku cross-checku. Confidence Parallel'a jest dodatkowym sygnałem widocznym w treści, ale nigdy nie zwalnia z manual review.
- **Soft claim** może zostać auto-tagowany ✅ jeśli STRICT cross-check pass + Parallel confidence > threshold; widoczny confidence w treści.

Skill po zakończeniu runu pokazuje analitykowi explicit listę claimów wymagających manual review, posortowaną per sekcja. Jeśli Parallel zwraca niski confidence (< threshold) na hard claimie, skill walil pełnym warning message zachęcającym do dodatkowej weryfikacji.

Section-renderer renderuje hard claimy z markerem `[MANUAL REVIEW NEEDED]` w markdown.

### Acceptance criteria

- [ ] Claim-classifier istnieje jako osobny moduł z deklaratywną listą reguł hard/soft dla Overview
- [ ] Verdict-engine flaguje wszystkie hard claimy `requires_manual_review = true` niezależnie od cross-check'u
- [ ] Soft claimy mogą być auto-✅ przy STRICT pass + confidence threshold
- [ ] Skill pokazuje listę hard claimów wymagających manual review na końcu runu
- [ ] Niski confidence Parallel'a na hard claimie generuje explicit warning w outputcie skill'a
- [ ] Markdown raportu zawiera marker `[MANUAL REVIEW NEEDED]` przy hard claimach
- [ ] Hard/soft klasyfikacja zachowana w `last_run.json` per claim
- [ ] E2E: re-run targetu z Phase 1 pokazuje totalSupply jako hard z manual review flagą

---

## Phase 3: Pełna sekcja Overview + comprehensive on-chain

**User stories**: 13, 22, 30

### What to build

Overview rośnie do produkcyjnego setu claimów: TVL, total supply, revenue, top holders, primary token addresses, key contract addresses. Etherscan wrapper rośnie do pełnego setu selectors z `pipeline/onchain/selectors.md` z planu (ERC-20, ERC-4626, Vat). Cache namespace dla on-chain z TTL 1h dostaje pełną pokrycie.

Wszystkie liczbowe claimy są cross-checkowane Parallel vs on-chain, zgodnie z STRICT policy. Section-renderer dla Overview produkuje markdown identyczny strukturalnie z istniejącym `sky-protocol/README.md` Overview section.

Pipeline obsługuje gracefully sytuacje gdy część on-chain queries się nie powiedzie (np. nieznany selector dla custom contract): brakujące pola wpadają jako ❌ z entry w "Pytania do founders", reszta sekcji się generuje.

### Acceptance criteria

- [ ] Etherscan wrapper obsługuje pełen set selectors potrzebny dla Overview (totalSupply, totalAssets, balanceOf, top holders przez logs lub API, contract owner reads)
- [ ] On-chain cache namespace z TTL 1h działa per (target, contract, selector)
- [ ] Wszystkie liczbowe claimy w Overview cross-checkowane przez verdict-engine
- [ ] Brak danych on-chain dla pojedynczego pola → ❌ + entry w "Pytania do founders", nie crash całej sekcji
- [ ] Markdown Overview sekcji strukturalnie zgodny z `sky-protocol/README.md` (te same sub-sekcje, te same metryki)
- [ ] E2E: target z Phase 1 ma teraz pełny Overview, wszystkie hard claimy flagowane do manual review

---

## Phase 4: Druga sekcja Team + legal verifier

**User stories**: 5, 19, 28

### What to build

Pierwszy drugi non-Parallel weryfikator klasy: legal registry adapter. KRS (PL) jako pierwszy adapter, OpenCorporates jako globalny fallback. Adapter zwraca structured JSON o tym samym kształcie co Parallel/Etherscan findings — `{claim, source, evidence, date}`.

Sekcja Team dostaje własny schema (founders, team members, ownership, ostatnie zmiany w cap table), własne reguły hard/soft (ownership / team credentials = hard, bio narrative = soft) i własny renderer. Wszystkie claimy o ownership zawsze cross-checkowane z legal registry — nawet jeśli Parallel ma high confidence, brak potwierdzenia z registry → ⚠️ + entry w "Open questions" + entry w "Pytania do founders".

Jurisdiction routing w skill'u: na podstawie `config.json` (jurisdiction wybrana w wizardzie) skill wybiera adapter (KRS dla PL, OpenCorporates dla reszty). "Skip" w wizardzie → auto-detect na podstawie domeny/footera dopiero teraz.

### Acceptance criteria

- [ ] KRS adapter dla PL: bierze KRS number lub nazwę, zwraca structured JSON (wspólnicy, zarząd, historia zmian)
- [ ] OpenCorporates adapter jako fallback dla non-PL jurysdykcji
- [ ] Legal registry findings w tym samym shape co Parallel/Etherscan, akceptowane przez verdict-engine
- [ ] Cache namespace dla legal registry z TTL 30d
- [ ] Sekcja Team ma własny schema, własne reguły hard/soft, własny renderer
- [ ] Ownership claimy zawsze cross-checkowane z registry; brak potwierdzenia → ⚠️ + "Open questions" + "Pytania do founders"
- [ ] Jurisdiction routing działa: PL → KRS, reszta → OpenCorporates
- [ ] "Skip" w wizardzie triggeruje auto-detect (domain footer / address parsing) tylko wtedy
- [ ] E2E: target combined typu (protocol+company) z Phase 3 ma teraz Overview + Team z legal registry verifier

---

## Phase 5: Wszystkie pozostałe sekcje raportu

**User stories**: 20, 22, 28, 30

### What to build

Pozostałe sekcje z istniejących templatów dorzucone end-to-end: Mechanism, Collateral/TVL Composition, Revenue, Governance, Regulatory, Historical Incidents, Risks, Key Contracts. Każda dostaje:

- własny structured JSON schema (definiowany jako dane, nie jako kod)
- własne reguły hard/soft w claim-classifier
- własny section renderer
- własny cache namespace jeśli ma niezależne źródła

Task-group-builder rośnie do budowania pełnego Parallel Task Group z N tasks równolegle (jeden per sekcja). agent-browser dorzucony jako trzeci typ niezależnego weryfikatora dla live dashboard screenshotów (sekcje Overview/TVL/Revenue zyskują screenshot evidence). Każda sekcja może mieć swoją kombinację weryfikatorów zgodnie z STRICT policy.

Pipeline produkuje pełny raport strukturalnie zgodny z istniejącymi `sky-protocol/README.md` i `stablewatch/README.md`.

### Acceptance criteria

- [ ] Wszystkie 9 sekcji raportu (Overview, Mechanism, Collateral, Revenue, Governance, Regulatory, Historical Incidents, Risks, Key Contracts) mają schema, reguły hard/soft, renderer
- [ ] Task-group-builder buduje pełny Parallel Task Group z N tasks równolegle
- [ ] agent-browser jako trzeci weryfikator dostarcza screenshot evidence dla live dashboardów
- [ ] Każda sekcja ma minimum dwie ścieżki weryfikacji (Parallel + ≥1 non-Parallel) zgodnie z STRICT policy
- [ ] Brakujące dane w jednej sekcji nie blokują reszty raportu (graceful degradation)
- [ ] Markdown finalny strukturalnie zgodny z `sky-protocol/README.md` (protocol) lub `stablewatch/README.md` (company) lub kombinowanym index'em
- [ ] **E2E test z PRD**: realny pełny DD na Ethena Labs + USDe (combined), tier Base, soft cap $5, wszystkie sekcje wygenerowane, wszystkie hard claimy flagowane do manual review, cost w `parallel-runs.jsonl` poniżej cap

---

## Phase 6: Refresh mode + delta-engine

**User stories**: 14, 15, 23, 36

### What to build

Drugi skill mode: `dd-research refresh <target>`. Skill ładuje istniejący `last_run.json` jako poprzedni state, re-runuje wszystkie weryfikatory (większość dostaje cache hit, on-chain hits ze świeższym TTL), produkuje nowy state. Delta-engine porównuje stary vs nowy state structurally (na poziomie JSON, NIE diff'em markdown'a) i generuje sekcję "Changes since last DD" w markdown z trzema typami zmian:

- **Added**: claimy które są nowe w current state (np. nowy member zarządu, nowy contract deployed)
- **Removed**: claimy które zniknęły (np. wykreślony wspólnik — Czarnecki case)
- **Modified**: liczby które się zmieniły o więcej niż threshold (TVL drift, supply changes, ownership %)

Cosmetic differences (whitespace, ordering) są ignorowane — tylko semantyczne zmiany trafiają do delta. Delta section dokleja się do README.md jako nowa sekcja na górze, reszta raportu zostaje bez zmian. Skill nadpisuje `last_run.json` nowym stanem (poprzedni można zachować jako `last_run.<timestamp>.json` dla audytu).

### Acceptance criteria

- [ ] `dd-research refresh <target>` ładuje istniejący last_run.json jako baseline
- [ ] Re-run wszystkich weryfikatorów respektuje cache TTL per namespace (większość on-chain swieża, Parallel z cache jeśli < 7d)
- [ ] Delta-engine porównuje structural JSON, nie markdown diff
- [ ] Delta klasyfikuje zmiany jako added / removed / modified
- [ ] Threshold dla "modified" liczb konfigurowalny (default np. 5%)
- [ ] Cosmetic differences (whitespace, ordering) ignorowane
- [ ] Sekcja "Changes since last DD" dokleja się na górze README.md, reszta raportu bez zmian
- [ ] Stary `last_run.json` zachowany jako `last_run.<timestamp>.json` dla audit trail
- [ ] E2E: refresh targetu z Phase 5 po wprowadzeniu fake on-chain change pokazuje delta z prawidłową klasyfikacją

---

## Phase 7: Section re-run mode

**User stories**: 16, 37

### What to build

Trzeci skill mode: `dd-research section <target> <section_name>`. Skill ładuje last_run.json, identyfikuje target section, invalidatuje cache namespaces dla tej konkretnej sekcji (Parallel task dla niej + powiązane on-chain queries jeśli są section-specific), re-runuje TYLKO te ścieżki, przelicza verdict dla sekcji, podmienia jeden section block w README.md i odpowiednie pola w last_run.json.

Opcjonalny `--focus "<custom prompt>"` argument pozwala przerzucić Parallel task z innym fokusem (np. `section ethena Risks --focus "regulatory enforcement actions"`) bez modyfikacji schemy ani reguł.

Skill weryfikuje że pozostałe sekcje pozostały dokładnie takie same w README.md (snapshot test na poziomie skill'a).

### Acceptance criteria

- [ ] `dd-research section <target> <name>` re-runuje tylko jedną sekcję
- [ ] Cache invalidation skoper do tej sekcji — pozostałe namespaces nieruszane
- [ ] `--focus` argument przekazywany do Parallel task'a tej sekcji bez zmian schemy
- [ ] Pozostałe sekcje w README.md identyczne po section re-run (skill self-checkuje)
- [ ] last_run.json zaktualizowany tylko w obrębie tej sekcji
- [ ] E2E: section re-run sekcji Risks dla targetu z Phase 6 zmienia tylko Risks, reszta raportu bit-identyczna

---

## Phase 8: Comparison mode + hardcoded matrix

**User stories**: 17, 18, 36

### What to build

Czwarty skill mode: `dd-research compare <target1> <target2> [<target3>]`. Skill ładuje `last_run.json` z 2-3 targetów z dysku — **zero nowych Parallel call'ów**, wszystko z istniejących stanów. Buduje hardcoded matrix table z stałymi kolumnami: target name, mechanism (one-liner), TVL, team size, regulatory status, top 3 risks.

Wartości dla każdej kolumny ekstraktowane są ze structured last_run.json poprzez stałe path'y per kolumna (np. TVL z Overview/total_value_locked, top risks z Risks section findings). Brakujące wartości w którymś last_run.json renderują się jako "—" z explicit warning na końcu.

Output to markdown table zapisany jako standalone artefakt (`comparisons/<t1>-vs-<t2>.md`) — nie modyfikuje istniejących README.md targetów. Cost = $0.

### Acceptance criteria

- [ ] `dd-research compare <t1> <t2> [<t3>]` ładuje 2-3 last_run.json z dysku
- [ ] Zero Parallel call'ów; cost pokazany jako $0 w outputcie skill'a
- [ ] Hardcoded matrix kolumn: target, mechanism, TVL, team size, regulatory, top 3 risks
- [ ] Wartości ekstraktowane stałymi path'ami z structured last_run.json
- [ ] Brakujące wartości jako "—" z warning na końcu
- [ ] Output zapisany jako `comparisons/<t1>-vs-<t2>.md`, nie modyfikuje README.md targetów
- [ ] E2E: porównanie 2 targetów z poprzednich faz (np. Phase 5 + Phase 1) generuje matrix

---

## Phase 9: Quality gates + commitable artifacts

**User stories**: 24, 28, 30

### What to build

Pre-commit quality gate aplikujący się do każdego skill mode'a (new / refresh / section / compare). Po zakończeniu każdego runu skill weryfikuje strukturalnie:

- Wszystkie ✅ claimy mają primary source z URL i datą w last_run.json
- Wszystkie ⚠️ claimy mają entry w sekcji "Open questions" w README.md
- Wszystkie ❌ claimy mają entry w sekcji "Pytania do founders" w README.md
- Hard claimy mają explicit "manually reviewed" marker (skill nie ustawi go sam — analityk musi to zrobić, skill tylko weryfikuje obecność po manual review pass)
- On-chain numbers świeższe niż 1h
- Cost summary dołączony do README.md (sekcja "DD metadata") z totalem z parallel-runs.jsonl
- last_run.json + parallel-runs.jsonl + config.json są obecne w katalogu targetu
- Brak API keys w żadnym z artifactów (regex scan przed commitem)

Skill produkuje listę "Pytania do founders" automatycznie z claimów otagowanych ❌, deduplikuje je, sortuje per sekcja.

Skill nadal nie commituje — zostawia clean diff, ale dodaje finalny raport do `<slug>/QUALITY_REPORT.md` z checklistą per gate (passed / failed) i konkretnymi action itemami przy failach.

### Acceptance criteria

- [ ] Quality gate aplikuje się do każdego skill mode'a (new / refresh / section / compare)
- [ ] Skill weryfikuje wszystkie 8 quality criteriów z PRD strukturalnie
- [ ] Lista "Pytania do founders" generowana automatycznie z ❌ claimów, deduplikowana, sortowana per sekcja
- [ ] Cost summary w README.md dołączany w sekcji "DD metadata"
- [ ] Regex scan na API keys (PARALLEL_API_KEY, ETHERSCAN_API_KEY patterns) w wszystkich artifactach
- [ ] `<slug>/QUALITY_REPORT.md` z checklistą per gate (passed / failed + action items)
- [ ] Skill nadal nie commituje automatycznie
- [ ] E2E: pełen flow new → refresh → section → compare na Ethena, każdy mode produkuje QUALITY_REPORT.md ze wszystkimi gates passed

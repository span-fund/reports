# PRD: `dd-research` skill + Parallel.ai integration

> Status: Draft — wynik discovery interview (`/ask:ask`) na bazie `plans/dd-methodology-rollout.md`.
> Powiązany plan: `plans/dd-methodology-rollout.md` (architektura repo, fazy, lista plików).
> Ten PRD nie zastępuje tamtego — uzupełnia go o decyzje produktowe wokół Parallel.ai i UX skill'a.

## Problem Statement

Po zakończeniu pierwszego pełnego DD (Sky Protocol + Stablewatch) chcę powtarzać ten proces dla 10+ projektów miesięcznie, solo. Obecny workflow ma trzy bóle:

1. **Ręczne klejenie raportu** — wyniki z 5 równoległych research agentów + on-chain queries + browser screenshotów + legal registry trzeba ręcznie skleić w spójny markdown. Połowa czasu DD to mechaniczne przepisywanie, nie research.
2. **Decyzje upfront** — żeby uruchomić nowy DD muszę zdecydować typ targetu, jurysdykcję, primary chain, listę kontraktów. Każdy nowy target = 15 minut "konfiguracji" zanim cokolwiek się dzieje.
3. **Brak gwarancji jakości claimów** — pierwsze DD pokazało że third-party źródła notorycznie się mylą (PSM $1.64B vs faktyczne $4.30B, "annualized run-rate" jako revenue, LinkedIn lag vs KRS, single-source PANews dla całego revenue breakdown). Bez systematycznego cross-check policy każdy nowy DD ryzykuje powtórzenie tych samych pomyłek.

Dodatkowo: Parallel.ai oferuje stack (Task/Search/Extract/FindAll/Monitor/Basis) który dokładnie pokrywa fazę 1 i 5 mojego pipeline, ale nie chcę wpadać w single-vendor lock-in ani polegać na jego confidence score'ach jako jedynym arbitrze prawdy.

## Solution

Skill `dd-research` w Claude Code, który:

- **Startuje od krótkiego wizarda** (4 pytania: typ, domena, chain+jurisdiction, tier kosztu) zamiast wymagania ręcznego config.yaml.
- **Orkiestruje równolegle** Parallel.ai Task Group (jeden task per sekcja raportu z structured JSON schema) **+ niezależne weryfikatory** (Etherscan V2, KRS/Companies House/OpenCorporates, agent-browser dla dashboardów). Parallel jest jedną z warstw, nie jedynym źródłem prawdy.
- **Cross-checkuje wyniki STRICT** — claim dostaje ✅ tylko jeśli minimum 2 niezależne źródła go potwierdzają, w tym minimum 1 non-Parallel. Konflikty → ⚠️ + flag w "Open questions".
- **Taguje verdykty hybrydowo per typ claimu** — "hard" claimy (liczby, ownership, regulatory, team credentials, smart-contract risks, red flags) zawsze wymagają manualnej weryfikacji; "soft" claimy (mechanism narrative, ecosystem context) mogą być auto-tagowane na podstawie Parallel Basis confidence.
- **Renderuje raport automatycznie** — section_json + template → spójny markdown bez ręcznego klejenia.
- **Pilnuje budżetu** — soft cap kosztu Parallel per DD wybierany w wizardzie, plain-JSON disk cache z TTL żeby re-runy nie płaciły dwa razy za niezmienione dane.
- **Wspiera 4 tryby** poza nowym DD: refresh (delta vs poprzedni stan), section re-run, comparison (2-3 targety side-by-side).

Po implementacji typowy workflow to: `dd-research` w Claude Code → 4 pytania w wizardzie → ~10 minut research w tle → review draftu z automatycznymi verdict tagami → manual override hard claimów → commit. Czas DD spada z dni do godzin, bez kompromisu w cross-check'u.

## User Stories

1. Jako solo analityk DD chcę uruchomić nowy DD jedną komendą i odpowiedzieć na 4 pytania, żebym mógł zacząć research w mniej niż 2 minuty zamiast wypełniać config.yaml.
2. Jako analityk chcę żeby skill sam pamiętał strukturę raportu (sekcje, ich kolejność, schema), żebym nie musiał kopiować templatów ręcznie dla każdego nowego targetu.
3. Jako analityk chcę żeby Parallel.ai Task Group leciał równolegle z moimi niezależnymi weryfikatorami (on-chain, legal registry, browser), żeby cross-check był wynikiem dwóch ścieżek a nie jednej.
4. Jako analityk chcę żeby każdy claim w raporcie miał verdict tag (✅⚠️❌🔄) na podstawie polityki cross-checku, żebym wiedział którym częściom mogę ufać bez własnej weryfikacji.
5. Jako analityk chcę żeby "hard" claimy (liczby, ownership, regulatory, team credentials, smart-contract risks) zawsze były flagowane do manualnej weryfikacji, żebym nie zaufał Parallel'owi w sprawach które decydują o invest.
6. Jako analityk chcę żeby "soft" claimy (mechanism, narracja) były auto-tagowane na podstawie confidence score'u, żebym nie spędzał czasu na review każdego zdania o tym jak działa AMM.
7. Jako analityk chcę widzieć confidence score Parallel'a obok każdego soft claimu, nawet gdy jest auto-tagowany, żebym mógł szybko zidentyfikować edge case'y.
8. Jako analityk chcę żeby konflikty między źródłami zawsze kończyły się ⚠️ i listingiem w "Open questions", żeby żadna rozbieżność nie umknęła w ciszy.
9. Jako analityk chcę żeby skill zawsze cytował primary source (URL + data) dla każdego ✅ claimu, żeby raport był audytowalny po fakcie.
10. Jako analityk chcę żeby wizard pytał o tier kosztu Parallel (Lite/Base/Pro/Ultra) na starcie, żebym kontrolował budżet świadomie zamiast eskalować w trakcie.
11. Jako analityk chcę żeby skill odmówił uruchomienia jeśli przewidywany koszt przekracza soft cap zdefiniowany w wizardzie, żebym nie palił budżetu przez przypadek.
12. Jako analityk chcę żeby wyniki Parallel'a były cache'owane na dysku per `(target, sekcja, schema_version)` z TTL 7 dni, żeby re-runy w tym samym tygodniu kosztowały zero.
13. Jako analityk chcę żeby on-chain queries (Etherscan V2) były cache'owane z krótszym TTL (np. 1h), żeby świeże numery były domyślne ale comparison mode nie kosztował ponownie pełnych 10 minut.
14. Jako analityk chcę móc uruchomić skill w trybie `refresh <target>` żeby zaktualizować istniejący DD i dostać sekcję "Changes since last DD" z diff'em poprzedniego stanu vs nowego.
15. Jako analityk chcę żeby refresh był liczony jako structured JSON comparison, nie jako diff plików markdown, żeby zmiany w wording'u nie generowały false positive'ów.
16. Jako analityk chcę móc uruchomić skill w trybie `section <target> <name>` żeby przepisać jedną sekcję z innym fokusem bez ruszania reszty raportu.
17. Jako analityk chcę móc uruchomić skill w trybie `compare <target1> <target2> [<target3>]` żeby dostać side-by-side matrix table z istniejących raportów.
18. Jako analityk chcę żeby comparison miał stałą hardcoded matrycę kolumn (target, mechanism, TVL, team size, regulatory status, top risks), żeby porównania były spójne i porównywalne między uruchomieniami.
19. Jako analityk chcę żeby skill auto-detektował chains+jurisdiction tylko wtedy gdy odpowiedziałem "skip" w wizardzie, żeby auto-detect nie nadpisywał moich świadomych wyborów.
20. Jako analityk chcę żeby raport finalny miał identyczną strukturę sekcji co istniejące `sky-protocol/README.md` i `stablewatch/README.md`, żeby moje istniejące przyzwyczajenia review'owe się nie zmieniły.
21. Jako analityk chcę żeby skill renderował każdą sekcję z osobnego JSON-a przez section renderer, żebym mógł podmienić pojedynczy renderer bez ruszania reszty pipeline'u.
22. Jako analityk chcę żeby wszystkie sekcje finalnego raportu były generowane jednym przebiegiem (Parallel Task Group + manual verifiers + verdict engine + render), żeby brak jednej sekcji nie blokował reszty.
23. Jako analityk chcę żeby skill zostawiał `last_run.json` w katalogu targetu z normalized state (Parallel findings + manual findings + verdicts), żeby refresh i section re-run miały deterministyczny punkt startu.
24. Jako analityk chcę żeby skill nigdy nie commitował API keys ani `.env` plików, żebym nie musiał audytować każdego commitu.
25. Jako analityk chcę żeby skill rozmawiał z Parallel.ai przez SDK/CLI a nie przez MCP plugin, żebym miał lepszą kontrolę nad structured output i nie zależał od stanu MCP serwera.
26. Jako analityk chcę żeby skill rozróżniał Parallel processor tiers (Lite/Base/Pro/Ultra) i używał wybranego w wizardzie dla wszystkich tasków w danym DD, żeby koszt był przewidywalny.
27. Jako analityk chcę żeby skill walil pełnym error message gdy Parallel zwraca niski confidence score na hard claimie, żebym wiedział że muszę ten claim zweryfikować ręcznie zanim zacommituję.
28. Jako analityk chcę żeby skill produkował listę "Pytania do founders" automatycznie z claimów otagowanych ❌ (not verifiable), żebym nie musiał ich szukać ręcznie po raporcie.
29. Jako analityk chcę żeby skill tworzył strukturę katalogów `<target>/{README.md, screenshots/, legal/, on-chain/, sources/}` automatycznie, żebym nie zapominał tego kroku.
30. Jako analityk chcę żeby skill generował raport również wtedy gdy część sekcji ma niekompletne dane (z ⚠️ w treści zamiast crash'a), żebym dostał draft do review zamiast nic.
31. Jako analityk chcę żeby cross-check engine był osobnym modułem testowalnym snapshot'ami, żebym mógł zmieniać policy bez ryzyka regresji w renderingu.
32. Jako analityk chcę żeby claim-classifier (hard/soft) był osobnym modułem z jasną listą reguł per sekcja, żebym mógł go review'ować i poprawiać bez czytania kodu pipeline'u.
33. Jako analityk chcę dostać explicit cost preview od skill'a przed pierwszym Parallel call'em, żebym mógł cancelować jeśli źle ustawiłem tier.
34. Jako analityk chcę żeby skill logował każde wywołanie Parallel z (task_id, processor, koszt) do `<target>/parallel-runs.jsonl`, żebym miał audit trail kosztów per DD.
35. Jako analityk chcę żeby skill weryfikował obecność `PARALLEL_API_KEY` i innych wymaganych env vars na starcie i fail'ował jasnym komunikatem zamiast w środku flow.
36. Jako przyszły kolaborant chcę żeby cały pipeline był reproducible z `last_run.json` + cache'a, żebym mógł re-runować cudze DD lokalnie bez płacenia od nowa.
37. Jako analityk chcę żeby skill miał skrót do "wymuś pominięcie cache" dla pojedynczej sekcji, żebym mógł re-runować tylko to co się zmieniło u źródła.

## Implementation Decisions

### Architektura — major functional components

**Deep modules** (testowalne w izolacji, stabilne API):

- **verdict-engine** — bierze structured findings z dwóch ścieżek (Parallel + manual verifiers) plus klasyfikację claimu (hard/soft) i zwraca tag (✅⚠️❌🔄) z rationale. Encapsuluje całą cross-check policy w jednym miejscu.
- **claim-classifier** — bierze tekst claimu plus jego sekcję raportu i zwraca "hard" lub "soft". Cała taxonomia w jednym module, łatwo iterowalna bez ruszania reszty.
- **task-group-builder** — bierze target config + wybrany tier i konstruuje Parallel Task Group spec (lista tasków, schemas per sekcja, source policy). Hermetyzuje wiedzę o tym jak rozmawiać z Parallel.
- **delta-engine** — bierze poprzedni state JSON i nowy state JSON, zwraca markdown sekcji "Changes since last DD". Refresh mode opiera się wyłącznie na nim.
- **section-renderer** — per sekcja raportu, bierze section JSON i zwraca markdown przez template. Wymienialny per sekcja bez wpływu na resztę.
- **cache** — disk-backed plain JSON, key = `(target, namespace, hash)`, TTL configurable per namespace. Zero zewnętrznych zależności (sqlite/redis/etc).

**Shallow components** (cienkie warstwy łączące):

- **wizard** — UI layer w skill (AskUserQuestion w Claude Code). 4 pytania, output to `target/config.json`.
- **cost-guard** — gate przed każdym Parallel call'em, sprawdza budżet vs soft cap, abortuje czysto jeśli przekroczony.
- **dd-research skill** — orkiestracja w Claude Code. Wywołuje wizard, task-group-builder, manual verifiers, verdict-engine, section-rendererów. Cienka warstwa kleju.

### Granice systemu i integration points

- **Parallel.ai** — przez SDK/CLI (NIE przez MCP plugin). Wymaga `PARALLEL_API_KEY` w env. Skill używa Task Group API, Search API, Extract API, FindAll API. Monitor API jest poza scope MVP.
- **Etherscan V2** — przez własny wrapper z planu (`pipeline/onchain/etherscan.sh`). Pozostaje niezależnym weryfikatorem, działa równolegle do Parallel'a. Wymaga `ETHERSCAN_API_KEY`.
- **Legal registry adapters** — KRS (PL), Companies House (UK), OpenCorporates (global fallback). Każdy zwraca structured JSON do verdict engine'a. Niezależne od Parallel'a.
- **agent-browser** — dla live dashboardów i screenshotów (Cloudflare/captcha/JS-rendered content). Niezależny weryfikator.
- **Claude Code skill runtime** — entry point. Skill loaduje się on-demand, nie globalnie.

### Key data flows

1. **Nowy DD:** Wizard (4 pytania) → target/config.json → task-group-builder buduje Parallel spec → równolegle: Parallel Task Group + manual verifiers (etherscan + legal + browser) → wszystkie wyniki do last_run.json → claim-classifier taguje claimy hard/soft → verdict-engine aplikuje cross-check policy → section-renderer'y generują markdown per sekcja → finalny README.md.
2. **Refresh:** Load last_run.json (poprzedni state) → re-run wszystkich verifiers (cache hit dla niezmienionych) → nowy state → delta-engine generuje "Changes since last DD" → render'uje delta sekcję, reszta raportu bez zmian.
3. **Section re-run:** Load last_run.json → re-run tylko jednego task'a Parallel'a + odpowiednie manual verifiers → verdict pass tylko dla tej sekcji → section-renderer wymienia jedną sekcję w README.md.
4. **Comparison:** Load last_run.json dla 2-3 targetów → zbuduj hardcoded matrix kolumn (target, mechanism, TVL, team size, regulatory, top risks) → render markdown table.

### Polityka cross-checku — STRICT

- Claim dostaje **✅** tylko gdy: ≥2 niezależne źródła potwierdzają, w tym ≥1 non-Parallel (on-chain XOR legal registry XOR official docs).
- Konflikt między źródłami → **⚠️** + automatyczny entry w "Open questions".
- Brak źródeł → **❌** + entry w "Pytania do founders".
- Poprawiony pierwotny claim → **🔄** z dokumentacją starej wersji.
- Hard claimy zawsze przechodzą przez verdict-engine niezależnie od confidence Parallel'a — Parallel jest dodatkowym sygnałem, nie autorytetem.

### Hard vs soft taxonomia

- **Hard** (manual + strict): liczby (TVL, supply, revenue, koszty), ownership i cap table, regulatory status, team credentials, smart-contract risks, security incidents, "red flag" claimy, każdy claim który decyduje o invest.
- **Soft** (auto-tag dozwolony): mechanism narrative, historia produktowa, ecosystem context, opisowe tło, partnerships marketing-level, public roadmap claimy.
- Granica zdefiniowana w `claim-classifier` jako lista reguł per sekcja raportu — review'owalna bez czytania kodu.

### Skill modes

- `new` (default) — wizard + pełny pipeline. Tworzy strukturę katalogów, last_run.json, README.md.
- `refresh <target>` — re-run verifiers, delta-engine generuje DELTA section.
- `section <target> <section_name>` — punktowy re-run jednej sekcji z opcjonalnym custom focusem.
- `compare <target1> <target2> [<target3>]` — hardcoded matrix table.
- Resume przerwanego DD — POZA scope MVP, do dodania jeśli okaże się potrzebne po pierwszych runach.

### Wizard

- 4 pytania, wszystkie obowiązkowe, każde z sensownym defaultem ale bez auto-skip:
  1. Typ targetu (protocol/company/combined)
  2. Primary domain / website
  3. Primary chain + jurisdiction (auto-detect tylko jeśli analityk wybierze "skip")
  4. Tier kosztu Parallel (Lite/Base/Pro/Ultra)
- Implementacja przez AskUserQuestion w Claude Code (to samo UX co inne skille interactive).

### Budget i cache

- **Soft cap kosztu** wybierany w wizardzie razem z tier'em. Cost-guard abortuje pipeline przed pierwszym Parallel call'em jeśli preview przekracza cap.
- **Eskalacja w trakcie** — NIE występuje. Jeśli okaże się że potrzeba więcej, analityk re-runuje z wyższym tier'em ręcznie.
- **Cache backend** — plain JSON files na dysku w `pipeline/cache/`. Zero zewnętrznych deps.
- **TTL per namespace** — Parallel sections 7 dni, on-chain queries 1h, legal registry 30 dni, browser screenshots 7 dni.
- **Audit trail** — każde wywołanie Parallel logowane do `<target>/parallel-runs.jsonl` z (task_id, processor, koszt, timestamp).

### Output format

- **Parallel zwraca structured JSON per sekcję** raportu, zgodnie ze schemami w `task-group-builder`.
- **Manual verifiers zwracają structured JSON** o tym samym kształcie co Parallel (`findings: [{claim, source, evidence}]`).
- **Section-renderer** łączy oba w markdown przez template per sekcja.
- **last_run.json** to normalized state: `{config, parallel_findings, manual_findings, verdicts, rendered_sections}`.

### Out-of-band assumptions

- Wszystkie API keys w `.env` (gitignored), nigdy w repo.
- Skill nie commituje automatycznie — zostawia dirty working tree do review.
- Skill nie modyfikuje istniejących plików DD bez explicit refresh/section call'a.

## Validation Strategy

### Per komponent

- **verdict-engine** — testowany snapshot'ami: zestaw fixture'ów `(parallel_findings, manual_findings, claim_type) → expected_tag`. Pełna macierz: hard×soft × strict pass × konflikt × brak źródeł × Parallel-only. "Done" gdy snapshot suite obejmuje wszystkie 4 verdykty (✅⚠️❌🔄) dla każdej kombinacji hard/soft.
- **claim-classifier** — testowany na ground truth wyciągniętym z istniejących `sky-protocol/README.md` i `stablewatch/README.md`: każdy claim z tych raportów ma expected hard/soft. "Done" gdy ≥95% zgadzania się z ground truth.
- **task-group-builder** — test integracyjny na małym targecie (1-2 sekcje, tier Lite) z prawdziwym Parallel API. "Done" gdy zwraca valid Parallel Task Group spec i przetwarza response bez crashów.
- **delta-engine** — snapshot test: dwa fixture state JSON-y, expected markdown delta. "Done" gdy generuje wszystkie typy zmian (add/remove/modify) i ignoruje cosmetic differences.
- **section-renderer** — snapshot test per sekcja: section JSON → expected markdown. "Done" gdy każda sekcja z istniejących raportów może być re-renderowana z jej JSON-a 1:1 (modulo whitespace).
- **cache** — unit test: get/set/TTL expiry/namespace isolation. "Done" gdy concurrent access do tego samego key działa bez korupcji.
- **cost-guard** — unit test: preview vs cap, edge cases (0, exact match, over). "Done" gdy abortuje czysto z explicit message.
- **wizard** — manual smoke test w Claude Code. "Done" gdy 4 pytania zapisują valid config.json.

### End-to-end

- **Test E2E na realnym targecie**: Ethena Labs + USDe (combined), tier Base, soft cap $5. Skill wizard → pełny pipeline → review draftu. "Done" gdy:
  - Wszystkie 9 sekcji raportu są wygenerowane.
  - Każdy claim ma verdict tag.
  - Lista hard claimów wymaga manual review (skill flaguje je explicit).
  - Cost trackuje się w `parallel-runs.jsonl` i nie przekracza soft cap.
  - last_run.json pozwala na deterministyczny refresh.
  - Refresh tego samego targetu po 24h cost'uje <$1 (cache hit dla wszystkiego poza on-chain TTL 1h).
  - Section re-run jednej sekcji nie modyfikuje pozostałych.
  - Compare Ethena vs Sky generuje hardcoded matrix bez dodatkowych Parallel call'ów (wszystko z cache).

### Quality gates przed każdym DD commitem (rozszerzenie z planu)

- [ ] Wszystkie ✅ claimy mają primary source z URL i datą.
- [ ] Wszystkie ⚠️ claimy mają explicit warning + entry w "Open questions".
- [ ] Wszystkie ❌ claimy mają entry w "Pytania do founders".
- [ ] Hard claimy mają explicit "manually reviewed" marker (nie tylko Parallel confidence).
- [ ] On-chain numbers świeższe niż 1h.
- [ ] Cost summary dołączony do PR / commitu.
- [ ] last_run.json zacommitowany razem z README.md.
- [ ] `parallel-runs.jsonl` zacommitowany.
- [ ] Brak API keys w diff'ie.
- [ ] Wizard config zachowany w `<target>/config.json`.

## Out of Scope

- **Monitor API / continuous DD refresh** — opcjonalne, do dodania po MVP gdy okaże się że refresh manualny nie wystarcza.
- **CLI tool** — wszystko przez Claude Code skill na początku. CLI wrapper pojawi się gdy/jeśli skill'a będzie chciał używać ktoś poza Claude Code.
- **Resume przerwanego DD** — pominięte w wizardzie skill modes. Cache zapewnia większość benefitów resume bez dodatkowej logiki.
- **Auto-eskalacja tier'a w trakcie** — analityk wybiera tier upfront w wizardzie, brak heurystyki "ważnego targetu".
- **Auto-detect targetu z samej nazwy** — wizard zawsze pyta domain, nie próbujemy zgadywać z `dd uniswap` czy chodzi o v2/v3/v4.
- **Współdzielony cache między userami** — cache jest local-only, każdy ma swój własny.
- **Multi-user permissions / team workflow** — solo na start, multi-user dodajemy gdy pojawi się drugi user.
- **Auto-commit / auto-PR** — skill zostawia dirty working tree, analityk decyduje co commitować.
- **Wsparcie dla non-EVM chains poza Etherscan V2 supported list** — Solana, Cosmos, Bitcoin etc. poza scope MVP. Dodajemy adaptery gdy pojawi się konkretny target.
- **Tradycyjne fintech / niekrypto targety** — eksplicyt w planie, skill jest tylko dla DeFi protokołów i krypto-spółek.
- **Generowanie investment recommendation** — skill produkuje raport DD, NIE generuje "buy/sell/hold". Decyzja inwestycyjna pozostaje po stronie analityka.

## Further Notes

### Relacja do `plans/dd-methodology-rollout.md`

Ten PRD jest komplementarny:

- Tamten plan definiuje **strukturę repo, fazy implementacji, listę plików, templates**.
- Ten PRD definiuje **decyzje produktowe wokół Parallel.ai i UX skill'a**: jak działa wizard, polityka cross-checku, hard/soft taxonomia, skill modes, cache, budżet.
- Po zaakceptowaniu PRD: aktualizujemy `plans/dd-methodology-rollout.md` o nowe pliki (`pipeline/parallel/`, `pipeline/cross-check/`, `dd-research` SKILL.md, etc.) i rebalansujemy fazy A/B/C/D.

### Lessons learned z DD #1 które kształtują policy

- **PSM $1.64B vs $4.30B** → pokazuje że Parallel high-confidence nie wystarcza dla liczb. Stąd hard = manual.
- **Czarnecki 29.12.2025 wykreślony, LinkedIn dalej "Co-Founder"** → legal registry > LinkedIn. Stąd KRS/Companies House jako niezależny weryfikator.
- **PANews jako single source dla revenue breakdown** → STRICT cross-check policy z ≥1 non-Parallel.
- **"Annualized run-rate" ≠ revenue, "Coming Soon" ≠ in production** → claim-classifier musi być świadomy tych pułapek (lista reguł per sekcja).
- **Etherscan V1 deprecated** → wrapper na V2 z chainid jako fundament.

### Decyzje świadomie odroczone (do reki w trakcie implementacji)

- Konkretne JSON schema per sekcja raportu (Overview/Mechanism/Team/Risks/...) — ekstrahowane z istniejących raportów w trakcie implementacji section-renderer'ów.
- Heurystyka co dokładnie jest "konfliktem" w cross-check — startowo: różnica liczbowa >5% lub conflicting boolean, potem fine-tuning.
- Format `parallel-runs.jsonl` — startowy minimalny, rozszerzany on-demand.
- Konkretne TTL per namespace — startowo wartości z PRD, mierzymy real cost po 5-10 DD i kalibrujemy.
- Comparison matrix kolumny — startowa lista hardcoded (target, mechanism, TVL, team size, regulatory, top risks), iterujemy gdy okaże się że brakuje czegoś krytycznego.

### Decyzje wywodzące się z discovery

Pełen log decyzji + alternatyw odrzuconych jest w historii rozmowy `/ask:ask` która poprzedziła ten PRD. Najistotniejsze rozwidlenia rozstrzygnięte:

| Decyzja | Wybór | Odrzucone alternatywy |
|---|---|---|
| Rola Parallel | Warstwa równoległa + Task Group orkiestrator | Single primary engine, only specific tasks, full lock-in |
| Cross-check policy | STRICT ≥2 niezależne, ≥1 non-Parallel | Tiered, Parallel-only high-confidence, konflikt-as-warning |
| Hard/soft boundary | Wszystko co decyduje o invest = hard | Tylko liczby = hard, on-chain only = hard, cross-ref = hard |
| Output format | Structured JSON per sekcja | Markdown z meta-tagami, hybrid, full markdown draft |
| Entry point | Claude Code skill | Bash CLI, slash command, multi-entry |
| Cost backend | Soft cap manual + cache TTL | Auto eskalacja, no cap, hard cap stay-in-lane |
| Cache backend | Plain JSON files | SQLite, redis, in-memory |
| Skill modes | new + refresh + section + compare | + resume |
| Wizard input | Typ + domena + chain/jurisdiction + tier | Sama nazwa, nazwa+url, nazwa+url+typ |
| Parallel access | SDK/CLI | MCP plugin |
| Refresh delta | Structured JSON comparison | Markdown diff |
| Compare matrix | Hardcoded kolumny | Configurable schema |
| Eskalacja tier | Manual w wizardzie | Auto na "ważnych" targetach |

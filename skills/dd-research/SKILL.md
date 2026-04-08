---
name: dd-research
description: Run a due-diligence research pipeline on a DeFi protocol or crypto company. Cross-checks Parallel.ai research against independent verifiers (Etherscan V2 on-chain, legal registries, browser screenshots) using STRICT policy (>=2 sources, >=1 non-Parallel). Produces a structured report with verdict tags per claim, cost audit log, and deterministic last_run.json. Use when the user wants to start a new DD, refresh an existing one, re-run a single section, or compare 2-3 existing DDs. Modes -- new / refresh / section / compare -- match `dd-research <mode> ...` invocations.
---

# dd-research

## What this skill does

Orchestrates a DD research run that combines Parallel.ai Task Groups with
independent verifiers and writes a structured report plus audit artifacts to
`<slug>/{config.json, last_run.json, parallel-runs.jsonl, README.md}`.

The Python pipeline that does the heavy lifting lives in `pipeline/`. This
skill is a thin wrapper: it runs the wizard, calls `run_dd_new`, and reports
results.

## Prerequisites

Before running, verify:

1. `.env` exists in repo root with real values for:
   - `PARALLEL_API_KEY` — https://parallel.ai
   - `ETHERSCAN_API_KEY` — https://etherscan.io/myapikey
2. `uv sync` has been run (dev deps available).

If either key is missing the skill will fail fast with an explicit message
from `pipeline.env_check.require_env_vars`.

## Mode: `new` — start a fresh DD

When the user invokes `dd-research new` (or just `dd-research` with no other
mode), follow these steps:

### 1. Run the wizard via AskUserQuestion

Ask exactly these four questions using the AskUserQuestion tool. Each is
required — no skipping.

1. **Target type** — options: `protocol`, `company`, `combined`
2. **Primary domain / website** — free text, must contain a dot (e.g. `ethena.fi`)
3. **Primary chain + jurisdiction** — two sub-answers:
   - chain: `ethereum` / `arbitrum` / `base` / `optimism` / `polygon` / `skip` (auto-detect)
   - jurisdiction: ISO-3166 alpha-2 (`us`, `pl`, `ch`, ...) or `skip`
4. **Parallel tier + soft cap** — two sub-answers:
   - tier: `lite` / `base` / `pro` / `ultra`
   - soft cap USD: numeric, must be > 0

Pass all answers through `pipeline.wizard.validate_wizard_input` which returns
a `TargetConfig` or raises `WizardError`.

### 2. Show cost preview and confirm

Before the first Parallel call, estimate cost based on tier and number of
tasks (for the tracer bullet: 1 task, Overview/totalSupply). Show it to the
user explicitly:

> Estimated cost: $X.XX vs soft cap $Y.YY. Proceed?

If the user declines, exit cleanly without touching the filesystem.

### 3. Resolve the Overview claim manifest

Phase 3 runs the Overview section off a declarative JSON manifest, one per
target, at `targets/<slug>/overview_claims.json`. Each entry binds a Parallel
schema field to an optional on-chain fetcher spec (see
`pipeline/overview_claims.py` for the dataclasses and
`targets/frax-com/overview_claims.json` for a real example).

Resolution order:

1. **Manifest already exists** at `targets/<slug>/overview_claims.json` — use
   it as-is. Tell the user which file you found and show a one-line summary
   (`N claims, M cross-checkable, K Parallel-only`).
2. **No manifest** — ask the user how they want to bootstrap it:
   - **(a) Hand-edit** — create `targets/<slug>/overview_claims.json` manually
     following the shape in `targets/frax-com/overview_claims.json`, then
     re-run the skill. Exit cleanly; do NOT auto-run with an empty Overview.
   - **(b) Minimal tracer** — ask for a single primary-token address +
     decimals and write a one-claim manifest (total_supply only). This
     reproduces Phase 1/2 tracer behavior and is fine for a smoke test but
     will NOT satisfy Phase 3 acceptance.

In either branch, validate the manifest by loading it through
`pipeline.overview_claims.load_overview_claims(path)` before calling
`run_dd_new`. A JSON parse error or missing required field surfaces as a
`KeyError` / `json.JSONDecodeError` — re-raise so the user can fix the file.

Claim kinds come from the manifest, not from `claim_classifier`. Every
numeric claim (supply, TVL, revenue, balances) should be `hard`; narrative
claims (mechanism one-liner, ecosystem context) are `soft`. Hard claims
always carry `[MANUAL REVIEW NEEDED]` regardless of cross-check outcome.

### 4. Run the pipeline

Invoke `pipeline.orchestrator.run_dd_new` with:

```python
from pathlib import Path
import os
import urllib.parse
import urllib.request
import json

from pipeline.orchestrator import run_dd_new
from pipeline.wizard import validate_wizard_input


config = validate_wizard_input(
    target_type=target_type,
    domain=domain,
    chain=chain,
    jurisdiction=jurisdiction,
    tier=tier,
    soft_cap_usd=soft_cap_usd,
)


def http_get(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{qs}", timeout=30) as r:
        return json.loads(r.read().decode())


# Real Parallel client — swap for official parallel-web SDK once installed.
# For the tracer bullet, a thin wrapper around the REST API is enough.
from parallel_web import Parallel  # official SDK

parallel_raw = Parallel(api_key=os.environ["PARALLEL_API_KEY"])


class ParallelAdapter:
    def run_task(self, *, processor: str, schema: dict, prompt: str) -> dict:
        task = parallel_raw.task_run.create(
            processor=processor,
            input=prompt,
            output_schema=schema,
        )
        result = parallel_raw.task_run.result(task.id)
        return {
            "task_id": task.id,
            "cost_usd": result.metadata.cost_usd,
            "output": result.output,
        }


targets_root = Path.cwd() / "targets"
manifest_path = targets_root / config.slug / "overview_claims.json"
if not manifest_path.exists():
    raise FileNotFoundError(
        f"No Overview manifest at {manifest_path}. "
        "Create it by hand (see targets/frax-com/overview_claims.json) "
        "or opt into the minimal tracer path from step 3."
    )

result = run_dd_new(
    config=config,
    overview_claims_path=manifest_path,
    cost_preview_usd=cost_preview_usd,
    targets_root=targets_root,
    env=os.environ,
    parallel_client=ParallelAdapter(),
    http_get=http_get,
)
```

Note: the manifest must live inside the target directory because
`run_dd_new` creates `targets/<slug>/` on first run. If you're bootstrapping
a brand-new target, create the directory and write the manifest there
*before* calling `run_dd_new`:

```python
targets_root.mkdir(parents=True, exist_ok=True)
(targets_root / config.slug).mkdir(parents=True, exist_ok=True)
(targets_root / config.slug / "overview_claims.json").write_text(
    json.dumps({"claims": [...]}, indent=2)
)
```

### 5. Report back to the user

After `run_dd_new` returns, tell the user:

- **Section verdict** (`result.verdict_tag`) — ✅ / ⚠️ / ❌ aggregate across
  every claim in the Overview manifest. ❌ means at least one claim failed
  STRICT cross-check (usually because its on-chain verifier was missing or
  errored, or the claim is Parallel-only and STRICT requires ≥1 non-Parallel).
- **Target directory** (`result.target_dir`) — where all artifacts landed.
- **Manual review list** (`result.manual_review_claims`) — print every entry
  as a bullet grouped per section (e.g. "Overview — frxusd_supply [MANUAL
  REVIEW NEEDED]"). Expect every hard claim in here, even the ✅ ones —
  Parallel confidence is never a shortcut for manual review on numeric
  claims.
- **Warnings** (`result.warnings`) — print each as a prominent warning line.
  Covers (a) low Parallel confidence on hard claims and (b) any claim that
  failed STRICT cross-check. Claims that failed show up in the README's
  `## Pytania do founders` section with the rationale from verdict-engine.
- Point them at `<target_dir>/README.md` for the rendered report. Structure:
  a `| Metric | Value | Source |` table (one row per ✅/⚠️ claim) plus a
  `## Pytania do founders` section aggregating ❌ claims.
- Remind them that this is a **draft** — every hard claim (all numbers,
  ownership, regulatory status) still needs manual review before commit.
- Remind them the skill did NOT commit anything — working tree is dirty for
  their review.

## Mode: `refresh` / `section` / `compare`

Not implemented yet — these are Phases 6-8 of the implementation plan. If the
user asks for them, tell them the current skill only supports `new` and point
them at `plans/dd-research-implementation.md` for the roadmap.

## Quality gates (for every `new` run)

After `run_dd_new` succeeds, verify before handing off to the user:

- [ ] `<slug>/config.json` exists and matches wizard answers
- [ ] `<slug>/overview_claims.json` exists (was required for the run)
- [ ] `<slug>/last_run.json` exists and has a `verdicts` entry for **every**
      claim in the manifest
- [ ] `<slug>/parallel-runs.jsonl` has at least one line (unless cache hit)
- [ ] `<slug>/README.md` contains the `| Metric | Value | Source |` table
      and at least one source citation per ✅/⚠️ claim
- [ ] Every hard claim in the manifest appears in
      `result.manual_review_claims` (hard claims never auto-pass)
- [ ] Working tree is dirty (skill never commits)
- [ ] No API keys appear in any of the written files (grep for
      `PARALLEL_API_KEY`, `ETHERSCAN_API_KEY`, and the actual key prefixes)

## When things go wrong

- **`MissingEnvVars`** — tell the user exactly which vars are missing and point at `.env.example`
- **`CostCapExceeded`** — tell the user the preview vs cap and suggest raising the cap or switching to a cheaper tier
- **`WizardError`** — re-ask the specific question that failed with the validation message
- **`FileNotFoundError` on `overview_claims.json`** — the target has no
  manifest. Offer the user the two bootstrap paths from step 3 (hand-edit
  vs. minimal tracer). Do NOT silently create an empty manifest.
- **`KeyError` / `json.JSONDecodeError` while loading the manifest** —
  re-raise with the offending path; the user needs to fix the JSON before
  re-running (don't auto-repair)

Never catch and swallow errors. Let them surface so the user can fix
configuration before burning Parallel budget.

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

### 3. Ask for the primary token contract

The tracer bullet needs a primary ERC-20 to cross-check. Ask:

- Token contract address (0x...)
- Token decimals (usually 18)

In later phases the skill will auto-resolve this from the target config.

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


result = run_dd_new(
    config=config,
    token_address=token_address,
    token_decimals=token_decimals,
    cost_preview_usd=cost_preview_usd,
    targets_root=Path.cwd() / "targets",
    env=os.environ,
    parallel_client=ParallelAdapter(),
    http_get=http_get,
)
```

### 5. Report back to the user

After `run_dd_new` returns, tell the user:

- Verdict tag for totalSupply (`result.verdict_tag`)
- Target directory path (`result.target_dir`)
- Point them at `<target_dir>/README.md` for the rendered report
- Remind them that this is a **draft** — hard claims (any numbers, ownership,
  regulatory status) still need manual review before commit
- Remind them the skill did NOT commit anything — working tree is dirty for
  their review

## Mode: `refresh` / `section` / `compare`

Not implemented yet — these are Phases 6-8 of the implementation plan. If the
user asks for them, tell them the current skill only supports `new` and point
them at `plans/dd-research-implementation.md` for the roadmap.

## Quality gates (for every `new` run)

After `run_dd_new` succeeds, verify before handing off to the user:

- [ ] `<slug>/config.json` exists and matches wizard answers
- [ ] `<slug>/last_run.json` exists and has a `verdicts` entry for totalSupply
- [ ] `<slug>/parallel-runs.jsonl` has at least one line (unless cache hit)
- [ ] `<slug>/README.md` contains the verdict tag and both source citations
- [ ] Working tree is dirty (skill never commits)
- [ ] No API keys appear in any of the written files (grep for `PARALLEL_API_KEY`, `ETHERSCAN_API_KEY`, and the actual key prefixes)

## When things go wrong

- **`MissingEnvVars`** — tell the user exactly which vars are missing and point at `.env.example`
- **`CostCapExceeded`** — tell the user the preview vs cap and suggest raising the cap or switching to a cheaper tier
- **`WizardError`** — re-ask the specific question that failed with the validation message

Never catch and swallow errors. Let them surface so the user can fix
configuration before burning Parallel budget.

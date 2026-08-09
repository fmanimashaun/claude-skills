---
description: Set up and drive the curated asset library — scaffold config, read the brief, plan what the product needs, generate what is outstanding, and keep the plan honest as the product grows.
---

# `/design-flow:assets`

The setup and drive command for the asset library. **Re-run it whenever you like** — it resumes, it
never resets, and it tells you what moved.

Four files, four jobs, and confusing them is the trap:

| file | holds | written by |
|---|---|---|
| `.design-flow/generation.json` | how to buy — ladder, ceiling, briefs | you, once |
| `docs/assets/plan.json` | **what the product needs** | the seeding pass |
| `docs/assets/manifest.json` | **what the project owns** | each successful generate |
| `docs/assets/prompts-library/prompts.json` | **what was asked for, by which model, at what price** | each generate and each verdict |

The **gap between plan and manifest is the remaining work.** That is the whole reason both exist.

The prompt library is the fourth because those three answer *what is left*, *what exists*, and *how
to buy* — none of them answers **"have I bought this before, and was it any good?"**. Until it
existed the composed prompt was printed to stdout and lost, so a brand change meant paying again for
work already done. `prompts.md` is its generated human view; see `/design-flow:generate` §5.

## 1. Scaffold — safe to re-run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --scaffold --prd docs/PRD.md
```

Creates the config and an empty plan **only if absent**, and pins the brief so drift is detectable.
A second run re-pins the fingerprint and **changes nothing else** — a setup command that resets the
rows on re-run is not idempotent, it is destructive.

It also creates **both destinations, before the first `--run`**, so nothing has to invent a folder
mid-generation:

```
docs/assets/
├── plan.json          ┐
├── plan.md            ├─ the INDEXES — what is needed, what exists
├── manifest.json      ┘
├── assets-library/    → the finished artefacts (PNG / SVG / MP4)
└── prompts-library/   → prompts.json + its generated prompts.md
```

Each folder gets a `README.md` saying what belongs in it. That is not decoration: **git does not
track an empty directory**, so a bare `mkdir` would give the scaffolding machine a layout nobody
else who clones the project ever sees.

Assets generated before this layout stay where they are and keep working — the manifest holds
explicit paths, so nothing needs moving. Only new artefacts land in `assets-library/`.

The config lands with **`aggregator: "agent"`** and **no API key at all** — because the agent
generates: it calls a connected provider MCP (OpenRouter's `generate-image`) or authors SVG itself.
Nothing to configure, nothing to leak.

`--run` marks agent rows **`awaiting-agent`** with the composed prompt and a target path; fulfil each
and register it with `generate_asset.py --record`, which re-runs the whole gate before the manifest
accepts it. Those rows stay **outstanding** until a file exists.

A key is needed in exactly one case: an **unattended** run, where no agent is in the loop to call an
MCP. Set `api_key_env` and a non-agent `aggregator` then, and not before.

## 2. Read the brief and plan the set — before any coding

This is the judgement step, and it is yours.

1. **Read the PRD and the skills it produced.** What the product does, who for, how it should feel.
2. **Brainstorm broadly, then cut to one family** — one style, one palette, one level of
   abstraction. Eight good ideas in eight styles is the pile this whole path exists to avoid.
3. **Walk the product's surfaces** and write a row per asset, static and motion separately: a
   looping accent is a different artefact from the still it animates.
4. **Write a brief per surface** into the config's `briefs` map.

Each row needs `surface`, `kind` and **`why`**. `why` is the one that looks optional: a row nobody
can justify is a row nobody should pay for, and it is what makes the plan reviewable by someone who
was not in the room.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --check
```

It refuses an **empty** plan (unplanned is not finished), a row with no `why`, **two rows for one
surface+kind** (that forks the surface's look), and a row whose surface has **no brief** — that last
one moves a refusal from run time, after the spend, to review time, before it.

## 3. Run what is outstanding

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --run
```

Exit **0** everything done · **1** rows outstanding · **2** the plan is unreviewable, nothing ran.

- **Resumes.** A `done` row is never re-run, so a second pass never re-buys the library.
- **Records what happened, not what was attempted.** A row is `done` only once the file is on disk;
  a failure keeps the provider's or the gate's reason **verbatim**. Paraphrasing a refusal into
  "generation failed" is how a fixable config problem reads like a broken provider.
- **Refuses to run an unreviewable plan at all** — finding out a row had no `why` after the bill is
  the wrong order.

Outstanding rows on the first pass are normal: no key, no aggregator, or the ceiling. Read the
reasons, fix the named thing, run again.

## 3b. It costs the whole plan before it starts

`--run` totals every outstanding row **before generating anything**, and refuses (exit **2**) if the
budget cannot finish the plan:

```json
{
  "estimated_total_usd": 0.036,
  "remaining_usd": 0.02,
  "shortfall_usd": 0.016,
  "affordable_now": ["marketing-hero/static"],
  "would_not_fit": ["pricing/static", "empty-state/static"]
}
```

**Why refuse instead of generating until the money runs out?** Because that leaves an *arbitrary*
half of the set — whichever rows happened to be first. A half-built family of illustrations is not a
cheaper library, it is an incoherent one, and you cannot tell by looking which half is missing.
Choosing which half is the entire value, and it is a decision worth making deliberately.

Three honest caveats the output states rather than hides:

- **The estimate is a floor.** Every row is priced at the cheapest rung, because that is where rows
  start; one that fails its acceptance check and climbs costs more.
- **Rows with no `priority` were split by plan order.** That is an assumption, not a decision, and
  the run says how many rows it applied to. Set `priority` on the ones that matter.
- **`--spent` is yours to supply.** Nothing here can read your provider balance, so what you have
  already spent this cycle is an input. Passing nothing assumes nothing has been spent, which is
  right on a fresh cycle and wrong on a resumed one.

Then choose: raise `budget_usd`, drop or defer rows, or

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --run --confirm-partial --spent 0.00
```

which generates exactly what fits, by priority, and leaves the rest `planned` — not `failed`, because
they were never attempted and a later run should pick them up unprompted.

### An UNPRICED plan is refused outright, and `--confirm-partial` is not a way round it

Before any budget arithmetic, `--run` checks that every outstanding row's kind has a rung with a
`cost_usd`. If one does not, it refuses (exit **2**) and names the rows and kinds:

```json
{
  "unpriced_rows": ["promo/video"],
  "unpriced_kinds": ["video"],
  "priced_rows_total_usd": 0.04
}
```

This is deliberately **not** a budget comparison. A ceiling can only refuse a number, and the whole
problem with an unpriced row is that there is no number: it scores `$0.00`, fits inside every budget,
and arrives at the executor as the cheapest thing in the plan. `--confirm-partial` does not bypass
it either — "buy what the budget affords" is a decision about rows whose price is known, and there is
no partial answer for a row whose price is not.

The scaffold ships `video` unpriced on purpose, because the provider's model list does not report
pricing and an invented figure is worse than none. Look the price up, write `cost_usd` into
`ladders.<kind>`, and the plan runs.

## 3c. A table for the human, the JSON for the agent

`plan.json` is the right shape for the thing that runs the plan and the wrong shape for the person
who has to **review** it — which is the step the plan exists for.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --render
```

writes `docs/assets/plan.md`: one row per asset, with the surface, kind, status, group, priority,
per-row cost estimate, produced file and `why`. Unpriced rows are marked **unpriced** rather than
shown as `$0.00`, so the reason a run will refuse is visible in the document you read to decide.

It is **generated, never hand-maintained**. A hand-kept table is a second source of truth that
disagrees with the first within a week and disagrees *silently*, because a stale table still looks
like a table. So `--run` re-renders it after every change, and `--check` reports it as stale if it
drifts. It says nothing when the file is absent: the table is opt-in, and a check that demanded a
file the scaffold never creates would fail every project that does not want one.

## 4. Keep it honest as the product grows

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --status
```

Two kinds of drift, neither visible any other way:

- **The brief moved.** A library planned against last month's PRD is quietly incomplete — every row
  `done`, the status clean, and the new surfaces have no rows at all. The pinned fingerprint turns
  that silence into a sentence. Re-read the brief, add rows, re-pin.
- **An asset exists that nothing planned.** Which brings us to:

## 5. Generating outside the plan

An agent may hit a surface the seeding pass did not foresee and call
[`/design-flow:generate`](generate.md) directly. That is expected — the library grows by coverage.

**But it must then add the row to the plan**, with:

- **`why`** — the rationale: what the surface needed that nothing owned
- **`use_cases`** — where it may be used, so the next agent finds it instead of buying another
- **`avoid`** — where it must not go; the field people skip and the one that stops a curated family
  drifting by well-meaning reuse

`--check` and `--status` report any manifest entry with no plan row, so this is enforced rather than
requested. Skip it and the plan stops describing the library it exists to track, which makes the
plan-versus-manifest gap meaningless — and that gap is the only thing that tells you when the set is
actually finished.

## Verifying a change to this path

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_plan.py" --selftest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prompt_library.py" --selftest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prompt_library.py" --check    # is prompts.md still the library?
```

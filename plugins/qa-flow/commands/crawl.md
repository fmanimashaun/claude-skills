---
description: Crawl every route in a browser and judge it — broken pages, dead controls, theme-only failures. Writes evidence the Python judges grade.
argument-hint: "[routes...] — defaults to the routes in qa/routes.json"
---

# /qa-flow:crawl — $ARGUMENTS

Drive the real app across its routes and produce evidence three judges then grade. **The browser
measures; Python judges.** Every rule, threshold and marker lives in the Python — which is why those
have 79 fixtures between them and the collector has none, and why the whole thing is gateable in a CI
with no browser.

## 1. Boot the app the way it says to be booted

Read `qa/qa.config.yml`'s `app:` block (`start`, `port`, `health`, `boot_timeout`) and use it. **Do
not invent a boot command** — the project already declared one, and a second one drifts from it.
If a server is already listening on that port, reuse it rather than starting a second.

## 2. Collect

```bash
npm i -D playwright && npx playwright install chromium   # once, in the project

node "${CLAUDE_PLUGIN_ROOT}/scripts/crawl_collector.js" \
  --base "http://localhost:${PORT:-3000}" \
  --routes / /dashboard /settings \
  --out qa/manual-tests
```

**Run it from the repo root.** Playwright is resolved from your **project**, not from the plugin —
the script lives in the plugin cache, and ESM resolution would otherwise walk `node_modules` from
*there* and fail with `ERR_MODULE_NOT_FOUND` even with Playwright plainly installed (#356). `NODE_PATH`
does not help; it has no effect on ESM. If it cannot find Playwright it exits **2** and names the
directory it looked from.

Writes `qa/manual-tests/crawl.json` and `qa/manual-tests/interactions.json`.

Routes come from `qa/routes.json` when it exists (`route_coverage.py enumerate` builds it) — crawling
a hand-typed list is how a route nobody remembered stays untested forever.

## 3. Judge

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/crawl_report.py" qa/manual-tests/crawl.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/interaction_report.py" qa/manual-tests/interactions.json
```

Both exit 1 on findings, so they gate. Both also report what they could **not** judge — an
unreachable route, an unexercised control, an overlay whose dismissal probe never completed — and
neither counts any of that as clean.

### Focus restore, and the overlays it deliberately ignores

When a control opens a layer the collector presses **Escape** and records whether the layer closed
and whether `document.activeElement` is the trigger element itself. `focus-restore-missing` fires
on that, and **only for the patterns APG actually mandates it for** — a modal dialog, a `role=menu`
popup, a combobox popup. An ordinary disclosure (an FAQ accordion) and a standalone listbox are
measured, printed as **out of scope**, and never counted as findings: APG's Disclosure pattern has
no `Escape` row at all, so a rule keyed on `aria-expanded` would flag every accordion you ship.

This is the *measured* half of something `a11y-auditor` already reports. That agent counts
`Restore Failures` per overlay in its CSV and `validate_evidence.py` gates the CSV's arithmetic —
but that number is the agent's own claim. This one asks the browser.

## 4. Visual regression (opt in with `--visual`)

```bash
# 1. Python resolves which selectors are masked on which route (global + per-route, from the config)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/visual_baseline.py" --masks \
  --routes / /dashboard --config qa/qa.config.yml > qa/manual-tests/masks.json

# 2. The browser measures: screenshots with those regions painted over, plus a diff image per shot
node "${CLAUDE_PLUGIN_ROOT}/scripts/crawl_collector.js" --visual --seeded \
  --masks qa/manual-tests/masks.json \
  --base "http://localhost:${PORT:-3000}" --routes / /dashboard --out qa/manual-tests

# 3. Python judges the ratios
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/visual_baseline.py" qa/manual-tests/visual.json
```

Three steps rather than one because **which regions are dynamic is a policy decision and painting
over them needs a browser** — the same split as everywhere else here. Skip step 1 and the judge
**refuses the run** (exit 2) rather than comparing pixels the config says are live; it will not
report a number measured over content nobody meant to compare.

**`--seeded` is your assertion, not the tool's.** The collector freezes motion and the clock, pins
`deviceScaleFactor` to 1 and waits for `document.fonts.ready` — but it cannot seed your fixtures, and
without fixed data a pixel diff is a flake generator, which is worse than no check because it trains
people to ignore the one report that needs eyes. Omit the flag and the judge **refuses the run**
rather than reporting noise. That is the correct outcome for a caller who has not said the data is
fixed. All five determinism controls are recorded in the run and all five must be true, so a shot
whose fonts never settled is refused rather than reported as a page that changed entirely.

**A screen with no baseline is reported `new` — neither a pass nor a failure.** Treating it as a pass
would call a brand-new screen visually correct the day it is written, when nothing has been reviewed.
Treating it as a failure means every new screen breaks the build until someone raises the tolerance
to zero effect.

**Nothing here writes to `qa/baselines/`.** Candidates land in `qa/baselines/_candidates/`, diff
images in `qa/baselines/_diffs/`; promoting a candidate is your act. An agent that can overwrite a
baseline can launder a regression into the new truth in a single run.

**Every regression names its diff image** — changed pixels magenta over a faded greyscale of the
candidate. A ratio on its own is a number nobody can triage, and "31% changed" with nowhere to look
is what gets answered with a tolerance bump instead of a fix.

Tolerances and ignore regions live under a `visual:` block in `qa/qa.config.yml`:

```yaml
visual:
  max_diff_ratio: 0.002        # global tolerance
  /checkout: 0.0001            # per-route tolerance — longest matching prefix wins
  ignore:                      # masked on EVERY route
    - "[data-testid=clock]"
  ignore_per_route:            # masked on routes with this prefix, ADDED to `ignore`
    /dashboard:
      - .live-chart
```

**Tolerances override; masks accumulate.** A tolerance is one number and a route must be able to move
it in both directions, so the longest matching prefix wins. A mask is an assertion that a region is
dynamic, and naming a chart on `/dashboard` must not quietly unmask the clock there — so a route's
list is added to the global one. `--masks` prints exactly what resolved, per route, if you want to
check.

**An unreadable line inside `visual:` is refused, not defaulted.** `max_diff_ratio: loose` exits 2
naming the file and line, rather than falling back to 0.002 and judging every route against a
tolerance you never wrote.

## 4. Theme parity (a separate pass, deliberately)

Theme parity needs **two snapshots of the same route**, which is why it is not part of the crawl
above and not registered as a project gate: the single-path gate manifest cannot express a pair.

Use design-flow's conformance collector twice — once as rendered, once with the app's `dark` class
applied — then compare. It **consumes that snapshot and re-runs none of its rules**; one rule, one
owner.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/theme_parity.py" \
  tmp/conformance/dashboard-light.json tmp/conformance/dashboard-dark.json
```

## What this does NOT do, and where each lives instead

- **Layout, tokens, tap targets, overflow** → design-flow's `rendered_conformance.py`. It already has
  `tap-target-small` and `horizontal-overflow` as `drift` rules; re-implementing them here would be a
  second rule with a second owner, drifting from the first.
- **Accessibility auditing** → the `a11y-auditor` agent (axe + the keyboard pass).
- **Route coverage** → `route_coverage.py`. This crawl produces evidence; it does not decide what
  "covered" means.
- **Screenshots** → the visual-asset recipe. This collector deliberately takes none.

## Evidence and git

Everything lands under `qa/manual-tests/`. **This command performs no git operations** — it writes
evidence and reports; committing is the human's decision, per the qa-flow evidence contract.

With `--visual` there are three trees and only one of them is meant to be committed:
`qa/baselines/<viewport>-<theme>/` is the reviewed truth and belongs in the repo; `_candidates/` and
`_diffs/` are regenerated every run and should be gitignored. Promoting a candidate — copying it over
its baseline — is a human's act, and nothing in this plugin can do it.

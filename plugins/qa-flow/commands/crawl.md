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
unreachable route, an unexercised control — and neither counts that as clean.

## 4. Visual regression (opt in with `--visual`)

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/crawl_collector.js" --visual --seeded \
  --base "http://localhost:${PORT:-3000}" --routes / /dashboard --out qa/manual-tests
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/visual_baseline.py" qa/manual-tests/visual.json
```

**`--seeded` is your assertion, not the tool's.** The collector freezes motion and the clock itself,
but it cannot seed your fixtures — and without fixed data a pixel diff is a flake generator, which is
worse than no check because it trains people to ignore the one report that needs eyes. Omit the flag
and the judge **refuses the run** rather than reporting noise. That is the correct outcome for a
caller who has not said the data is fixed.

**A screen with no baseline is reported `new` — neither a pass nor a failure.** Treating it as a pass
would call a brand-new screen visually correct the day it is written, when nothing has been reviewed.
Treating it as a failure means every new screen breaks the build until someone raises the tolerance
to zero effect.

**Nothing here writes to `qa/baselines/`.** Candidates land in `qa/baselines/_candidates/`; promoting
one is your act. An agent that can overwrite a baseline can launder a regression into the new truth
in a single run.

Tolerances live under a `visual:` block in `qa/qa.config.yml` — a global `max_diff_ratio` and
per-route overrides, longest matching prefix wins:

```yaml
visual:
  max_diff_ratio: 0.002
  /checkout: 0.0001
```

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

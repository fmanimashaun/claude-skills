---
description: Crawl every route in a browser and judge it — broken pages, dead controls, theme-only failures. Writes evidence the Python judges grade.
argument-hint: "[routes...] — defaults to the routes in qa/routes.json"
---

# /qa-flow:crawl — $ARGUMENTS

Drive the real app across its routes and produce evidence four judges then grade. **The browser
measures; Python judges.** Every rule, threshold and marker lives in the Python — which is why each
judge carries a `--selftest` and a declared mutation while the collector carries neither, and why the
whole thing is gateable in a CI with no browser. (A fixture count used to sit here. It was stale, and
nothing could have told you — run `--selftest` on each judge for the real one.)

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

## 4. Broken links and missing assets (opt in with `--links`)

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/crawl_collector.js" --links \
  --base "http://localhost:${PORT:-3000}" --routes / /dashboard --out qa/manual-tests
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/link_audit.py" qa/manual-tests/links.json
```

**This is the pass that looks at what your pages link TO.** Everything above judges the routes you
listed; a footer link to `/pricng` is not in `qa/routes.json`, so nothing else ever visits it. The
collector inventories every `href`, every fragment target, and every sub-resource that answered
4xx/5xx, then probes each distinct **same-origin** target once — once, not once per page, so a
footer link across 72 pages costs one request.

**A 404 sub-resource is not a failed request**, which is why `crawl.json`'s `failedRequests` does not
already cover it. Playwright fires `requestfailed` for network-level failures only: *"HTTP error
responses, such as 404 or 503, are still successful responses from HTTP standpoint, so request will
complete with `requestfinished`"*. A `<img src="/logo-old.png">` returning a well-formed 404 is
invisible to a status check and to the request-failure log alike.

**A 401 or 403 target is reported `unverified`, not broken.** The crawl is unauthenticated, so an
auth-gated page is unknown; calling it dead would flood the report and get the rule switched off.
Same for any target no probe reached. Neither counts as a pass — both are named on every run.

**`#` and `#top` are silent, `#topic` is not.** Both of the first two are the top of the document per
the HTML Standard with no matching element required. A fragment that matches no `id` and no `a[name]`
— on this page or on another page the crawl inventoried — is a `dead-fragment`.

One broken target is **one finding** with a page count and up to three example routes, never one per
page (#118). External origins and `mailto:`/`tel:`/`javascript:` links are counted and not followed —
the scheme is read from the start of the `href`, so `/contact?to=mailto:x@y` is an ordinary internal
link and is still judged.

## 5. Visual regression (opt in with `--visual`)

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

## 6. Theme parity (a separate pass, deliberately)

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
  "covered" means. `link_audit.py` will tell you a linked target was never probed; deciding that a
  route is untested is still that tool's job.
- **Whether a linked page is itself broken** → `crawl_report.py`. `link_audit.py` judges the link;
  the page it lands on has an owner already, which is why a `document` 4xx is skipped there.
- **Screenshots** → the visual-asset recipe. This collector deliberately takes none.

## Evidence and git

Everything lands under `qa/manual-tests/`. **This command performs no git operations** — it writes
evidence and reports; committing is the human's decision, per the qa-flow evidence contract.

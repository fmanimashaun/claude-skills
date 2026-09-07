---
description: Independent QA verification after a feature merges to dev — smoke gate, sanity, and targeted regression to prove the change broke nothing previously certified
argument-hint: "[PR number or feature slug]"
---

<!-- topology: parallel
     merge: any layer reporting an S1/S2 outranks every PASS — a clean run from one agent is never
            evidence against another's defect. The same defect found by two layers is ONE defect
            (dedupe on route + assertion), reported with the layers that saw it. -->

# /qa-flow:verify — $ARGUMENTS

Fires after a feature PR merges into dev. QA's question here is NOT "does the new
feature work" (the developer flow proved that) — it is "did this change break
existing, previously-certified behavior?" Independent toolchain, black-box, against
the running app.

## Phase 0 — Environment

Read the PR documentation for `$ARGUMENTS` (`gh pr view`), CLAUDE.md, and
`qa/` config. Ensure a testable target: run **`/qa-flow:smoke`** to boot the app in a QA/test
environment and liveness-check it — it sets `QA_BASE_URL` — or point at a provided URL. If the
app won't boot, STOP here: "dev build not testable" → file the breakage (S1); the deeper phases
can't run against an app that isn't up. If `qa/` is not scaffolded, tell the user to run
`/qa-flow:setup-qa` first.

## Phase 1 — Smoke gate (build verification)

With the app proven up (Phase 0's `/qa-flow:smoke` confirmed boot + key routes), `e2e-tester`
runs the fuller `@smoke` set against `QA_BASE_URL`. If it fails, STOP: the build is not
verifiable — report "smoke failed, dev build not testable" and file the breakage (S1). No point
testing further.

## Phase 2 — Plan (blast radius)

`qa-lead` produces the verify plan: sanity targets + regression selection. The
mechanical blast-radius floor runs autonomously; if the change touches
**auth, tenancy, money, migrations, or a shared concern**, present the regression
selection for approval before executing.

**Blast radius needs a denominator (#119).** "Select the affected routes" is judgement over an
unknown set unless you know what the routes *are*, so refresh the route inventory and read the
coverage gap before selecting:

```bash
bin/rails routes > qa/reports/routes.txt   # or --sitemap / --fs for other stacks
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/route_coverage.py" enumerate --rails qa/reports/routes.txt
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/route_coverage.py" report \
  --evidence qa/manual-tests --evidence qa/reports --json
```

Coverage is attributed from the **already-validated** evidence CSVs, so a route counts as covered
only when a row that passed `validate_evidence.py` says a pass went there. When the change touches a
controller, its routes are in `qa/reports/routes.json` — and the ones the report lists as untested
are the selection you would otherwise have guessed at. **Untested non-GET and authenticated routes
rank first**, because an untested route that changes state is the worst kind to leave uncovered.

A gap is **not** a failure of the run: it is the deliverable, and `report` exits 0 with one. Use
`--fail-on-untested` only once a team has reached full coverage and wants to hold it.

**`enumerate` exits 2 rather than write a partial route file.** Rails prints a route's `defaults:`
after the controller, and the parser used to require the controller to be the last token — so on a
real app 64 of 143 verb-bearing rows were dropped in silence and coverage reported *"49/49 (100%)"*
over a denominator that contained none of the pages its defects were on. Any verb-bearing row the
parser cannot read is now printed and the run refuses: a percentage over an incomplete route table
is a confident claim about a different application.

### Coverage has a second axis: measured at a small viewport

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/route_coverage.py" report \
  --evidence qa/manual-tests --evidence qa/reports --json
```

```
route coverage:      65/113 (57%) — 48 untested
responsive coverage: 4/94 (4%) measured at ≤480px — 90 never measured small (GET-like routes only)
```

Those are two answers to two questions and they are never averaged. "Covered" means a validated pass
asserted something about the route; it says nothing about the **width** that pass ran at. Downstream
the difference was total: a suite reported every route covered while 71–83% of every data table was
hidden at a phone width.

The evidence is `layout.json`, from `crawl_collector.js --layout --viewport 390x844` (see
`/qa-flow:crawl` §3a). Three ways a route appears in it and still does not count, because each is
the difference between measuring a route and reporting an unmeasured one as measured:

- the probe threw (`elements: null`) — not measured;
- it landed somewhere else (`landedOn` ≠ the route) — the measurement belongs to that somewhere else;
- the viewport was wider than the boundary — a desktop measurement, which is the state this axis
  exists to distinguish from no measurement at all.

**Non-GET routes are not in the denominator.** A layout probe navigates with `page.goto`, which is a
GET, so a `DELETE /users/:id` cannot be measured at any width and counting it would make the axis
permanently unreachable.

Declare the boundary and any exclusions in `qa.config.yml`:

```yaml
coverage:
  small_viewport_max: 480     # the width at or below which a measurement counts as small
  responsive_exclude: []      # routes excluded from THIS axis only, printed like every suppression
```

`--fail-on-unmeasured` gates this axis alone, separately from `--fail-on-untested`, because the two
are reached at different times and one flag would make the easier one hostage to the harder.

**Then DERIVE the radius rather than reasoning it out (#134).** The route table is the
denominator; `blast_radius.py` is the selection. It reverse-walks the architecture graph
(`/rails-flow:graph`, #141) from the changed files to their **dependents**, maps those onto the
route table and onto conventional spec paths, and prints the justifying edge for every inclusion:

```bash
git diff --name-only "$(git merge-base origin/main HEAD)"..HEAD > qa/reports/changed.txt
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/blast_radius.py" derive \
  --changed-from qa/reports/changed.txt \
  --graph docs/architecture/graph.json \
  --routes qa/reports/routes.json
```

Read the exit code, do not just skim the output:

| exit | meaning | what you do |
|---|---|---|
| 0 | targeted scope derived, every changed file accounted for | select autonomously, attach the report to the plan |
| 1 | **wide** — a risk axis fired and/or a changed app file could not be accounted for | present the selection for approval **before** executing, exactly as the rule above says |
| 2 | unusable — no changed-file list, or an input that could not be read | fix the input; a check that did not run is never a pass |

Three properties are worth knowing before you argue with it:

- **`--graph` is optional.** With no graph artefact the derivation falls back to Rails conventions
  and says so in its `derived from:` line. It is useful on day one, on any Rails project, with no
  graph tool installed. When `graphify`/`code-review-graph` output has been folded into the graph,
  the tool is **named in the report** and every edge it contributed is labelled `[via <tool>]`;
  `--no-enrichment` reproduces the bare-runner walk. The verdict is the same either way.
- **It is a FLOOR, never a ceiling.** The graph extractor is regex-based, so metaprogrammed
  structure is invisible to it — the graph's own `notes` are reprinted in the report for that
  reason. Use a computed radius to justify **widening** a scope; never cite it to shrink one below
  the certification baseline.
- **Nothing narrows silently.** Every route not selected, every node past `--depth`, every changed
  file excluded as non-app code, and every conventional spec path that does not exist is printed
  with its reason — including when the list is empty.

## Phase 3 — Targeted execution (parallel where possible)

Per the plan, dispatch: `e2e-tester` (sanity + selected `@regression` charters,
chromium), `api-contract-tester` (touched endpoints + authz matrix) if the API
changed, `a11y-auditor` if views changed, `perf-tester` (k6 smoke thresholds if hot
paths changed; the client-side capture over the same touched routes whenever views
changed — on chromium, and in its own fresh context per route, since a warm cache
makes the byte totals fiction), `exploratory-tester` (1-2 light charters). Skip layers
the change can't affect and say so.

## Phase 4 — Report & defects

`qa-reporter` consolidates the report and files each defect as a
`qa,from-qa,severity:sN` issue.

**Consolidating a fan-out needs two rules, not one, and only the verdict rule was ever written
down.** Phase 3 dispatches up to five agents over overlapping surfaces, so:

- **Precedence.** Any layer reporting an S1/S2 outranks every other layer's PASS. A clean run from
  `e2e-tester` is not evidence against a defect `exploratory-tester` found — they looked at
  different things. Silence from a skipped layer is not a PASS either; say it was skipped.
- **Dedupe.** The same defect seen by two layers is **one** defect, keyed on route + failing
  assertion, reported with every layer that saw it. Two *similar-looking* defects on different
  routes are two. Filing one issue per layer inflates the count and makes the fix queue lie.

Verdict:
- **PASS** → the feature is cleared; report it, next feature may proceed.
- **FAIL** → the feature is NOT cleared. Defects flow to `/rails-flow:issues
  label:qa` for fixing through the developer flow; verify re-runs until PASS. No
  next feature meanwhile. This is the feature->dev quality gate.

Verify never writes the certification stamp — only /qa-flow:certify does.

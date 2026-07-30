---
description: Independent QA verification after a feature merges to dev — smoke gate, sanity, and targeted regression to prove the change broke nothing previously certified
argument-hint: "[PR number or feature slug]"
---

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

## Phase 3 — Targeted execution (parallel where possible)

Per the plan, dispatch: `e2e-tester` (sanity + selected `@regression` charters,
chromium), `api-contract-tester` (touched endpoints + authz matrix) if the API
changed, `a11y-auditor` if views changed, `perf-tester` (smoke thresholds) if
hot paths changed, `exploratory-tester` (1-2 light charters). Skip layers the change
can't affect and say so.

## Phase 4 — Report & defects

`qa-reporter` consolidates the report and files each defect as a
`qa,from-qa,severity:sN` issue. Verdict:
- **PASS** → the feature is cleared; report it, next feature may proceed.
- **FAIL** → the feature is NOT cleared. Defects flow to `/rails-flow:issues
  label:qa` for fixing through the developer flow; verify re-runs until PASS. No
  next feature meanwhile. This is the feature->dev quality gate.

Verify never writes the certification stamp — only /qa-flow:certify does.

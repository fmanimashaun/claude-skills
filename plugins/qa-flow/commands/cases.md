---
description: Author and maintain the in-repo test-case catalogue (qa/test-cases.csv) from the PRD, app surface, qa-lead plan, and past defects. Automates the repetitive case-writing/upkeep; stable IDs, idempotent, Excel-openable. Free, no online tool.
argument-hint: "[feature slug | menu/area | issue #n | all]"
---

# /qa-flow:cases — $ARGUMENTS

Automate the tedious part of QA — writing and maintaining test cases. Delegates to the
**case-author** agent, which derives cases and keeps `qa/test-cases.csv` in sync.

## Scope

- `$ARGUMENTS` a **feature slug / menu area** → author/update cases for just that area.
- an **issue `#n`** → add regression case(s) for a fixed defect (`Source: defect:#n`).
- **`all`** or empty → full reconcile of the catalogue against current requirements + app
  surface.

## What it does

Reads the PRD/`docs/`, the app's menu/routes/OpenAPI, the latest `qa/plans/*`, and
`docs/brain/` defects; diffs against the existing `qa/test-cases.csv`; then **adds** new
cases (next stable `TC-###` ID), **updates** changed ones in place, and **deprecates**
(never deletes) cases for removed behaviour. Assigns Area/Type/Priority/Source. Idempotent —
re-run any time; the change shows up as a reviewable `git diff` of `qa/test-cases.csv`
(and the optional `qa/test-cases.md` human view).

## Notes

- **Free & repo-local** — the catalogue is a CSV in the repo (opens in Excel); no Testmo or
  other online case manager required. A Testmo export can seed it, but the file is the
  source of truth.
- Feeds **`/qa-flow:functional`**, which executes these titles via Playwright MCP and writes
  its evidence report back into `qa/manual-tests/`.
- Run `/qa-flow:setup-qa` first if `qa/` isn't scaffolded yet.

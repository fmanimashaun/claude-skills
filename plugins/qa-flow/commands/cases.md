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

## Requirements get a case (the owner's rule, #1853)

When `qa/requirements.yml` exists, every requirement that is not an owner decision must be named, by id, in the `Source` column of an **Active**
case, or sit on the shrinking baseline. List what is missing, then author a case for each and put the requirement id in its `Source`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_requirements.py" --uncased   # the ids with no active case
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_requirements.py"             # the gate: exit 0 when none are missing
```

A case for a requirement states how to prove its intent by hand; it is not a copy of the requirement. Never put an id in `Source` for a case that does
not prove it, and never delete a baseline line to make the gate pass: the line goes when a case names the requirement.

## Notes

- **Free & repo-local** — the catalogue is a CSV in the repo (opens in Excel); no Testmo or
  other online case manager required. A Testmo export can seed it, but the file is the
  source of truth.
- Feeds **`/qa-flow:functional`**, which executes these titles via Playwright MCP and writes
  its evidence report back into `qa/manual-tests/`.
- Run `/qa-flow:setup-qa` first if `qa/` isn't scaffolded yet.

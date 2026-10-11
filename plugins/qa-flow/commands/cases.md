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

Put ids in `Source` separated by a space, comma, semicolon or pipe; `REQ-001/REQ-002` (a slash) names neither. The catalogue may be saved from Excel (a BOM is read).
The registry's `# rows: N` header must equal its entry count and the baseline's `# size: N` its line count, so a requirement or a baseline line cannot be added or
dropped unseen; the shipped check compares the baseline with the base branch, so it cannot grow against it. The base is `base:` under `requirements:` in `qa/qa.config.yml`
(default `origin/dev`; a project on `main` sets `base: origin/main`). A missing default base is a printed note and exit 3 (a skip), a configured one that cannot be
read is exit 2, and a base with no registry and no baseline yet (the first adoption) skips the growth check with a note.

A requirement that is a **feature** carries `feature: true` in the registry and needs an end-to-end spec too: its id appears in a test title, a describe title or a tag of an active
Playwright test, and some runner actually selects that test (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_e2e_paths.py"`). The runners are the files listed under
`e2e_paths: runners:` in `qa/qa.config.yml` (a shell script or a `package.json` that runs `playwright test`). The check does not re-implement Playwright's filtering: it runs each
runner's command with `--list --reporter=json` (the project's own `npx --no-install playwright`, from the config's directory or `e2e_paths: cwd:`) and reads which tests Playwright
says it would run. The runner's literal environment (`QA_TARGET=image npx playwright test`, an earlier `export QA_TARGET=image`) is applied to the listing, since a config can read it. A command it cannot execute safely (an
argument built from a shell variable, one inside an `if` or a function, one after an `exit`, a heredoc or an unexplained `cd`, an environment value that is not a literal, a `source` or `.` line, `--only-changed`, `--last-failed`) or a Playwright that cannot be run makes the verdict "could not check" (exit 2, which the project gate runner grades ERROR; exit 3 would be graded not applicable and never fail), never a pass. A feature with no selected test is on
`qa/e2e-unselected-baseline.txt` (shrink-only, like the uncased baseline) or a finding.

A case for a requirement states how to prove its intent by hand; it is not a copy of the requirement. Never put an id in `Source` for a case that does
not prove it, and never delete a baseline line to make the gate pass: the line goes when a case names the requirement.

## Notes

- **Free & repo-local** — the catalogue is a CSV in the repo (opens in Excel); no Testmo or
  other online case manager required. A Testmo export can seed it, but the file is the
  source of truth.
- Feeds **`/qa-flow:functional`**, which executes these titles via Playwright MCP and writes
  its evidence report back into `qa/manual-tests/`.
- Run `/qa-flow:setup-qa` first if `qa/` isn't scaffolded yet.

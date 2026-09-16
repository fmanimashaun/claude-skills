---
description: Walk every persona's whole journey in a live browser — every page, every action, every hand-off to the next persona, at three widths — judged against the spec's intent, not a case title. Finds what no scripted layer has a case for.
argument-hint: "[persona ...] — defaults to every persona in qa/qa.config.yml → walkthrough.personas"
---

<!-- topology: sequential -->

# /qa-flow:walkthrough — $ARGUMENTS

`journey-walker` drives the running app persona by persona and files what it finds through
`qa-reporter`. This is the layer for defects that live **between** personas and **beneath** a 200:
an applicant sent to a placeholder with no route onward; a thread that says *signed* over an
*issued* contract; a mail the catalogue names and nothing sends; a modal that clips at 700px. On
the app this was measured against, thirty such defects sat under a green 230-test suite.

## Phase 0 — Refuse to walk blind

The walk is only as good as what it is judged against, so the command **stops** unless the project
has declared its personas, sign-in recipes and journey documents:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/walkthrough_plan.py" --config qa/qa.config.yml > qa/reports/walkthrough-plan.json
```

Exit `2` prints every finding — no `walkthrough:` block, a persona with a sign-in recipe the plugin
cannot drive, a journey file that does not exist, viewports that miss one of the three bands — and
the command ends there: tell the engineer what to declare (the schema is in `/qa-flow:setup-qa`) and
stop. A plan that cannot be produced is not a plan to improvise.

The rubric is the design doctrine as well as the project's spec, and that doctrine ships in another
plugin: `skills/design-system/references/` (page anatomies, responsive bands, components, forms)
must be readable — it arrives with `rails-stack`. If it is absent, say which plugin is missing
**and stop**; a walk judged against no doctrine files taste as findings.

Then confirm a testable target the way `/qa-flow:smoke` does: reuse the server already listening on
the configured port, or boot it as `app.start` says; run the project's freshness check if it has
one. Record the sha under test — every issue carries it.

## Phase 1 — Walk

Dispatch `journey-walker` with the plan. Scope `$ARGUMENTS` to a subset of personas when given;
the default is every persona, every viewport, every journey document. The agent's own doctrine
governs how it signs in, what it records per page, how it switches persona at every hand-off, how
it reads the dev inbox, and which stand-ins it may run (`reference/stand-ins.md`).

## Phase 2 — Validate, then report

The two new evidence profiles are gates, not suggestions — a hand-off marked `Missing` without a
screenshot, or a notification marked `Sent` with nothing observed, is refused before anything is
filed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_evidence.py" docs/evidence/qa/<date>-walkthrough/handoffs.csv
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_evidence.py" docs/evidence/qa/<date>-walkthrough/notifications.csv
```

Then `qa-reporter` consolidates: one row per page per width, one per hand-off, one per expected
notification, the stand-ins listed, then the deduplicated findings with `Source` = `journey`, and
one issue per distinct defect with facts, reproduction, severity, acceptance criteria and the
embedded screenshot. Each issue names the spec section the page was judged against.

## What this is not

- **Not a replacement for `e2e-tester` or `functional-tester`.** Those regress what is known; a
  confirmed finding here leaves with a `@regression` charter for `e2e-tester`, so it never needs
  discovering again.
- **Not a code editor.** `journey-walker` never touches `app/`; a stand-in is a declared model call
  run through the project's runner and named in the report.
- **Not device emulation.** Three viewport bands, per `responsive.md` §4 — compact, medium,
  expanded — not a device list.

## Evidence and git

Evidence lands under `docs/evidence/qa/<date>-walkthrough/` on a branch of that name made in a
`git worktree`, so the walk never sits on the working branch. Committing and pushing are two
commands, never one; and they are the agent's act on that branch only — this command performs no
git operation on the branch you are on.

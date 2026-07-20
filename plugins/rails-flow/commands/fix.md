---
description: Systematically fix a bug or a phased review backlog — one issue at a time, each proven by a spec
argument-hint: <bug description | path to review report | phase number>
---

# /rails-flow:fix — $ARGUMENTS

Fix work follows the same discipline as features, with two entry modes.

## Setup

Read `CLAUDE.md`, `GUARDRAILS.md`, and — if `$ARGUMENTS` references a review report —
that report (e.g. `docs/reviews/*.md`). Identify the next phase marked "Not started",
or treat the described bug as a single-phase fix. Base branch: `dev` if present.

## Principles (non-negotiable)

1. **Implement, don't comment.** A TODO is not a fix.
2. **One issue at a time**: read → implement → test → verify no regression → commit.
3. **Bugs are reproduced before they are fixed**: write the failing spec that demonstrates
   the bug FIRST, then make it pass. The spec is the proof and the regression guard.
4. **Every behavioral change gets a NEW spec proving the new behavior.** Passing the
   existing suite only proves you didn't break old behavior.
5. **Never introduce a regression**: if a fix touches scoping or authorization, check every
   caller; verify legitimate users still pass and unauthorized ones still fail.
6. **Verify the fix addresses the reported issue** — re-read the reported line/method after
   editing and confirm it actually changed.

## Workflow (per phase)

```
1. BRANCH:    git checkout <base> && git pull && git checkout -b fix/<phase-or-slug>
2. IMPLEMENT: the loop above, one issue per commit; delegate big items to rails-developer,
              schema changes to migration-writer
3. VERIFY:    test-runner → FULL suite, 0 failures; code-reviewer → VERDICT: CLEAN
4. PUSH + PR: gh pr create --base <base> --title "fix: <phase — summary>"
5. GATE:      review-pr skill if the code-review-graph CLI + graph are present
              (command -v code-review-graph && [ -d .code-review-graph ]), else
              pr-reviewer — repeat until CLEAN
6. CLOSEOUT:  /rails-flow:pr-comments <n> — every review thread fixed on-branch or
              folded into a tracked repo issue; re-run the gate if code changed.
              A PR must close clean before the next phase starts.
7. MERGE:     on CLEAN, merge to dev (squash); default-branch bases stop for the user
8. DOCS:      doc-updater; mark the phase done in the review report
```

Then report: issues fixed, specs added, gate verdicts, PR link, next phase remaining.

## Unattended operation

The whole backlog can run without a human in the loop:
`/goal all phases in <report path> are marked done — work them with /rails-flow:fix,
one phase at a time`. The guardrail hooks, stop gate, and non-skippable merge review
keep autonomy inside the rails: no destructive git/db operations, no unproven
behavioral changes, nothing past `dev` without a CLEAN tool verdict.

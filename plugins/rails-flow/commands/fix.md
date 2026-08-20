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

**When a `findings.jsonl` sits beside the report, read that instead — it is the source and the
markdown is a rendering of it** (#138). Take the fix order from the data rather than from the
prose:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" order docs/reviews/<date>/findings.jsonl
```

**The order is topological, and an edge outranks severity** — a P1 symptom appears *after* its P3
cause, deliberately. Do not "correct" that back to severity order: fixing a symptom before its cause
is wasted work, and the graph is the only place that relationship is recorded. If the command
reports a **cycle**, it fell back to severity for those ids and said so — that usually means a
mutual `caused_by` someone should look at, not something to route around.

A record's `signature` groups duplicates, so one fix may close several ids. Say which ids a fix
covers; that is what lets the completeness check pass later.

**File first if it isn't filed.** If this defect surfaced live in conversation (the user was
reviewing the running app) and no repo issue exists for it, **file it before touching code** —
`gh issue create` with the repro, expected vs actual, and `file:line` if known — then work it from
that issue. If **several** defects surfaced in one sitting, file them **all** (one issue each,
batched in a single pass), then work them **one at a time**, each on its own branch → PR, each
proven by a spec. Never accumulate multiple unrelated fixes on one branch, and never hot-fix
straight onto an existing feature branch just because it's checked out — that's the ad-hoc path
this flow exists to prevent. Say which issues you filed before you start fixing.

## Phase 0 — classify the failure before you debug it (#647)

**Not every problem is a bug. Not every bug needs debugging.** Name the failure type and the evidence
that chose it, in one line, before touching code. The classification goes in the report, so a wrong
call is visible in review rather than buried in a transcript.

| type | the tell | first move | what debugging it costs |
|---|---|---|---|
| **defect** in our code | reproduces from a clean checkout at the stated commit | reproduce → criterion → failing spec → fix | correct |
| **environment** | fails before any of our code runs: a missing key, a stale bundle, the wrong Ruby | fix the environment, then re-run | hours reading correct code |
| **wrong expectation** | the test asserts something no doctrine or criterion ever promised | fix the test, or the doctrine — decide which | a "fix" that breaks correct behaviour |
| **upstream** | reproduces in a minimal script with our code removed | pin, work around, report upstream — **and stop** | unbounded; there is no natural end |
| **flake** | passes in isolation, fails in a suite; or depends on order, clock or a shared fixture | make it deterministic — **do not change the logic** | a chased ghost, and it returns |

**The last two are the expensive misclassifications.** Debugging our own code for an upstream bug has
no stopping point. "Fixing" a flake by editing correct logic makes it worse and hides the real cause.
So both rows say **stop** rather than *continue carefully*.

**This stays advisory.** Classifying is judgement, and this repo's record on gating judgement is
explicit: `#476` proposed four monotony axes for `check_page_pacing.py` and the measurement killed
them, because the threshold flagged **our own** worked example — *"a gate that needs a carve-out on
its first real input is taste wearing a count."* A gate on *"is this really a flake?"* earns the same
fate. What is mechanical is that a classification was **stated**, which is the shape
`check_criteria.py` already uses: it requires criteria to exist without judging whether they are good.

**It is not `/rails-flow:escalate`.** That is the async human-in-the-loop — it asks a human a question
on a GitHub issue, parks the thread, and moves on. Use it when a decision is not yours to make. This
happens earlier and usually needs no human at all: it decides **what kind of problem you have**
before choosing how to respond.

## Principles (non-negotiable)

1. **Implement, don't comment.** A TODO is not a fix.
2. **One issue at a time**: read → implement → test → verify no regression → commit.
3. **Bugs are reproduced before they are fixed**: write the failing spec that demonstrates
   the bug FIRST, then make it pass. The spec is the proof and the regression guard.
   **State the criterion before the spec.** For a fix, the criterion IS the bug report made
   falsifiable — record it in `docs/acceptance/<phase-or-slug>.md` before touching code:

   ```md
   ## Wrong-tenant invoice leak
   - **AC-1** Given a user in tenant A, when they GET /invoices/<id-in-tenant-B>, then the
     response is 404 and no invoice number appears in the body [error]
   ```

   A bug fixed against a criterion written afterwards proves only that the code changed. Note
   a fix's criteria are usually error-path by nature, which the required error path suits.
   Validate with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py" "docs/acceptance/<slug>.md" --specs spec`;
   the spec cites the id (`it "AC-1 denies cross-tenant reads"`). The Stop gate enforces both
   on `fix/*` branches.
4. **A phase backlog gets a work order.** For a single reproduced bug the criteria are usually
   enough. For a multi-phase report — and for anything that will run unattended — write
   `docs/handoff/<phase-or-slug>.md` with `/rails-flow:handoff` first: the scope boundary and the
   stop conditions are what keep a grinder inside the rails, and the Stop gate validates the file
   whenever it exists.
5. **Every behavioral change gets a NEW spec proving the new behavior.** Passing the
   existing suite only proves you didn't break old behavior.
6. **Never introduce a regression**: if a fix touches scoping or authorization, check every
   caller; verify legitimate users still pass and unauthorized ones still fail.
7. **Verify the fix addresses the reported issue** — re-read the reported line/method after
   editing and confirm it actually changed.

## Workflow (per phase)

```
1. BRANCH:    git checkout <base> && git pull && git checkout -b fix/<phase-or-slug>
2. IMPLEMENT: the loop above, one issue per commit; delegate big items to rails-developer,
              schema changes to migration-writer
3. VERIFY:    test-runner → FULL suite, 0 failures; code-reviewer → VERDICT: CLEAN
4. PUSH + PR: gh pr create --base <base> --title "fix: <phase — summary>" --body "<PR Documentation Contract>"
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

**Those keep the run from doing damage; they do not tell it when to stop.** An agent that cannot
make progress does not idle — it digs: reverts its own fixes, loosens a spec until it passes, widens
scope to route around the blocker. Every one of those looks like activity in a log and two look like
success. So an unattended run needs the work order's **stop conditions** as well as the hooks:

- **Attempt cap** (default 3 per phase). On exhaustion: stop, write the diagnosis, move to the next
  **independent** phase. Never retry an unchanged failure indefinitely.
- **No progress** = the same failure signature twice with nothing changed. Repetition *without a
  changing error* is the signal; a changing error is progress.
- **Forbidden, and they end the run**: weakening or deleting a failing spec; reverting a phase that
  already passed to unblock this one; editing outside the phase's declared scope; disabling a
  guardrail or hook.
- **The final report distinguishes complete / partial / stopped** and names every phase not
  attempted. A grinder that reports "all phases done" having skipped two has produced a worse
  outcome than one that stopped at phase one and said so.

Write them into `docs/handoff/<phase-or-slug>.md` (`/rails-flow:handoff`) before starting the run —
a bound that lives only in the prompt is gone the moment the session is resumed.

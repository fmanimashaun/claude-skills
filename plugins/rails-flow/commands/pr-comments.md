---
description: Sweep a PR's review feedback — fix every actionable comment on-branch or fold it into a tracked repo issue; the PR must close clean before any next task
argument-hint: "[PR number]"
---

# /rails-flow:pr-comments — $ARGUMENTS

Review feedback is work, not noise. Nothing raised on a PR may evaporate: every
actionable comment is either fixed on this branch or captured as a repo issue —
and the PR is not finished until that is true for every thread.

## Phase 0 — Gather everything

Resolve the PR: `$ARGUMENTS` if given, else the current branch's
(`gh pr view --json number`). Then collect ALL feedback surfaces:

```bash
gh pr view <n> --comments                                  # conversation comments
gh api repos/{owner}/{repo}/pulls/<n>/comments             # inline review comments
gh pr checks <n>                                           # CI — failures are raised issues too
```

## Phase 1 — Classify each item

- **Actionable, in scope**: a defect, gap, or required change within this PR's intent.
- **Actionable, out of scope**: real, but belongs to a different concern (larger
  refactor, unrelated module, future work).
- **Discussion / resolved / nit-with-no-change-requested**: acknowledge, no action.

When intent is ambiguous, ask the commenter on the thread rather than guessing.

## Phase 2 — Resolve (one item at a time)

- **In scope** → fix on THIS branch now. Behavioral change → failing spec first, per
  the /fix rules. Commit, push, then reply on the exact thread: what changed, the
  commit SHA. Resolve the thread if permissions allow
  (`gh api graphql` resolveReviewThread), otherwise the reply is the record.
- **Out of scope** → fold into the tracker:
  ```bash
  gh issue create --title "<summary>" \
    --body "Raised in PR #<n> review: <link to comment>. <context>" --label "from-pr-review"
  ```
  Reply on the thread with the new issue link so the reviewer sees it captured.
- **CI failures** → treat as in-scope items: read the log, fix, push.

## Phase 3 — Re-gate and verify clean closure

If any code changed during the sweep: re-run test-runner (full suite, 0 failures) and
the merge gate (review-pr skill / pr-reviewer) until CLEAN again.

The PR closes clean only when ALL are true:
- every review thread is fixed-and-replied or folded-and-linked
- CI is green
- the merge gate's latest verdict is CLEAN

**Only then** merge (base `dev`) or hand to the user (default-branch base) — and only
then may the next unit, phase, issue, or task begin. Jumping ahead with open threads
is a flow violation.

## Report

Threads handled: fixed on-branch (with commits), folded into issues (with links),
acknowledged-no-action (with reasons); gate verdicts; final PR state.

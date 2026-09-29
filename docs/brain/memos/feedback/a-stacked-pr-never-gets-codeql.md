---
name: feedback-a-stacked-pr-never-gets-codeql
description: A PR based on another feature branch skips branch-filtered workflows, and retargeting the base does not fire them.
type: feedback
---

`.github/workflows/codeql.yml` triggers on `pull_request: branches: [dev, main]`. A PR opened
against a *feature* branch (a stack) matches neither, so CodeQL never runs — and `CodeQL` is a
**required context** on `dev`, so the PR sits `BLOCKED` with `gates=SUCCESS` and no failing check to
point at. Retargeting with `gh pr edit --base dev` does **not** fix it: that fires the `edited`
activity type, and the default `pull_request` types are `opened`, `synchronize`, `reopened`.

`gh pr close <n> && gh pr reopen <n>` fires `reopened` and the required workflow runs.

**Why:** `mergeStateStatus=BLOCKED` with every *present* check green reads like a permissions or
review problem. The real cause is a required context that was never *reported*, which is invisible
in the check rollup because a run that never started has no row. This is the same shape as
"a check that did not run is not a pass", one level up.

**How to apply:** when a PR is BLOCKED and every check shown is green, compare the rollup against
`gh api repos/<o>/<r>/branches/<b>/protection --jq .required_status_checks.contexts` — the missing
context is the answer. Then either close/reopen, or open stacked PRs against `dev` from the start
and accept the wider diff until the parent merges.

Related: [[filter-ci-runs-by-event]], [[a-watcher-that-cannot-see-a-dead-job]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-stacked-pr-never-gets-codeql.md._

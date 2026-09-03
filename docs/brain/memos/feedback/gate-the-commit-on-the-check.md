---
name: feedback-gate-the-commit-on-the-check
description: A check printed FAIL and the push still ran; `cmd | tail -1 && echo merged` reported a merge that GraphQL had refused — wrap commit/push/merge in `if <check>; then`, never chain with `;` or after a pipe
type: feedback
---

Two false successes in one session, same shape:

- A `for c in checks; do … && echo ok || echo FAIL; done` loop printed `FAIL lint_self_consistency`,
  and the next line — `git commit && git push` — ran anyway, because the loop's exit status is the
  last iteration's, not "any failed". A PR went out carrying a lint finding.
- `gh pr merge 845 … 2>&1 | tail -1 && echo "merged"` printed **merged** after GitHub had refused
  the merge with a conflict: the `&&` saw `tail`'s exit code, not `gh`'s.

**Why:** the doctrine here is "a gate that cannot fail is the defect". A shell chain that reports
success regardless is that defect in the maintainer's own hands, and it produces exactly the
claims-vs-enforcement gap the repo exists to catch.

**How to apply:** every commit, push, merge or publish sits inside `if <the actual check>; then …;
else echo "not doing X"; fi`, with the check's own exit code — no pipe between the command and the
test (`| tail` eats it; use `set -o pipefail` or capture to a variable first). After a merge, assert
the state (`gh pr view N --json state`), never the echo. Related: [[assert-ancestry-not-merge-output]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, gate-the-commit-on-the-check.md._

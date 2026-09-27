---
name: feedback-a-diagnostic-object-is-not-a-pass
description: "A test helper returning `{ note: \"missing X\" }` is truthy, so three QA cases printed PASS while their own notes said what was absent."
type: feedback
---

In a QA harness, cases returned either `true` or a diagnostic object like `{ note: "missing People" }`.
Objects are truthy in JavaScript, so the runner recorded PASS on three cases whose notes said the thing
was missing — a false pass, printed next to its own contradiction.

**Why:** a green report nobody can disbelieve is worse than a red one. The failure mode is silent and
looks like success, which is the same class as a gate that cannot fail.

**How to apply:** make the pass condition explicit — `r === true` or `r.ok === true`, everything else a
fail. Then read the run's own notes against its statuses before reporting: a PASS whose note names an
absence is the bug. See [[gate-the-commit-on-the-check]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-diagnostic-object-is-not-a-pass.md._

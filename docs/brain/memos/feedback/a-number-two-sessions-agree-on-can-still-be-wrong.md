---
name: feedback-a-number-two-sessions-agree-on-can-still-be-wrong
description: When two independent measurements of the same thing disagree, never settle it as "different methods" — find the defect; and a fixture that recomputes the filter proves its own arithmetic, not the code.
type: feedback
---

Two things went wrong the same afternoon (2026-08-20) and they share one root: **an answer that
looks reconciled is not verified.**

**1. Do not close a numeric disagreement as a units difference.** Two sessions measured
`claude-skills`'s gate count as 84 and 85, compared methods, agreed it was "the same reality counted
differently", and moved on. It was a defect: `maintainer_doctor.py --gates-only` counts
`check_is_marketplace_repo` — a precondition, not a gate — into the headline `N passed`, so that
number has always been gates + 1. Three wrong counts had already reached shipped text, including a
CHANGELOG bullet in the release then being armed. Fixed by making the reporting say which number to
quote (`Doctor.gate_results()`), not by hand-correcting the three numbers.

**Why:** a wrong number that survives cross-checking by two independent measurements is a reporting
defect, not a slip — the reconciliation is what hides it. The tell is agreeing on *why* the numbers
differ without either side deriving the other's figure from a named source.

**2. A fixture that recomputes the logic proves its own arithmetic.** Three times in one day a
mutation SURVIVED because the fixture tested an adjacent claim:
- a prefix fixture comparing `v1.9.0` to `v1.92.0` that could not fail either way;
- a two-clause rule whose fixtures tripped both clauses, so neither was proven alone;
- a filter written inline inside a `print`, so the test re-derived the same comprehension by hand.

All three were found by **a mutation surviving**, never by reading the fixture.

**How to apply:** extract the logic into a callable (`gate_results()`), have the test *call* it, and
for a rule with N clauses write a fixture tripping exactly one. When a mutation survives, suspect the
fixture before the mutation description.

Related: [[verify-counts-before-stating-them]], [[confirm-your-branch-not-just-your-repo]],
[[downstream-runs-beat-code-review]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-number-two-sessions-agree-on-can-still-be-wrong.md._

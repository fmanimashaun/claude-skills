---
name: feedback-a-negative-assertion-its-fixture-never-reaches
description: A check asserting "X is NOT credited" passes for free when the fixture never makes X a candidate; pair every negative with a positive control on the same input.
type: feedback
---

`route_coverage_selftest.py` carried what looked like the guard for #1037:

```python
check("attribution: never-visited route uncovered", cov["DELETE /users/:id"].covered, False)
```

It passed **vacuously**. The fixture's evidence held `/users/42/edit` and `/users` — neither matches
the pattern `/users/:id` — so the route was uncovered because it was never *reached*, not because
its verb was weighed. The assertion read **identically before and after the fix**. Meanwhile the
real defect credited 78 of 201 Retask routes (76% reported, 46% true).

**Why:** a negative assertion has two ways to pass — the guard worked, or the input never got as far
as the guard. Both print green. The label ("never-visited route uncovered") even described the
vacuous reading honestly, and still nobody noticed, because a passing check is not re-read. This is
the apparatus-failure family arriving *inside the test that was supposed to be the apparatus*.

**How to apply.** Every negative needs a **positive control on the same input**, asserted first:

```python
# control: the path DOES match, so a False below can only be the verb
check("GET /users/:id IS covered by a visit to /users/42", vcov["GET /users/:id"].covered, True)
check("DELETE /users/:id is NOT covered by that same visit", vcov["DELETE /users/:id"].covered, False)
```

Build the pair so the two differ in **exactly one** attribute. Without the control, a matcher that
had stopped matching anything at all would pass too.

Then prove it: revert only the fix and confirm the negative flips. If it does not, the check was
decoration. **Parse the mutated file before trusting the run** — a load error fails the same way a
caught mutation does (`[[a-harness-that-cannot-see-a-broken-mutation]]`).

Corollary for reviews: when a codebase states a rule in several places, check whether the one place
that *omits* it is the one that matters. Here the GET-only rule was written out and enforced on the
crawl axis and the responsive axis, each with a fixture — and missing from `covered`, the only
number anyone quotes.

Related: [[a-check-that-cannot-tell-the-two-apart]], [[a-criterion-can-name-a-route-that-404s]],
[[a-lookup-whose-key-you-assumed]], [[proving-the-helper-is-not-proving-the-caller]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-negative-assertion-its-fixture-never-reaches.md._

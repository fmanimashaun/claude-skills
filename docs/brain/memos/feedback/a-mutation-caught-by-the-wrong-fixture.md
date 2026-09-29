---
name: feedback-a-mutation-caught-by-the-wrong-fixture
description: "\"caught, but not by the expected fixture\" means a change made a different break parse instead of vanish — a near-miss, never a pass."
type: feedback
---

`mutation_check.py` reports three outcomes, and the middle one is the one that teaches: SURVIVED,
caught-by-the-expected-fixture, and **"caught, but not by the expected fixture (no mention of
'<label>')"**. That middle line looks like noise and is a finding. It fired five times on
2026-09-17 and every one was real:

- a fixture indexed `findings[0]` on an empty tuple, so the mutant **crashed** the selftest before a
  later labelled assertion could report — and the crash was scored as the catch for a *different*
  mutation. A crash is not a verdict, and it steals the verdict from elsewhere.
- a scalar pattern I widened made `[]   # comment` **parse as a value** instead of vanishing, so the
  fixture that exists to catch broken comment-stripping stopped discriminating. Fixed by refusing a
  scalar that begins with `#` or `[` — both constraints came from mutants, not from reading.
- a `if False:` on a guard fell through to `FAIL_ON[raw]` and raised `KeyError`; the honest mutation
  was `return FAIL_ON["none"]`, which **disarms** rather than crashing, and that is the defect a
  real typo would produce.

**Why:** a fixture proves something only if the break makes it fail *for its own reason*. When a
change lets the broken input take a different path — parsed instead of dropped, crashed instead of
asserted — the fixture goes quiet and something else fails in its place, so the suite stays green in
aggregate while one specific guard has stopped guarding.

**How to apply:** treat "caught by the wrong fixture" as a failed run, never a pass. Ask which path
the mutant's input now takes; if it crashes, make the mutation disarm instead; if it parses, tighten
the pattern so it vanishes again. Related: [[a-harness-that-cannot-see-a-broken-mutation]],
[[proving-the-helper-is-not-proving-the-caller]], [[a-check-that-cannot-tell-the-two-apart]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-mutation-caught-by-the-wrong-fixture.md._

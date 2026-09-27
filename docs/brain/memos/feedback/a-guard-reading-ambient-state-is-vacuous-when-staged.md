---
name: feedback-a-guard-reading-ambient-state-is-vacuous-when-staged
description: Assertions that read git/env state passed vacuously in the mutation harness's staged tempdir; inject the state and assert values, not field names.
type: feedback
---

Two ways a brand-new guard for #1047 was worthless while reporting green, both found by running
the mutations rather than by reading them.

- **It read ambient state.** `stale_inventory()` called `git rev-parse HEAD` internally.
  `scripts/mutation_check.py` stages the subject into a **plain tempdir that is not a git
  repository**, so `HEAD` was `None` there, the function returned "not stale" for every input, and
  **every staleness assertion passed vacuously**. Surfaced only by the harness's own INERT-baseline
  check — *"the UNMUTATED selftest already fails in the staged tempdir, so every mutation below is
  'caught' whether or not it breaks anything"*. Fix: make the state **injectable**
  (`stale_inventory(prov, head=...)`) so the check is hermetic, with a sentinel separating "look it
  up" from "there is none" — `None` cannot mean both.
- **It asserted field NAMES, not values.** `set(provenance()) == {"commit","dirty","rails_env",...}`
  passed under a mutation hardcoding `rails_env: None`, which would have shipped a permanently
  empty field — the exact hole the issue existed to close. Fix: set the env var and assert the
  value comes back.

**Why:** a check that consults the environment measures the environment, and a test harness
deliberately gives it a different one. A guard can therefore be green in CI, green locally, and
prove nothing where it is actually exercised.

**How to apply:** before trusting a new guard, ask what it reads that the staged tempdir will not
have — git, cwd, env vars, network, the repo tree. Inject those. Assert **values**, never the shape
of a dict. And read `mutation_check`'s INERT line as a finding, not noise: it is the only thing that
distinguishes "all mutations caught" from "nothing was ever run". Related:
[[a-harness-that-cannot-see-a-broken-mutation]], [[proving-the-helper-is-not-proving-the-caller]],
[[a-negative-assertion-its-fixture-never-reaches]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-guard-reading-ambient-state-is-vacuous-when-staged.md._

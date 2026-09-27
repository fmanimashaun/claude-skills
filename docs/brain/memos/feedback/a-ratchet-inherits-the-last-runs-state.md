---
name: feedback-a-ratchet-inherits-the-last-runs-state
description: A coverage ratchet compares against the previous run, so any step that leaves rows behind makes the gate red every other run and name the wrong cause.
type: feedback
---

Retask's `bin/ci` ran `Tests: RSpec` then `Tests: Seeds` (`db:seed:replant`). The seed step left
its rows, so the **next** run's suite started against them — and branch coverage differs by
database state: **1,762 of 2,485 branches from empty, 1,760 after a replant**. The SimpleCov
ratchet compares against `.last_run.json`, which every run rewrites, so a clean branch failed
"branch coverage has dropped by 0.04%" on every second consecutive run. The message named
coverage; the cause was state.

**Why:** I nearly adjusted the committed baseline to make it pass, which would have made the noise
permanent and hidden a real drop later.

**How to apply:**

- Before believing a ratchet's verdict, **run it twice from the same tree**. Three runs said 70.78%
  and five said 70.91% on identical code ([[repeat-before-blaming-your-change]]).
- Compare per-file `(covered, total)` between resultsets, not branch keys — SimpleCov keys embed
  line numbers, so any insertion makes every branch below it look new
  ([[a-number-two-sessions-agree-on-can-still-be-wrong]]).
- Fix the state, not the number: `db:test:prepare` before the suite, then prove it with two
  consecutive green runs of the sequence that failed.

Related: [[ratchet-a-baseline-dont-set-a-threshold]], [[assert-your-own-records-not-the-table]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-ratchet-inherits-the-last-runs-state.md._

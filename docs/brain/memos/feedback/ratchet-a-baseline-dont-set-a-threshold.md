---
name: feedback-ratchet-a-baseline-dont-set-a-threshold
description: A fixed threshold is inert below the repo and red above it; gate the regression against a recorded baseline instead.
type: feedback
---

`minimum_coverage 90` sat commented out with *"enable once realistic"* for the life of every
project, so coverage was unenforced from first commit to last. A fixed threshold cannot work: set
below where the repo sits it is inert, set above it every run is red and it is switched off within
a week.

**Gate the DROP.** `refuse_coverage_drop` compares against a recorded baseline, so the floor is
wherever the repo already is — never red on day one, never sliding, rising by itself. Used three
times here: coverage (#800), doctrine-map surface coverage (#798), and every drift gate in the repo.

**Why it can gate where a threshold cannot:** "is 83% good?" is judgement, and gating judgement gets
it switched off. A drop is a *measured regression against a recorded baseline* — the same class as a
drift gate. The maintainer's rule: **"gate is the key, advise can be ignored."**

**How to apply:** when tempted to pick a number, ask what the recorded baseline is instead. If the
count is over files or items, make the floor count the same unit — a floor over rows is met by
adding a second row to an item already covered, so coverage looks like it rose when it did not.
Related: [[verify-counts-before-stating-them]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, ratchet-a-baseline-dont-set-a-threshold.md._

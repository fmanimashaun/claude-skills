---
name: feedback-check-the-denominator-not-the-percentage
description: A parser dropped 64 of 143 routes in silence, so coverage read 49/49 (100%) over a table missing the whole admin surface; the honest number was 57%.
type: feedback
---

`route_coverage.py`'s Rails parser required the controller to be the **last** token on a row. Rails
prints a route's `defaults:` after it, so every row like

    requests GET /requests(.:format) placeholders#show {screen: "All requests"}

was skipped by a bare `continue`. On Retask that was **64 of 143 verb-bearing rows**, and the dropped
set was the entire admin surface — the pages a human review had just found eight layout defects on.
Coverage reported **49/49 (100%)**. Corrected: **65/113 (57%), 48 untested**.

**Why:** a percentage is only as honest as its denominator, and a 100% is the *least* likely reading
to be questioned. The silence was the defect; the regex was only how it got in.

**How to apply:** when a coverage number looks good, count the denominator against the source of
truth yourself — `rails routes | wc -l` against the enumerated file — before believing the ratio. And
make the tool refuse: any input row it cannot parse gets reported and the run exits non-zero, rather
than producing a confident percentage over an application that does not exist.

Pairs with [[coverage-counts-assertions-not-properties]] — that one is the wrong *property*, this one
is the wrong *population*. Same session, same afternoon, same green report.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, check-the-denominator-not-the-percentage.md._

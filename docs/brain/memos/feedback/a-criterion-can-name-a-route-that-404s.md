---
name: feedback-a-criterion-can-name-a-route-that-404s
description: An acceptance criterion pointing at a dead route is satisfiable by the error page; resolve every route in a criterion before measuring it.
type: feedback
---

Retask #303's criterion 2 said "No button label wraps at 1440 px" on **`/account` (root admin)**.
There is no `/account` route — `GET /account` returns Rails' "No route matches" page. My first
browser pass reported `url=/account, 1 button, 0 wrapped` and that would have read as the criterion
PASSING. The real screen is `/settings/security` (h1 "Security", `AdminShell::RootAccount` via
`app/controllers/settings/security_controller.rb`).

**Why:** a criterion is a gate, and a gate pointed at a 404 can only ever come back green — the
error page has no buttons to wrap, no select to clip, no brand link to duplicate. This is
`gate-that-cannot-fail` living in the issue text rather than in code, so no linter sees it. The
issue's author could not spot it either: they wrote the path from the design, not from `bin/rails
routes`.

**How to apply:** before measuring any criterion, resolve every route it names —
`bin/rails runner 'Rails.application.routes.routes...'` or `bin/rails routes | grep` — and confirm
the page renders what the criterion talks about. If a criterion's screen 404s, that is a finding
about the ISSUE, reported to whoever owns the text; do not quietly measure the nearest live page
and score the criterion. Say which route you actually drove, in the report, so the next
verification starts from the real one.

The mirror-image error is as bad: a peer then claimed the control named there "is not built at all
— canvas data only". It was built — an `<a href="/admin/actions/rootCodes/new">` whose modal
carries a real form. **A criterion that cannot be reached is not evidence the feature is absent.**

Related: [[a-diagnostic-object-is-not-a-pass]], [[a-check-that-cannot-tell-the-two-apart]],
[[a-missing-template-is-not-a-missing-design]], [[coverage-counts-assertions-not-properties]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-criterion-can-name-a-route-that-404s.md._

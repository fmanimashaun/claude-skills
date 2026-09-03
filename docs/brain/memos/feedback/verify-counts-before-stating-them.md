---
name: feedback-verify-counts-before-stating-them
description: Never report a count, total, or "nothing changed" claim without running the bounded command first — the maintainer has caught two wrong numbers.
type: feedback
---

Every number I state to this maintainer must come from a command that bounded its own input.
Two were wrong in one session, both caught by them, not me:

- **"30 open issues" when there were 42.** `gh issue list` defaults to `--limit 30`, and I had
  dropped the explicit limit. Always `--limit 200` (or `gh api search/issues -q .total_count`).
- **"this release changes the `.skill` assets"** — hashing them showed all four byte-identical.

**Why:** both were `unverified-negative` from the repo's own `code-review` skill, committed while
holding that rule in context. Writing a rule down demonstrably does not prevent violating it. The
first wrong count also turned out to be hiding a real defect — `issue-triager`'s dedupe read the
same truncated list — which became issue #211.

**How to apply:** before stating a count, total, "all X are Y", or "nothing changed", run the
command that proves it and paste the number from that output. Prefer hashing artifacts over
believing a build step. If a listing could paginate, bound it explicitly. See
[[name-where-a-decision-landed]] for the related habit on claims about decisions.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, verify-counts-before-stating-them.md._

---
name: feedback-two-dot-and-three-dot-answer-different-questions
description: Twice in an hour I verified a narrow thing and asserted a wide one — `A...B` quoted as `A..B`, and one filtered `rspec -e` reported as the whole file. Both times the change was right and did not need the bigger claim.
type: feedback
---

2026-09-17, Retask PR #415. After merging `origin/dev` into my branch I told two sessions that
`git diff fa3d07c..77d7680 -- . ':!docs/architecture'` was **empty**, so nothing authored had moved.
It was not empty: 8 files, 299 insertions, including
`db/migrate/20260917210000_add_human_reference_numbers.rb` and `db/schema.rb`.

What I had actually run was `git diff 828282d...77d7680` — **three-dot, against `dev`** — which asks
*"what does my branch add beyond dev"* and is genuinely free of migrations. What I wrote was
**two-dot, against my own pre-merge head**, which asks *"what arrived in my branch"* and necessarily
includes everything the merge brought in. Right conclusion, wrong evidence, and the clause I dropped
— *there is a new migration, re-prepare your database* — was the only load-bearing one.

**Why:** the QA session had a database loaded from the pre-merge schema and a server booted against
it. Had they believed me, they would have driven a browser against a column map predating the
migration — the same failure as the orphaned server I had diagnosed twenty minutes earlier. They
re-derived the diff themselves and caught it.

**How to apply:** after any merge of the base into a branch, state the migration and schema position
explicitly rather than implying it through a diff range — and run the range you are about to quote,
in the form you are about to quote it, at the moment you quote it. `A..B` and `A...B` are different
questions and the output looks equally authoritative. A claim written in good faith reads exactly
like a true one, which is the argument for the person merging re-running it rather than trusting the
author's summary. Per [[verify-counts-before-stating-them]], a range is a count.

**SECOND INSTANCE, SAME HOUR, DIFFERENT TOOL.** On Retask #419 I mutated `ShelfReset` to drop its
`where` and ran `rspec -e "leaves exactly the counts this run minted"`. The example survived, and I
wrote in the PR that the defect was *"invisible to the file whose whole subject is that reset"*. The
file caught it: `dev`'s spec already had `leaves other shelves alone` at line 125, correctly scoped,
and under that mutation the original file goes red with 2 failures. **A filtered run measures the
example, not the suite**, and I reported the narrow result as the wide claim.

Both slips share one shape, and it is not carelessness about syntax: the change was right and did not
need the stronger argument. **Reaching for the more impressive justification is what manufactured the
false claim** — a surviving mutation I did not have, an empty diff I had not run. When the honest
version is already sufficient, stop there.

Related: [[assert-ancestry-not-merge-output]], [[a-stale-server-fails-as-a-behaviour-bug]],
[[a-dirty-file-in-a-shared-checkout-has-no-author]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, two-dot-and-three-dot-answer-different-questions.md._

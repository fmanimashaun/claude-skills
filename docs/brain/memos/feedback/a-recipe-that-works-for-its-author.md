---
name: feedback-a-recipe-that-works-for-its-author
description: A working recipe carries an unstated precondition from its author's environment. Retask's bin/ci isolation needed a test-stamped database; three sessions got it wrong three ways in one evening.
type: feedback
---

On 2026-09-22 the question *"can `bin/ci` be isolated with `DATABASE_URL`?"* got **three different
wrong answers from three sessions in one evening**, and all three were argued carefully.

1. **My original claim (from a handoff): no** — `bin/setup` runs in development, later steps pin
   `RAILS_ENV=test`, so one `DATABASE_URL` collapses them and Rails refuses.
2. **A peer: yes** — it had been running that way all evening, with private `DATABASE_URL` and
   `QA_BASE_URL`, and could show the runs.
3. **My retraction: yes, and here is the mechanism** — step 60 is `RAILS_ENV=test bin/rails
   db:reset`, which drops and recreates and therefore rewrites `ar_internal_metadata`, clearing the
   mismatch that the development-mode setup created. I broadcast this to three sessions.

**All three were wrong.** The truth, from the error a fresh database produced:

    ActiveRecord::EnvironmentMismatchError: ... last run in `development` ... running in `test`
    Tasks: TOP => db:reset => db:drop => db:check_protected_environments

**The check runs BEFORE the drop.** `db:reset` never reaches the recreate, so it cannot heal
anything — my mechanism was plausible, ordered backwards, and I never ran it. And `bin/setup:31` is
`system! "bin/rails db:prepare"` with **no `RAILS_ENV`**, so step 1 stamps the database
`development`.

**Why it worked for the peer:** its database had been created with `RAILS_ENV=test bin/rails
db:create db:schema:load db:seed` before its first `bin/ci`, so `db:prepare` found it prepared and
did not restamp it. A database that session created *without* `RAILS_ENV` was stamped `development`,
exactly like mine. The recipe worked for its author because of a step taken hours earlier and not
mentioned.

**The working recipe, with its precondition:**

    RAILS_ENV=test bin/rails db:create db:schema:load db:seed   # FIRST, on a fresh database
    DATABASE_URL=postgres:///retask_test_<you> QA_BASE_URL=http://127.0.0.1:31NN bin/ci

Preferred over `bin/rails db:environment:set RAILS_ENV=test` after setup, because it does not depend
on the order of steps inside `bin/ci`. Still unmeasured: whether `qa:sweep_fixtures`, which `bin/e2e`
runs against a **development** server pointed at that test-stamped database, makes its own
protected-environment check.

**Why:** a recipe is reported from a working environment, so every precondition already satisfied
there is invisible to its author. "It works for me" is evidence that it *can* work, never that the
stated steps are sufficient. And a mechanism reasoned out from task names is not a measurement — the
task list in the error was what settled it, and it was available the whole time.

**How to apply:** when adopting a peer's recipe, **run it on a fresh resource**, not on one you have
been using — a stale one hides exactly the setup step nobody wrote down. When your own recipe is
about to be copied, say what state the target must already be in. And never retract a measured claim
on the strength of someone else's experience plus your own unrun reasoning: ask what is different
about their environment, which is the question that would have found this in one exchange.

Related: [[verify-in-the-environment-it-runs-in]], [[a-value-two-causes-both-produce]],
[[exit-status-describes-the-command-not-the-state]], [[a-true-result-about-the-wrong-file]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-recipe-that-works-for-its-author.md._

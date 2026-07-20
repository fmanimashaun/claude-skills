---
description: Full parallel codebase review — seven specialist passes producing a phased, /fix-consumable report
---

# /rails-flow:review

Run a thorough review of this Rails project and write a phased fix plan.

## Pre-review context

Read `CLAUDE.md` (conventions + Project Overrides), `GUARDRAILS.md`, and skim the docs/
index if present. The review judges the code against THIS project's rules, not generic taste.

## Parallel review passes

Launch these as parallel subagent tasks; each returns findings as
`[P1|P2|P3] file:line — issue — suggested fix` (P1 = security/data-loss, P2 = correctness,
P3 = quality/conventions):

1. **Models** (general-purpose): concerns coverage per project rules, validations vs DB
   constraints, association options (`dependent:`, `optional:`), N+1 risks in scopes and
   callbacks, uniqueness validations without matching unique indexes, race conditions,
   business-logic correctness against the documented domain.
2. **Controllers & routes** (general-purpose): authentication and authorization on every
   action, tenancy/ownership scoping, IDOR via user-supplied ids, statuses (422/303),
   unpermitted params, error handling on lookups, RESTful shape.
3. **Views & frontend** → `design-auditor` across `app/views` and Stimulus controllers.
4. **Services & jobs** (general-purpose): result-object contract, idempotent `perform`,
   id-only job arguments, transactional boundaries, `_later` broadcasts.
5. **Specs quality** (general-purpose): do specs assert behavior or merely execute code?
   factories minimal-valid? request specs over controller specs? system specs on money
   paths? fixtures of known pitfalls covered?
6. **Migrations & schema** → `migration-writer` in review mode: reversibility, unsafe
   operations, missing indexes on FKs and frequent WHEREs, money column types.
7. **Security** → `security-auditor` over the whole app surface.

## Synthesis

Merge and de-duplicate findings, order into **phases** (Phase 1 = all P1s, then coherent
P2/P3 groupings of ~5-10 items each), and write the report to
`docs/reviews/<YYYY-MM-DD>-codebase-review.md` with each phase marked `Status: Not started`.

Report the totals (P1/P2/P3 counts), the top 5 most serious findings inline, and point the
user at `/rails-flow:fix` to start Phase 1.

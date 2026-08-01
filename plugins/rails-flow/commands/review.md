---
description: Full parallel codebase review — seven specialist passes producing a phased, /fix-consumable report
---

<!-- topology: parallel
     merge: dedupe collapses the SAME finding seen by two passes (never two findings that merely
            look alike); on disagreement the higher severity wins, and a pass that reports nothing
            is not evidence of absence. -->

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

## Teams mode (optional, experimental)

On wide codebases, if agent teams are available (Claude Code ≥ 2.1.32, Opus-class
lead, feature enabled), run the seven passes as persistent teammates spawned from
these same agent types instead of one-shot subagents: reviewers can cross-message
findings (`SendMessage`) — security asking models about a scope check, specs pass
verifying a controller finding — and a `TaskCompleted` hook can refuse to let a pass
complete with an empty report. Same passes, same output contract; richer
cross-examination. Default remains one-shot subagents.

## Synthesis

**Each pass appends its findings as JSONL to `docs/reviews/<YYYY-MM-DD>/findings.jsonl`**, one
record per finding, before writing any prose. The record shape and every rule below are enforced by
`findings.py` — run it rather than doing this by judgement:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" validate docs/reviews/<date>/findings.jsonl
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" dedupe   docs/reviews/<date>/findings.jsonl
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" order    docs/reviews/<date>/findings.jsonl
```

```json
{"id":"sec-001","pass":"security-auditor","severity":"P1","category":"authz",
 "file":"app/controllers/invoices_controller.rb","line":42,
 "signature":"missing-tenant-scope:InvoicesController#show","issue":"…","repro":"…",
 "fix_options":["…"],"caused_by":null,"blocks":["perf-003"],"duplicate_of":null}
```

**You write `signature`; the script trusts it.** It is a stable identity for the *defect*, not the
occurrence — `missing-tenant-scope:InvoicesController#show`, not a file and line. Two passes seeing
one defect must produce the same signature, and that is the one judgement the mechanics cannot make
for you: file+line is wrong in both directions, since the same defect moves when a line is inserted
and two different defects share a line.

Then synthesis, which is now checked rather than promised:

1. **Dedupe is mechanical** — `dedupe` groups by signature and reports `distinct (N instances)`. It
   collapses the *same* defect seen by two passes; it never discards a real one.
2. **Completeness is verified, not contracted.** Every input id must appear in the output as either
   a reported finding or a `duplicate_of`. Synthesis may reorder and may collapse; it may **not**
   drop. A dropped id **fails**:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" completeness --input findings.jsonl --output synthesis.jsonl
   ```
3. **Fix order is topological, not just severity-sorted.** `caused_by` / `blocks` are edges, and an
   edge **outranks severity**: a P1 symptom waits for its P3 cause, because fixing the symptom first
   is wasted work. Severity is the tiebreak *within* what the graph leaves free. A cycle is reported
   rather than raised — a mutual `caused_by` is usually a modelling error worth a human look.
4. **The markdown report is generated from the data**, never authored:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/findings.py" report docs/reviews/<date>/findings.jsonl > docs/reviews/<date>-codebase-review.md
   ```

Each pass reports **every** finding (any severity) with `file:line` + repro + fix option(s) and
does **not** self-decide disposition. Order into **phases** (Phase 1 = all P1s, then coherent
P2/P3 groupings of ~5-10 items each), and write the report to
`docs/reviews/<YYYY-MM-DD>-codebase-review.md` with each phase marked `Status: Not started`. Every
finding — including low-severity/residual ones — appears in the report, issue-ready; the
disposition (fix now / defer / accept) is the developer flow's and the human's call, never a pass's.

Report the totals (P1/P2/P3 counts), the top 5 most serious findings inline, and point the
user at `/rails-flow:fix` to start Phase 1.

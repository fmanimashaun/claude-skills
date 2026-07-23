---
description: Weekly maintenance sweep of docs/brain — flag stale STATUS/evidence, surface decisions-vs-PRD drift and contradictions, compress patterns, and check hypotheses against evidence. Read-only analysis + proposed edits; never rewrites silently.
argument-hint: "[optional: focus area, e.g. 'hypotheses' | 'drift' | 'staleness']"
---

# /rails-flow:brain-review — $ARGUMENTS

The keystone ritual the brain needs to stay trustworthy: without it, `docs/brain/` becomes a
landfill that accumulates without synthesis. Run it weekly (a ~15-minute Friday sweep) or before
a planning session. This is **analysis first** — you produce a report and propose edits as diffs;
you apply changes only after the user confirms (or auto-apply only the mechanical ones you list).

If `docs/brain/` doesn't exist, say so and point to `/rails-flow:setup-flow`. If `$ARGUMENTS`
names a focus area, do that section first but still surface anything urgent from the others.

## The sweep

1. **Staleness.** Read `STATUS.md`'s `_Updated:_` header and compare to `git log -1 --format=%cd`.
   Flag if STATUS is older than the last code change on the base branch (it's lying about "now").
   Flag `[assumed]` claims and hypothesis evidence older than ~30 days (assumptions rot), and
   `[observed]`/`[reported]` evidence older than ~90 days that a live hypothesis still leans on.
2. **Decision ↔ reality drift.** Cross-check `DECISIONS.md` against the PRD / CLAUDE.md / actual
   code (`git grep`, key files). Surface where shipped work contradicts a stated decision or the
   strategy — *tension is signal*, report it, don't resolve it unilaterally. Flag decisions whose
   **reversal condition** has now been met.
3. **Contradictions.** Scan for claims that disagree (two `[reported]`s, a STATUS line vs a
   DECISIONS entry, a hypothesis marked confirmed with refuting evidence). **Never average them
   away** — list both sides with their provenance so the human adjudicates.
4. **Hypotheses.** For each in `HYPOTHESES.md`: has it gathered evidence since last review? A
   `candidate`/`proposed` with no new evidence in ~2 sweeps → flag as stalled (promote, park, or
   drop). A `confirmed` with no `DECISIONS` entry → draft the decision record it implies.
5. **Compression.** Where several PROGRESS-LOG entries or memos describe the same recurring
   pattern, propose a single compressed durable note (a `feedback_*`/`decision_*` memo) — but
   **preserve minority signals**: a one-off that contradicts the pattern stays, tagged as such.
6. **Index hygiene.** MEMORY.md has one line per existing memo (no dead links, no orphaned memos).

## Output

A dated report: **Stale · Drift · Contradictions · Hypotheses · Compression · Index**, each a
short bullet list with `file:line`-style pointers and a one-line recommended action. End with a
**proposed-edits** block (STATUS refresh, new/updated DECISIONS or HYPOTHESES entries, memo
compressions) as concrete diffs. Apply only what the user approves; you may auto-apply the purely
mechanical ones (dead-link removal, `_Updated:_` refresh) if you list exactly what you changed.

Append a one-line entry to `docs/brain/PROGRESS-LOG.md`: `<date> — brain-review sweep: <N flags, key action>`.

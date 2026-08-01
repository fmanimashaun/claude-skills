---
name: quality-pass
description: >-
  A SECOND review pass over changed code, for quality rather than correctness —
  reuse (is this duplicating something that already exists?), simplification
  (redundant or derivable state, copy-paste with variation, dead code left
  behind), efficiency (repeated I/O, work hoisted out of a loop, independent work
  run in series) and altitude (a bandaid where the root cause is reachable, a
  special case where the mechanism generalises). Use after the correctness review
  passes, when asked to clean up, simplify, tidy, refactor or de-duplicate a diff,
  or when a change felt repetitive to write. It is ADVISORY and never a merge
  gate. It does NOT hunt for bugs — the `code-review` skill owns correctness,
  authorization, query safety and claims-vs-enforcement.
---

# The quality pass

A correctness review asks *is this right?* This pass asks a different question, and only
this one:

> **Is this the change, or just a change that works?**

Nothing here is about bugs. If a finding is a bug, it is not yours — hand it to
**`code-review`** with the class name and move on. A reviewer hunting correctness and
quality in the same read does neither well, which is the entire reason this is a separate
pass.

## Three rules before you start

1. **Advisory. Always.** Quality is judgement, and a gate that blocks on taste gets
   switched off — after which nothing checks quality at all. Report findings, never
   refuse a merge on one. The deterministic layer (linters, tests, the project's gates)
   is where refusals belong, because those are decidable without taste.
2. **Run it second.** On a diff that is still wrong, every quality finding is provisional:
   the fix may delete the code you commented on. Correctness first.
3. **Each finding names a dimension and a concrete cost.** "This feels repetitive" is not
   a finding. "`format_currency` here rounds half-up while `ApplicationHelper`'s rounds
   half-even, so two screens will disagree on the same order" is.

## Measure the mechanism, not the text

The first thing this pass gets wrong is confusing *textual* overlap with *extractable*
duplication. They differ by a lot, and always in the same direction.

Applied to four files in this repo's own toolchain, **29% of the lines matched at least
one other file** — and only about **6%** was mechanism a shared module could hold. The
rest was the language's own boilerplate: imports, decorators, `if __name__ ==
"__main__":`. A tool that reports the 29% will get you to extract the 6% and call the job
done.

So before proposing an extraction, say **how many lines it removes** and **what it adds**
(an import, a dependency, a file). If you cannot say the first number, you have not
measured; you have pattern-matched. The full worked example, with the counts and the
decision they produced, is in
[references/worked-example.md](references/worked-example.md).

## The four dimensions

Each one has a **near-miss** — the case where the pattern is *correct* and flagging it
would be the false positive that gets this pass ignored. Read the near-miss first. The
near-misses are where the judgement lives; the positives are the easy half.

### `reuse` — new code re-implementing something that exists

- A helper written into a controller that already exists in `ApplicationHelper`.
- A second scope computing what an existing scope computes, with a different name.
- A validation re-expressed in a form object while the model already declares it.
- A constant re-typed rather than referenced, so the two can drift apart silently.

**Near-miss: the copy is across a boundary the import cannot cross.** Two independently
installed packages; an engine and its host; a shipped script and a build script that
never ships; a service and its client. Then duplication is the *correct* answer and the
real requirement is different: **both copies need the same external control.** Two
implementations of a published formula are safe when each is tested against the standard's
own published value — they cannot silently diverge, because the standard is the arbiter.
Two implementations of a *house rule* with no shared control are a defect however far
apart they live.

**Detect:** grep for the **behaviour**, not the name. A second implementation almost never
reuses the name — that is why it survived review. Search for a distinctive constant, a
magic number, a regex fragment, a column name.

### `simplification` — state that need not exist

- A variable assigned in three branches whose value is always derivable from one
  expression.
- A boolean column that is `status == "archived"` with extra steps, and can disagree with
  it.
- Copy-paste with variation: three near-identical blocks where only one key differs. The
  variation is the parameter.
- Dead code the change left behind — the old branch, the flag that is now always true, the
  method whose last caller went away in this diff.

**Near-miss: derivable is not the same as cheap to derive.** A counter cache, a
denormalised column and a memoised total exist *because* deriving is expensive or the
source is remote. Redundant state with a stated invalidation rule is a design; redundant
state with none is a bug. Equally: two blocks that look identical but answer to **different
owners** must stay apart — merging two rules that happen to coincide today creates a
coupling the next requirement breaks, and the person who breaks it will not know why they
were joined.

**Detect:** for each derived value, ask *what could make this wrong?* If nothing can, it is
redundant. If something can, the question is whether the invalidation is written down.

### `efficiency` — work done more often than it needs to be

- An N+1: a query inside a loop over records.
- A set, regex, config read or file read rebuilt on every iteration of a loop it does not
  depend on.
- Independent I/O run in series when nothing orders it.
- Loading a whole collection to count it, or to take its first element.

**Near-miss: anything that changes *when* an effect happens leaves this pass.** Reordering
work whose sequence is the contract, parallelising calls that share a connection or a
transaction, or caching something whose freshness is the point — those are correctness
changes wearing an efficiency costume, and they belong to `code-review`. Also: a loop over
three elements does not need a hoist, and a hoist that costs more clarity than it saves
work is a net loss. Say the size of the loop.

**Detect:** read every loop body for expressions that contain **no loop variable**. Those
are the hoistable ones, and they are invisible when you read a loop for what it *does*
rather than for what it *repeats*.

### `altitude` — the fix is at the wrong level

- A `nil` guard added at the fourth call site instead of at the one place the `nil` is
  produced.
- A third `if provider == "..."` branch where a lookup keyed by provider is the shape.
- A rescue that swallows a specific error the caller could have prevented.
- A special case for one caller in code every caller shares.

**Near-miss: the root cause may genuinely be out of reach** — inside a gem, in another
team's service, behind a migration that cannot run this week. A bandaid whose comment
names the root cause and why it is unreachable is the *correct* change, and demanding the
deep fix would block the release for nothing. And a special case is not always a missing
generalisation: **two cases is not a pattern.** Generalising on the second produces an
abstraction the third does not fit, and unpicking that costs more than the third `if`
would have. Wait for the third.

**Detect:** ask where the value **became** wrong, not where it was noticed. Those are the
same place only in the easy cases.

## Reporting

- **One dimension per finding**, named. A finding matching two dimensions is usually one
  finding described twice.
- **Give the cost and the price.** What this buys (lines removed, queries saved, a
  divergence closed) and what it costs (a new file, a new dependency, a wider revert).
  A proposal with only the first half is a wish.
- **Report everything you found, and dispose of nothing yourself.** Severity and
  "worth it?" are the author's call. Never mark your own finding "won't fix" to reach a
  clean verdict — and never suppress a small one because the list is already long.
- **A decision not to change something is a real outcome.** Record it with its reason and
  its number. "We looked and decided no" is worth strictly more than silence, because the
  next reader does not have to look again.

## Where this stops

| you found | it belongs to |
|---|---|
| duplication, redundant state, repeated work, wrong level | here |
| a bug, a missing authorization check, an unsafe query, an untested branch | `code-review` |
| a claim in prose that nothing makes true | `code-review` (`claims-vs-enforcement`) |
| a check that cannot fail | `code-review` (`gate-that-cannot-fail`) |
| a style or formatting preference | the formatter, or nobody |

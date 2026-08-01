# Worked example: the pass applied to four files, and the decision it produced

This is the quality pass run once, for real, on the toolchain of the repository that ships
this skill. It is here because the pass is easy to agree with in the abstract and hard to
apply honestly — the interesting output was a **decision not to extract**, reached with
numbers rather than taste.

## The input

Four Python "judges" in one plugin's `scripts/` directory, written in the same week by the
same author, **1,189 lines** between them:

```
plugins/qa-flow/scripts/crawl_report.py         289
plugins/qa-flow/scripts/interaction_report.py   289
plugins/qa-flow/scripts/theme_parity.py         291
plugins/qa-flow/scripts/visual_baseline.py      320
```

Each was reviewed against the `code-review` skill when it was written. None of the
duplication below registered, because duplication is not a class that skill looks for —
which is the gap this skill exists to close.

## What was measured

Two numbers, and the gap between them is the whole lesson.

**Textual overlap.** Runs of three or more consecutive lines appearing verbatim in at least
two of the four files: **345 of 1,189 lines, 29%.**

**Extractable mechanism.** The subset a shared module could actually hold, once imports,
`@dataclass` decorators, blank lines and `if __name__ == "__main__":` are excluded. Itemised,
so the arithmetic is checkable rather than asserted:

| unit | lines per copy | copies | total |
|---|---|---|---|
| `Unusable` class + docstring | 2 | 4 | 8 |
| the `load()` JSON prologue | 4 | 4 | 16 |
| the selftest `check()` harness | 7 | 4 | 28 |
| the `SELFTEST FAILED` reporter | 7 | 4 | 28 |
| the collector field cross-check | 8 | 3 | 24 |
| | | | **104** |

A module keeps one copy of each (**28 lines**) and every file gains an import line (**4**), so
the net removal is **72 lines — about 6%** of the 1,189.

Not counted: the three-line `except Unusable: print(...); return 2` in each `main()`. It wraps a
different call in each file, so a helper would hold two of its three lines at best; counting it
would flatter the number by nine lines and it is exactly the kind of rounding that turns an
estimate into a claim.

A duplication tool reports the 29%. Acting on the 29% means extracting the 6% and
believing the job is done.

## The shapes, counted

Measured across `plugins/**/*.py` and `scripts/**/*.py`.
`scripts/` is included on purpose: it is maintainer tooling that **never ships to a user**,
and half of what follows turns on that boundary.

<!-- shared-shapes:begin -->

| shape | files | where |
|---|---|---|
| `class Unusable(RuntimeError)` | 5 | one plugin |
| the `json.loads` -> `Unusable` prologue | 5 | one plugin |
| the `check(label, ok, detail)` selftest harness | 11 | two plugins + non-shipped tooling |
| the `SELFTEST FAILED --` reporter | 10 | two plugins + non-shipped tooling |
| WCAG relative luminance | 2 | one plugin + non-shipped tooling |

<!-- shared-shapes:end -->

These counts are not asserted. `scripts/check_shared_shapes.py` re-derives every one of
them from the repo and fails when this table disagrees — a count in prose that nothing
re-reads is the `claims-vs-enforcement` class, and it would be a poor look inside the
skill next door to the one that names it.

The harness (9) and reporter (8) counts include **that checker's own selftest**, which
uses the same harness every other script in the repo uses. That is not an oversight and it
is not excluded: it is the near-miss made concrete. A shared *idiom* — the shape every
selftest in a codebase takes — is not the same thing as a shared *mechanism*, and carving
the measuring file out of its own measurement is exactly the kind of exemption this repo
lints for.

Which had an immediate consequence worth recording, because the checker found it on its
first run against real input. Its selftest builds a small synthetic corpus, and the corpus
was written as literal Python — so `class Unusable(RuntimeError)` and the luminance
coefficient existed as *strings* inside the measuring file, and the counts moved from 4 to
5 and 2 to 3. Two fixes were available: exempt the file from its own walk, or stop the
fixture from containing the shape. The exemption was rejected — it is a carve-out that
would also hide a genuine copy landing there later — and the fixture now substitutes
placeholders at write time. **Fix the input, do not widen the carve-out.**

## The findings

**`reuse`, near-miss — the four `Unusable` classes.** The report that prompted this work
said four *plugins* each held their own copy, and that duplication might be right because
plugins ship independently. The first half is wrong: all four files are in **one** plugin,
in **one** directory. And the boundary argument is already settled here in the other
direction — two files in this codebase import a sibling module out of exactly such a
directory. So the import resolves, the objection does not apply, and the honest reason not
to extract has to be a different one. (It is: see below.)

**`reuse`, near-miss — WCAG relative luminance, twice.** One copy is in a shipped plugin
script, one in maintainer tooling that never leaves the repository. No import can cross
that boundary, so duplication is correct. What makes it *safe* is that each copy is tested
against the standard's own published control value — `#767676` on white is `4.54:1` — so
they cannot silently diverge. That is the general form: **duplication across an
uncrossable boundary is fine when both copies answer to the same external arbiter, and a
defect when the rule is a house rule with no arbiter at all.**

**`efficiency` — a set rebuilt once per iteration.** In `theme_parity.compare()`, the
second loop tested membership against a set comprehension over the *other* snapshot's
elements, written inside the loop:

```python
for ref, el in by_ref_dark.items():
    if ref not in {e.get("ref") for e in light.get("elements", [])}:
        ...
```

The comprehension does not depend on the loop variable, so it was rebuilt for every
element in the dark snapshot — quadratic in the page's element count, on a rule whose whole
input is a page's worth of elements. Hoisted; identical behaviour, and the existing
fixture for that branch still passes unchanged. This is the dimension's textbook shape and
it survived a correctness review because it is not incorrect.

## The decision

**Nothing was extracted.** Recorded here rather than left implicit, because "we looked and
decided no" is a real outcome and the next reader should not have to measure again.

1. **The prize is 72 lines out of 1,189.** `Unusable` is two lines — the class line and a
   per-file docstring; the `load()` prologue is four before each judge's validation
   diverges completely. Against that: a new module, an import in four **gate** scripts, and
   a new dependency in four entries of the mutation checker — whose model is "copy the
   subject and its selftest into a temp directory and break it". Every added dependency is
   one more way a mutant dies at import instead of at a labelled fixture, and a crash is
   not a verdict.
2. **The one unit big enough to be worth a module cannot be shared.** The selftest harness
   is the largest shared shape, and it has **nine** copies spanning two plugins that install
   independently plus tooling that never ships. A module inside one plugin reaches four of
   the nine, leaves the pattern in place everywhere else, and buys the smaller half of the
   saving.
3. **So the real question is a distribution question, not a refactor** — whether these
   plugins should vendor a shared module at all. That is a decision about how the product
   is packaged, it is not made by a review pass, and it was filed separately
   ([#398](https://github.com/fmanimashaun/claude-skills/issues/398)) rather than smuggled
   in under a cleanup. Filing it is part of the finding, not a way of avoiding one: the
   pass's job is to surface the question at the level it actually lives at.

The `efficiency` finding was fixed in place, because it costs nothing and removes real
work.

## What to take from this

- Report both numbers. The textual one motivates the look; the mechanism one decides.
- State the price beside the prize. "Extract this" without "and it adds an import to four
  gates" is half an argument.
- A near-miss that turns out to be wrong is still the most valuable output of the pass —
  here it was wrong in the direction that made extraction *more* defensible, and the
  decision still went the other way, for a reason that survives being written down.

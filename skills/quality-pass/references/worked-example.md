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

| shape | files | reach | where |
|---|---|---|---|
| `class Unusable(RuntimeError)` | 5 | 5 | one plugin |
| the `json.loads` -> `Unusable` prologue | 5 | 5 | one plugin |
| the `check(label, ok, detail)` selftest harness | 12 | 5 | three plugins + non-shipped tooling |
| the `SELFTEST FAILED --` reporter | 10 | 5 | two plugins + non-shipped tooling |
| WCAG relative luminance | 3 | 1 | two plugins + non-shipped tooling |

<!-- shared-shapes:end -->

**`reach` is the column decisions rest on** (#398). `files` says how much duplication exists;
`reach` says how much of it a shared module could ever remove — the size of the largest single
install root holding the shape. Each plugin is its own `source:` in `marketplace.json` and every
plugin script is invoked through `${CLAUDE_PLUGIN_ROOT}`, which resolves to that plugin's own root,
so copies only share with copies under the same root. Read the rows where the two columns agree
against the row where they differ most, and the findings below fall out of the table rather than
out of judgement: where `reach` equals `files` the copies are all in one plugin, an import
resolves, and the boundary is no defence — the reason not to extract has to be the size of the
prize. Where `reach` is 1, no two copies are reachable from one module at all, duplication is the
only option available, and the question becomes what keeps them honest instead.

These counts are not asserted. `scripts/check_shared_shapes.py` re-derives every one of
them from the repo and fails when this table disagrees — a count in prose that nothing
re-reads is the `claims-vs-enforcement` class, and it would be a poor look inside the
skill next door to the one that names it. `reach` is gated the same way, and its grouping is
cross-checked against `marketplace.json`: if `plugins/<name>` ever stops being where a plugin is
installed from, the column would be counting a boundary nobody ships, and that fails rather than
rots.

The harness and reporter counts include **that checker's own selftest**, which uses the
same harness every other script in the repo uses. That is not an oversight and it is not
excluded: it is the near-miss made concrete.

(Those two counts were restated here as bare numbers, and by the time #129 next touched
this file both were stale — the table said 11 and 10, the prose still said 9 and 8. The
gate could not see it, because it reconciles the *table*. Restating a gated number in
ungated prose gives you a second copy with no arbiter, which is the very thing the row
above is about, so the numbers are gone and the sentence now points at the table.) A shared *idiom* — the shape every
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

**`reuse`, near-miss — WCAG relative luminance, three times.** Two copies are in shipped
plugin scripts, one in maintainer tooling that never leaves the repository. No import can
cross that boundary, so duplication is correct. What makes it *safe* is that each copy is
tested against the standard's own published control value — `#767676` on white is `4.54:1`
— so they cannot silently diverge. That is the general form: **duplication across an
uncrossable boundary is fine when both copies answer to the same external arbiter, and a
defect when the rule is a house rule with no arbiter at all.**

The third copy arrived later (#129, `plugins/design-flow/scripts/palette_candidates.py`)
and is worth recording, because it tested the rule rather than merely obeying it. Sharing
the external arbiter is the *minimum*; that copy also has `check_token_contrast.py
--selftest` import it and assert the two agree to `1e-9` across a probe set, **plus a
positive control proving the comparison can detect a disagreement at all**. That last part
is the bit worth copying. A parity assertion with no positive control cannot tell "the two
agree" from "nothing was compared", and the first draft of that fixture was exactly that
tautology — caught by mutation, not by review.

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
   is the largest shared shape, and it is the row where the table's `files` and `reach` columns
   disagree most — its `where` column says why. A module inside any one of those install roots
   reaches only the `reach` share of the copies, leaves the pattern in place everywhere else, and
   buys the smaller part of the saving.

   (Those two numbers were restated here as bare digits — "nine copies", "four of the nine" —
   and by the time #398 read this section both were stale, one of them wrong in three separate
   ways. The fix three lines under the table caught the other instance of the same defect and
   missed this one, which is what it looks like when you patch an instance instead of grepping
   the pattern. Again: the digits are gone, the sentence points at the table.)
3. **So the real question is a distribution question, not a refactor** — whether these
   plugins should vendor a shared module at all. That is a decision about how the product
   is packaged, it is not made by a review pass, and it was filed separately
   ([#398](https://github.com/fmanimashaun/claude-skills/issues/398)) rather than smuggled
   in under a cleanup. Filing it is part of the finding, not a way of avoiding one: the
   pass's job is to surface the question at the level it actually lives at. It was answered
   separately too — see below.

The `efficiency` finding was fixed in place, because it costs nothing and removes real
work.

## The distribution question, answered: still no (#398)

#398 asked the one thing the pass deliberately left open — whether the plugins should vendor a
shared selftest harness rather than carry a copy each. **They should not.** The reasoning is here
so the next reader inherits it instead of re-measuring, and because a decision recorded only in a
closed issue is a decision nobody finds.

**What the boundary actually is.** Not "the files are absent". The marketplace is one git repo, so
an install may well have every plugin tree on disk. The boundary is that **`${CLAUDE_PLUGIN_ROOT}`
is the only path a plugin is given**, and it resolves to that plugin's own root. Every script
invocation in `plugins/` goes through it and **none** reaches outside — no `.py` under `plugins/`
resolves a path above its own plugin (`parents[2]` and higher appear zero times). A cross-plugin
import would have to hard-code a relative escape that depends on a layout nothing promises and that
breaks the moment a plugin is vendored, copied, or installed from a different marketplace. That is
a new coupling between independently installable products, not a refactor — which is why the
`reach` column exists and why it is measured from `marketplace.json` rather than assumed.

**The arithmetic, so the answer is checkable rather than asserted.** A shared harness has to be an
object: `check()` mutates closure state and the reporter reads it. Call it ~16 lines with its
docstring. Per file it removes the 7-line harness and the 7-line reporter and adds four — two to
put the sibling directory on `sys.path` and import it, one to construct, one to `return
t.report()`. So one install root holding **R** copies nets **10R − 16** lines. At the ceiling the
`reach` column records today, that is the low thirties; across all four roots together, about
**44 lines** — out of the **6,016** in the twelve files, well under **1%**.

Against that: **298** call sites become `t.check(...)`, and **ten** of the twelve subjects carry a
`mutation_check.py` guard that would gain a `deps=` entry, covering **81** declared mutations.
Every one of those is a way a mutant dies at import rather than at a labelled fixture.
`run_baseline` (#422) now makes that failure loud instead of silent — it runs the unmutated
selftest first and reports INERT — so the risk is smaller than #398 assumed when it was filed.
Smaller, not gone, and it is being spent on well under 1%.

Those three are point-in-time, like the 29% at the top of this file, and they are re-derivable
rather than remembered. The twelve files are the harness row's own hits — `check_shared_shapes.py`
prints them whenever the row drifts. The call sites are `grep -c '^[[:space:]]*check('` across
them; the mutations are the `Mutation(` entries under those subjects' `GUARDS` in
`scripts/mutation_check.py`.

**Vendoring is the worse of the two options, not the better one.** Copying one source module into
each plugin at package time needs a build step and a drift gate to guarantee four copies of a
16-line module stay identical. That machinery is larger than the duplication it polices, and it
converts twelve honest copies into four copies that *claim* to be one — which is strictly worse to
debug, because a diverged vendored copy looks like a shared module until it doesn't.

**What makes the copies acceptable is a shared control, not a shared module** — the general form
already stated for the luminance near-miss above. `scripts/mutation_check.py` proves each of these
selftests can actually fail, which is the property the duplication could otherwise silently lose.
It covers ten of the twelve. The exceptions are real and worth naming rather than rounding away:
`plugins/rails-flow/scripts/extract_claims.py` and `plugins/rails-flow/scripts/findings.py` both
ship a `--selftest` that no guard mutates, so for those two the control is asserted rather than
proven. That is a mutation-coverage gap, not an argument for a shared module.

**What would change the answer.** The `reach` column, gated, is the trigger: if one install root
ever holds enough copies for `10R − 16` to be worth the churn, the number moves and the gate makes
someone re-read this section. A count of copies across the repo never will be — it is the wrong
number, and reporting it was how the question got framed as a refactor in the first place.

## What to take from this

- Report both numbers. The textual one motivates the look; the mechanism one decides.
- State the price beside the prize. "Extract this" without "and it adds an import to four
  gates" is half an argument.
- A near-miss that turns out to be wrong is still the most valuable output of the pass —
  here it was wrong in the direction that made extraction *more* defensible, and the
  decision still went the other way, for a reason that survives being written down.

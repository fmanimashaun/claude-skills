---
name: code-review
description: >-
  Review doctrine for the class of defect authors are systematically blind to —
  code that is correct on its own terms but does not do what its own
  documentation, config, comments or project rules claim it does. Use this skill
  whenever reviewing a diff, a pull request, or a branch; before committing;
  when asked to check, audit, critique or sign off on changes; or when acting as
  a merge gate. Names the recurring defect classes (claims-vs-enforcement,
  dead-declaration, carve-out-without-negative-test, coverage-gap,
  doctrine-contradiction, unverified-negative, gate-that-cannot-fail) and how to
  detect each. Complements correctness review (authorization, scoping, query
  safety, tests); it does not replace it.
---

# Reviewing for claims the code does not honour

Most review checklists ask one question:

> Is this code correct?

Nearly every defect that survives self-review came from a different one:

> **Does this code do what its own documentation, config, comments and project
> rules claim it does?**

Correct-looking code passes the first question and fails the second. This is the
class an author cannot see, and the reason is structural, not carelessness: the
author read the claim and the code as a single intention. A reviewer with fresh
context reads them as two artefacts that may disagree.

Ask both questions on every review. This skill covers the second.

## How to use this

1. **Run the deterministic checks first**, whatever the project has — linters,
   `bash -n`, the test suite. They are free and never wrong. Prose review after,
   for the classes no machine catches.
2. **Load the project's own rules** — `CLAUDE.md` (especially any *Project
   Overrides*), `README`, `CONTRIBUTING`, `docs/`, ADRs. Compliance is judged
   against the project's stated rules, not generic taste. **These rules are the
   input to this review**: most findings below are a rule in the repo disagreeing
   with code in the repo.
3. **Walk the classes below against the diff.** Each one is a question with a
   concrete shape, not a vibe.

## The classes

### `claims-vs-enforcement`
A guarantee stated in prose that nothing makes true.

- A comment claiming a `before_action` guards an action that has none.
- A documented validation never declared on the model.
- A README setup step, or a "you must pass `--flag`", that the code does not require.
- A docstring describing behaviour the implementation only partly covers — e.g.
  "handles ERB and Ruby comments" where only ERB is handled.
- A guard that *softens* a verdict instead of deciding whether to run a check:
  `verify --check || echo "skipped"` makes the gate unable to fail.

**Detect:** for every assertion in prose, find the code that makes it true and
check each branch it claims to cover. When a claim and the code disagree, decide
which is wrong — **the fix is not automatically the code.**

### `dead-declaration`
A declaration nothing reads.

- An ENV var in `.env.example` no code loads.
- A `config/settings.yml` key never referenced.
- A feature flag never checked; a CLI flag parsed and ignored.

A condition quietly false is worse than an absent one: it gets copied into
documentation, results files, or onboarding notes and read as fact.

**Detect:** grep the declared name across the code that loads that config. No hit
means wire it up or delete it.

### `carve-out-without-negative-test`
An exemption written more broadly than the rule it encodes.

- `unless admin?`, a `skip_before_action`, a lint disable, a path-matched
  exemption — with no test proving it does **not** apply to the near-miss case.
- Example shape: a rule exempts one specific component, but the exemption matches
  any file whose *name* contains that word, so anything can opt out by renaming.

**Detect:** every exemption needs a **near-miss negative test**. A carve-out
tested only in the positive direction is untested in the direction that matters.

### `coverage-gap`
A rule or behaviour exercised against only part of what it actually covers.

- A shared concern spec'd through one including model while three others include
  it untested.
- A check that scans several file types but whose fixtures only use one.

**Detect:** compare the set a rule *applies to* against the set its tests
*exercise*. The gap is where bugs live.

### `doctrine-contradiction`
Code, comments, or generated output contradicting the project's own stated rules.

The dangerous version is guidance that contradicts a rule elsewhere in the same
project, because it is confidently wrong **and blames the developer for
following the real rule.** Worse still when a generator writes the wrong rule into
the project's own rules file, so the contradiction becomes self-reinforcing.

**Detect:** when the diff states a rule on a topic the project's docs cover, open
those docs and confirm they agree. When you find one instance, **grep for the
pattern** — this class travels in groups, because the wrong rule gets copied.

### `unverified-negative`
Reporting a count from a list you did not read to the end.

"Four findings" from a paged or truncated listing that actually had five. The
missed one ships.

**Detect:** **count first, then read.** A claim of "N findings" needs the total
from the source, not from what fit on screen. The same applies to "no matches" —
confirm the search actually ran over the intended input.

### `gate-that-cannot-fail`
A check whose failure path cannot fail anything.

- `rescue nil`; `|| true` in CI; a spec that executes code without asserting
  behaviour.
- A check reporting "clean" over input it never read — a regex that silently
  skipped most of its targets is indistinguishable from a passing check.
- A check so strict everything fails it equally, so the signal is constant.

**Detect:** **make the check fail on purpose once.** A gate never observed failing
is not known to work. And when a check reports clean, confirm what it examined —
"no findings" over zero inputs is not a pass.

## Reporting

Two rules keep this from becoming ritual:

1. **A finding needs a named class and a concrete failure.** "This looks fragile"
   is not a finding. "`settings.yml` declares `retry_limit` and nothing reads it,
   so the documented retry behaviour never happens" is.
2. **Report every finding, with the disposition left to the author.** A reviewer
   does not decide what is worth fixing — surface it with `file:line`, a failure
   scenario, and a severity, then let the author and the human choose. Never
   silently drop a small finding, and never mark your own finding
   "accepted / won't fix" to reach a clean verdict.

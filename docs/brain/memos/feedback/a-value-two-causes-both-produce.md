---
name: feedback-a-value-two-causes-both-produce
description: Seven signals in two days that could not name their own cause — before believing a value, name the other thing that produces it.
type: feedback
---

A value that **two different causes both produce**, read as if it named one of them. The reader is
not wrong about the value; they are wrong that it identifies a cause. Because it looks like an
answer, the cost is not a missed signal — it is hours spent debugging the wrong half.

| the signal | cannot separate |
|---|---|
| `conclusion: failure` | a failed suite from **a runner that never started** (0 steps, billing) |
| a half-seeded database | "seeded and broken" from **"never finished seeding"** |
| `Status: pass` | a coverage claim from **a correctness one** |
| `Exercised` | a driven route from **an invented artifact** |
| `0 findings` | a clean repo from **a silenced judge** |
| `selftest: 0 failures` | a parser that handles every form from **fixtures containing only one** |
| `PostToolUse has never fired` | a hook not yet loaded (restart fixes) from **a plugin not enabled** (restart never will) |

**Why:** the discriminator usually already exists and is not being read. `conclusion` has `steps`
beside it; the doctor could read `enabledPlugins`. And it defeats the obvious review question —
`gate-that-cannot-fail` asks *make the check fail on purpose once*, and on the expression-index
parser that **passes**: mutate the regex and the selftest goes 0 failures to 2, while the defect
survives. What was missing was not a failure path but an **input shape**.

**How to apply:** before believing a value, **name the other thing that produces it**. If you can
name one, it is not evidence yet — find the field that separates them, or build the case where the
two disagree. Watch for it in your own controls: my "positive control" for a containment check
planted a slot genuinely *contained* in the recipe, so it satisfied containment **and**
co-occurrence and could not tell them apart. Only an input where they disagree separates them.
Related: [[a-check-that-cannot-tell-the-two-apart]] (the same defect when *writing* a check, not
reading a value), [[fixtures-in-one-canonical-form-miss-format-variance]],
[[a-diagnostic-object-is-not-a-pass]], [[a-mutation-caught-by-the-wrong-fixture]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-value-two-causes-both-produce.md._

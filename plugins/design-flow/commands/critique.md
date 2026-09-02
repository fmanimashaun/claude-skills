---
description: Critique UI look-and-feel against the art-direction doctrine — visual hierarchy, focal point, per-surface aesthetic intent — and return ranked, concrete improvements. Advisory; never blocks.
argument-hint: "[path, view, or surface to critique; default: changed files]"
---

# /design-flow:critique — $ARGUMENTS

Judge whether `$ARGUMENTS` (or the working diff) reads as **considered** or **mechanically
assembled**. Delegate to the **design-critic** agent.

**This command cannot fail.** It returns ranked suggestions, never a pass, a fail, a score
threshold, or a merge recommendation. If you want the blocking check, that is
`/design-flow:audit` — and the two answer different questions:

| | `/design-flow:audit` | this |
|---|---|---|
| asks | is this **correct**? | is this **considered**? |
| authority | **gate** — blocks | **lens** — advisory |
| output | `file:line` + the exact fix | the missing decision + the specific change |

Running only this one and shipping is a mistake; running only the auditor is how you ship a surface
that is correct and lifeless. They are both cheap.

## Preconditions

**The `design-system` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`design-system`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

## 1. Read the rubric

[`art-direction.md`](../../../skills/design-system/references/art-direction.md) is the doctrine —
one focal point per surface, a different brief per surface class, and one bounded escape from the
grid. The critic applies it; it does not invent rules beside it.

## 2. Name the surface class first

Marketing · dense app · focused task · empty/error. The brief differs by class, so a critique that
has not named the class is grading against the wrong one. **If the class cannot be inferred from the
code, say so and stop** rather than guessing — a dashboard given marketing advice is worse than no
advice.

## 3. Expect the flat diagnosis

The most common real finding is **no focal point at all** — every element at the same scale, weight
and contrast, so the eye has nowhere to land. It passes every gate we ship, which is exactly why a
gate was never going to find it.

## 4. Consistency findings are not yours

Raw hex, missing `aria-*`, off-catalog variant, hand-rolled layout CSS → name it as the auditor's and
move on. Two roles grading the same thing disagree in front of the user, and the blocking one wins.

## 5. Ranking variants

Given `/design-flow:variants` output, this command is the rubric that one lacks: rank the N
compositions on **brief-fit first, craft second**, and say which single change would most improve the
winner. *"They are all fine"* is not a ranking.

## Generated assets get a fitness verdict, and it blocks

If `$ARGUMENTS` includes a **generated** asset, the critic runs **fitness first**: does the image match
the brief recorded with it — depicts what was asked, omits what was forbidden, leaves the space the
layout needs, legible at render size. That returns **pass/fail**, not a suggestion, and **this command's
advisory stance does not cover it**.

The distinction is the point. Taste is judgement, so it never blocks. Fitness is a **comparison against
a brief we wrote**, so it can — and an asset that fails it is not referenced by a view: regenerate with
a corrected brief, or fall back a tier. **No recorded brief is a fail**, since there is nothing to
compare against.

## Report

Per surface — class · focal point (or its absence) · ranked suggestions, each carrying the missing
decision, the specific change, and why from the surface's purpose.

**End with what could not be judged.** A surface whose class was unclear, a value that only resolves
at runtime, anything needing a rendered page rather than markup. Unlike the auditor there is no gate
behind this to catch a silent skip, so an unstated gap reads as a clean bill of health.

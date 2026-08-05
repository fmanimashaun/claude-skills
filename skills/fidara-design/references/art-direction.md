# Art direction — the creative hat, inside the system

**Change type: our decision, not an external claim.** Nothing here cites a spec, because no spec
settles whether a surface is well art-directed. Where this file touches something a source *does*
settle — contrast, motion gating, focus order — it defers to the file that owns it rather than
restating it at a different strength.

## Why this file exists

Every other reference in this skill answers *"is this correct?"* — the right token, the right
primitive, the right variant, the right role. All of it is necessary and none of it is sufficient.
A surface can pass every gate we ship and still be **mechanically assembled**: correct, accessible,
dark-mode-aware, and lifeless.

That is not a hypothetical. The tooling we ship is entirely *avoid-the-bad* and *match-the-system* —
`llm_tell_detector.py` catches AI tells, `rendered_conformance.py` checks token conformance,
`check_page_pacing.py` measures band repetition. There is no *achieve-the-good*, and the
`design-auditor`'s own priority order says **`breaks-consistency > a11y > polish`**, with polish last
and framed as consistency.

So this file is the missing half. It is **advisory by construction** — read *Why none of this is
gated* at the end before proposing otherwise.

## 1. Correct versus considered

Hold these apart, because conflating them is what produces the mechanical output:

| | asks | owned by | fails how |
|---|---|---|---|
| **Correct** | did you use the system? | every other reference + the gates | drift, a11y break, off-catalog variant |
| **Considered** | did you make a decision? | this file | nothing is wrong and nothing is *chosen* |

The diagnostic question for *considered* is not "is it pretty". It is: **name the decision.** For any
surface, you should be able to say what the eye lands on first and why, what the surface is *for*
emotionally, and what you deliberately made quieter so that the first thing could be loud. If the
honest answer is "I composed the primitives in the order the catalog lists them", the surface is
assembled, not designed.

## 2. One focal point per surface

**Exactly one element wins.** Not two, not zero. Zero is the common failure and it is what "flat"
means: every element at the same scale, weight and contrast, so the eye has nowhere to land and the
reader has to *read* the page to navigate it.

Rank the surface before styling it. Whatever is rank 1 gets the scale, the weight, or the contrast —
**one of those three, not all three**, because using all three is how a focal point becomes a shout.
Everything else steps down deliberately.

- **Scale** carries hierarchy on a marketing surface, where there is room.
- **Weight** carries it in dense UI, where there is not.
- **Contrast** carries it when neither scale nor weight is available — a single saturated element in
  an otherwise neutral field. Ration this hardest; it is the one that stops working the moment there
  are two of them.

Note what this does *not* license: `text-step-5` on three headings is not three focal points, it is
none. The steps are a ladder, and a ladder with every rung at the same height is a wall.

## 3. Per-surface aesthetic intent

**The same composition is right on one surface and wrong on another**, and the brief differs by
surface class, not by brand. This is the concrete answer to "the marketing pages look like slop and
the app looks mechanical" — they were given the same treatment.

| surface class | the brief | so |
|---|---|---|
| **Marketing** — hero, landing, pricing | **emotion, then comprehension** | generous negative space, one large claim, imagery that carries meaning; asymmetry is allowed and often better |
| **Dense app** — tables, dashboards, lists | **clarity and density, no drama** | tighten spacing, drop decoration, let *alignment* do the work a border would do badly; the focal point is the primary action, not a heading |
| **Focused task** — auth, checkout, single form | **calm and singular** | remove everything that is not the task; `cover > center > stack`; the focal point is the submit |
| **Empty / error** | **orientation, then a way out** | one sentence of plain language and one action; never decorate a dead end |

A marketing hero art-directed like a dashboard is the "too mechanical" complaint. A dashboard
art-directed like a hero is worse — it wastes the density a working screen needs, and it is the
reason "enterprise redesigns" get reverted.

## 4. Taste within the constraints — and the one sanctioned way out

**Default: the system, entirely.** Role tokens, the fluid scale, the layout primitives. Almost all
art direction is achieved *inside* those — the scale ladder has enough range, and negative space is
free.

**The escape hatch, bounded.** A hero moment may break the **grid** and the **scale**. It may not
break the **token contract**. Concretely, for one surface, at most one element:

- may sit outside `grid-auto`/`Switcher` with bespoke placement,
- may use a size between or beyond the `--text-step-*` rungs,
- **must still** take its colour from role tokens, honour dark mode by construction, keep its
  contrast obligations, and gate its motion per `motion.md`.

Everything about that is deliberate. Colour is where a fork becomes unfixable — a bespoke hex outlives
the brand it was chosen for and breaks every future pack — whereas a bespoke *size* on one hero
element is a local decision you can see and revert. And "at most one element, one surface" is what
stops the hatch becoming the habit; two exceptions on a page is a system fork wearing a smaller name.

## 5. Type: expressive or plumbing, decided per surface

Type is **plumbing** almost everywhere: it carries the content and gets out of the way. On a hero it
may be **the design element itself** — the largest step, tight leading, a deliberate measure — and
then it needs nothing beside it: no gradient, no outline, no shadow. Expressive type plus decoration
is the tell that neither was chosen.

Two things that read as craft and cost nothing: a **measure** that actually holds (`--measure`, not
a full-bleed line of 120 characters), and **one** type role doing the emphasis rather than three.

## 6. Negative space is the cheapest thing you have

Most "this looks unfinished" is not a missing element — it is missing space. The failure is uniform
`--space-m` everywhere, which reads as a spreadsheet.

**Space carries grouping.** Related things sit close, unrelated things sit far, and the *difference*
between those two distances is the signal. Two elements at `--space-s` and the next group at
`--space-xl` says more than any divider. Reach for a border only when space cannot do it — a border
is an admission that the spacing failed.

## 7. Motion as choreography

`motion.md` owns the mechanics — durations, easings, `prefers-reduced-motion`, the cap of one
entrance pattern and three animated regions. It is not restated here.

What this file adds is **sequence**: when several things enter, they enter in the order the reader
should read them, with a small stagger, not all at once. Simultaneous entrance is the mechanical
tell. And motion should describe a *relationship* — a panel growing from the control that opened it
says where it came from; the same panel fading in centre-screen says nothing.

## 8. Imagery and texture — restraint is the direction

`visual-assets.md` owns what an asset may be and when illustration is warranted. The art-direction
rule on top of it: **an image must carry meaning the copy cannot.** A photograph of a laptop on a
product page carries nothing; a screenshot of the actual product at the actual density carries the
claim. If an image is there for texture, it belongs behind content at low contrast, and it must not
compete with the focal point chosen in §2.

## Worked example — a marketing hero

**Before** — everything correct, nothing decided:

```erb
<section class="bg-card section-y">
  <div class="stack text-center prose-measure mx-auto">
    <h1 class="text-step-3">Ledger for modern finance teams</h1>
    <p class="text-step-1 text-muted-foreground">Track, reconcile and report.</p>
    <div class="cluster justify-center">
      <%= render Ui::Button.new(variant: :primary) { "Start free" } %>
      <%= render Ui::Button.new(variant: :primary) { "Book a demo" } %>
    </div>
  </div>
</section>
```

Passes every gate. Two `primary` buttons means **no** focal point; `text-step-3` on the claim leaves
the ladder's top two rungs unused; centred-everything is the reflex composition; and the claim could
introduce any product after a logo swap.

**After** — one decision per line:

```erb
<section class="bg-card section-y">
  <div class="stack" style="--space: var(--space-l)">
    <%# rank 1: the claim, at the TOP of the ladder — scale carries hierarchy here %>
    <h1 class="text-step-5 max-w-[38ch]">Close the month in a day, not a week</h1>
    <%# rank 2: who it is for, concretely. Quieter by ROLE, not by shrinking it to unreadable %>
    <p class="text-step-1 text-muted-foreground max-w-[55ch]">
      For finance teams reconciling more than 2,000 transactions a month.
    </p>
    <%# rank 3: ONE primary. The second action is real but subordinate %>
    <div class="cluster" style="--space: var(--space-s)">
      <%= render Ui::Button.new(variant: :primary, size: :lg) { "Start free" } %>
      <%= render Ui::Button.new(variant: :ghost) { "Book a demo" } %>
    </div>
  </div>
</section>
```

What changed is not styling. The claim became specific and measurable, the hierarchy is a ranking
rather than a stack, one action wins, and the left-aligned measure gives the eye a start position.
No new token, no bespoke CSS, no grid break — all of it inside the system.

## Worked example — a dense app table

**Before** — a hero's treatment on a working screen:

```erb
<div class="stack" style="--space: var(--space-xl)">
  <h2 class="text-step-4 text-center">Transactions</h2>
  <div class="box shadow-md">
    <table class="w-full">…</table>
  </div>
</div>
```

`text-step-4` centred spends the ladder on a label nobody reads twice; `--space-xl` and a shadow put
air and ornament where the screen needs rows; and the focal point is the *heading*, which is not what
anyone came for.

**After** — density is the brief:

```erb
<div class="stack" style="--space: var(--space-s)">
  <%# The heading is plumbing here. The focal point is the ACTION %>
  <div class="cluster justify-between">
    <h2 class="text-step-1">Transactions</h2>
    <%= render Ui::Button.new(variant: :primary, size: :sm) { "New transaction" } %>
  </div>
  <%# Alignment does the work a border would do badly; numbers right-aligned and tabular %>
  <table class="w-full">
    <tbody class="divide-y divide-border">
      <tr><td class="py-2">…</td><td class="py-2 text-right font-mono tabular-nums">…</td></tr>
    </tbody>
  </table>
</div>
```

Same system, opposite brief: the heading steps *down*, space tightens, the shadow goes, and hierarchy
comes from alignment and one small primary action.

## Why none of this is gated

**Every rule above is judgement, and a gate on judgement gets switched off.** Once it is off, nothing
checks anything — which is strictly worse than advisory guidance nobody can disable.

This is not a guess. `#476` proposed extending `check_page_pacing.py` to four "monotony" axes that
look exactly like §2 and §6, and the measurement killed it: the threshold flagged **our own** worked
band sequence, because one shape legitimately covers 3 of its 7 bands. A gate that needs a carve-out
on its first real input is taste wearing a count. The reasoning is recorded in that script's
docstring so it is not re-proposed.

So the enforcement model here is deliberate and split:

- **`design-auditor`** stays the **gate**: objective, blocking, `breaks-consistency > a11y > polish`.
- **`design-critic`** is the **lens**: advisory, ranked suggestions, never pass/fail, never a merge
  condition.

The one thing that *is* mechanically checkable — that this file exists and is indexed, and that its
vocabulary is present rather than absent — is covered by the skill-routing gate, not by a rule that
judges surfaces.

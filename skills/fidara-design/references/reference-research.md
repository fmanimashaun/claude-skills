# Reference research — look before you design, and synthesise rather than borrow

A designer does not open a blank canvas. They gather references for the *kind of problem* they are
solving, work out **why** each one works, and build something of their own from the mechanisms —
not from the surface.

This file is that method, written so an agent can follow it. It applies to **any** interface with a
design problem, not just marketing pages: a dashboard, an onboarding flow, an empty state and a
pricing page all benefit identically. The one place marketing genuinely differs is named in §7.

**Why this exists at all.** An agent that skips research does not produce *nothing* — it produces
the median of everything it has seen, which is the stock-SaaS look: gradient hero, three feature
cards, a testimonial row. That look is not a style. It is the absence of one, and it is what a
reader recognises instantly without being able to say why.

## 1. Research a JOB, not a page type

*"Find landing page inspiration"* returns the median. The median is the problem.

State the job first, in a sentence naming the user, their state of mind, and the decision the
surface has to move:

> *A technical buyer who has already heard of us, arriving from a docs link, deciding whether this
> is credible enough to try in an afternoon.*

Now the references you want are legible: interfaces that establish credibility fast for a sceptical
reader who dislikes being marketed to. That is a **searchable** brief, and it excludes most of what
"landing page inspiration" would have returned.

## 2. Sample across categories — direct competitors converge

Take **at least three** references, and do **not** take them all from your own category.

Direct competitors have converged on the same look precisely because they all copied each other,
one reasonable decision at a time. Research only them and you inherit the convergence; the output
is on-trend and indistinguishable, which is the outcome this whole file exists to avoid.

A workable spread:

| where from | what it gives you |
|---|---|
| one direct competitor | the conventions your user already expects — the ones you must *not* break |
| one adjacent industry | mechanisms your category has not adopted, which is where difference lives |
| one outside software | print, editorial, packaging, signage — proportion and hierarchy without UI clichés |

The third row is the one people skip and the one that does the most work.

## 3. Capture the artefact, not the link

Screenshot it. A bookmark rots, renders differently next month, and cannot be compared side by side
with the others while you decide.

Capture at the widths you actually build for, because a hero that works at 1440 often collapses at
390 and **that is frequently the whole trick you were admiring**. Store captures beside the record
in §5 so the reasoning and the evidence stay together.

### 3b. Sites behind a login — stop and ask

The best-stocked sources are gated. Pinterest, Dribbble, Behance and Mobbin all serve a **sign-in
wall** to a fresh browser, and most galleries paginate only after you are authenticated.

**A login wall does not error. It returns a page.** So an unattended capture succeeds, produces a
screenshot of a sign-in form, and files it as a reference — and nothing downstream can tell that from
real research, because the file exists and has the right name. That is the failure worth designing
against here, not the missing content.

So: **detect the wall and escalate.** Before capturing, check for the tells — a `/login` or
`/signin` redirect, a password field, a modal overlaying the content, a body that is mostly the same
few hundred bytes on every URL you try. On any of them, stop and tell the human plainly:

> *"`mobbin.com` requires a signed-in session. Sign in once in the Playwright browser profile and I
> will reuse it; or point me at ungated sources instead."*

Then let them authenticate **once**, into a persistent browser profile the session reuses. Never ask
for the credentials themselves, never type them, and never store them — the human signs in, the
profile holds the session, and the agent only drives a browser that is already authenticated.

If they would rather not, that is a complete answer: plenty of reference material is ungated — real
product sites, marketing pages, documentation, print work. Gated galleries are convenient, not
necessary, and a research record built entirely from ungated sources is not a lesser one.

Mark it in the record either way, with `gated: true` on the sources that needed a session, so a later
reader knows why a capture cannot be reproduced on a clean machine.

## 4. Decompose to the mechanism — this is the whole skill

For each reference, write down **what makes it work**, in terms you could apply to a different
subject. If your note names the brand, it is not yet a mechanism.

| not a mechanism | a mechanism |
|---|---|
| "looks like Linear" | one focal point; everything else demoted to plumbing type |
| "nice gradient" | a single saturated ground so foreground type needs no decoration |
| "clean" | three type steps total, and generous negative space instead of dividers |
| "good hero" | the product screenshot *is* the hero image; no illustration competes with it |

A mechanism survives a change of subject, palette and typeface. If yours does not, keep going —
you have described the surface, and copying a surface is what produces the tells in §6.

## 5. Record it, including what you rejected

Without a record the same three sites get researched again next quarter, and the reasoning that
produced the current design is unrecoverable — so the next person changes it on taste alone.

`docs/design/reference-research.json`:

```json
{
  "job": "a technical buyer from a docs link, deciding if this is credible enough to try today",
  "references": [
    {
      "source": "https://example.com/pricing",
      "category": "adjacent",
      "capture": "docs/design/captures/example-pricing-1440.png",
      "mechanism": "price anchored to a single sentence of outcome, not a feature list",
      "adopt": "state the outcome above the number on our pricing band",
      "reject": "their comparison table — our plans differ on one axis, so a table implies complexity we do not have"
    }
  ]
}
```

`reject` is the field people skip and the one that keeps the file honest: a research record where
everything was adopted is a shopping list, not research.

## 5b. The record must name the style it chose

`style` is the **output** of this method, not an input, and it belongs in the record beside the
references it came from.

Three sources disagree — that is why three are the minimum — and **the choosing is the design**. A
record that gathers and does not choose is a mood board: it documents the looking and omits the
decision, so the next reader cannot tell what was concluded from what was merely seen.

It is also the link that makes research mean anything downstream. Every brief in the project is held
to this value: research monochrome ink line-work and brief a 3D render, and the plan refuses before
anything is bought. Without it the record is a box that was ticked.

## 6. Synthesis — three sources minimum, and the reason is not arbitrary

- **One** source is a copy, whatever you tell yourself.
- **Two** is a blend, and blends read as derivative because the seam is visible.
- **Three or more forces you to choose**, because they will disagree — and the choosing *is* the
  design. When two references conflict, the one that matches the **job** in §1 wins; where they are
  equally good, the brand pack breaks the tie.

Then express every adopted mechanism in **your own tokens**. A mechanism you cannot state in the
pack's palette, type scale and spacing is one you cannot ship — you would be hand-rolling values
next to a design system, which is how a codebase acquires two of everything.

## 7. Where marketing actually differs

Only in what the surface is allowed to do, not in how you research it:

- **A product surface is bound by convention.** Users navigate it repeatedly; novelty costs them
  time. Research narrows toward the convention your users already know.
- **A marketing surface is bound by attention.** It is seen once, by someone who owes you nothing,
  and looking like everyone else is the failure mode rather than the safe choice.

So the same three-reference method, weighted differently: for product surfaces lean on the direct
competitor row; for marketing lean on the adjacent and outside-software rows.

## 8. The convergence trap, and its tells

Research is how you avoid the median — and done lazily, it is how you arrive at it, because you
sampled what everyone sampled. The tells, so you can name them in review:

- a gradient hero with a centred headline and two buttons, one ghost
- exactly three feature cards, each with a small icon in a tinted rounded square
- a logo strip labelled *"trusted by"* with no numbers near it
- testimonials in equal-width cards with circular avatars
- an FAQ accordion because the page felt short

None of these is *wrong*. All of them are **defaults**, and a surface built entirely from defaults
has made no decisions — which is exactly what a reader senses and calls "AI-generated".

The check is not *"do we use any of these?"* but *"did we choose this, and can we say what it beats?"*
A default you selected deliberately, and can defend against the alternative you rejected, is a
decision. The same default arrived at by not deciding is a tell.

---
name: feedback-name-where-a-decision-landed
description: Don't say a decision is "worth recording" — say which file, fixture or issue it went into, and whether it is enforced or only documented.
type: feedback
---

When I summarise a decision to this maintainer, I must name **where it now lives** and whether
anything makes it true. They asked "so where did this go?" about a section I had headed *"Two
decisions worth recording"* — the decisions had in fact landed in four places each, but I had
reported the reasoning without the location, so they had no way to tell recording from narrating.

**Why:** "worth recording" describes an intention. In this repo the whole thesis is that prose
states a rule and only a check makes it true, so a decision reported without its location is
indistinguishable from one that was merely mentioned in chat and lost. PR bodies and commit
messages are the least durable places and I over-use them; nobody greps a merged PR.

**How to apply:** for each decision, state the durable home and its strength — a **selftest
fixture** (fails if reversed, strongest), **CLAUDE.md** (loaded every session), **the issue**
(the authority for architecture calls with no upstream, and CLAUDE.md requires the CHANGELOG link
to it), or a **code comment** (read when editing). Say plainly when something is only documented
rather than enforced, instead of implying parity. Related: [[verify-counts-before-stating-them]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, name-where-a-decision-landed.md._

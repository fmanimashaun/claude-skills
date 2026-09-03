---
name: feedback-grep-our-own-corpus-for-reported-misuse
description: When a downstream project reports a wrong pattern, search our shipped examples first — they probably copied it from us.
type: feedback
---

A downstream misuse report is a lead to grep **our own shipped doctrine**, not just a bug in
their project. #750 reported `bg-fm-navy/50` (a brand primitive where a role belongs) from a live
project; the detector written for it found the identical line in
`skills/design-system/references/component-implementations.md:383`. They had copied it from us.

**Why:** doctrine is read verbatim by other people's agents, so a wrong example propagates into
every project that follows it. The report is downstream evidence that upstream is wrong.

**How to apply:** before implementing a reported misuse as "their bug", grep the corpus for the
exact pattern. If a new detector fires on our own files, the doctrine is the bug — never tune the
rule to make our files pass. Related: [[downstream-runs-beat-code-review]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, grep-our-own-corpus-for-reported-misuse.md._

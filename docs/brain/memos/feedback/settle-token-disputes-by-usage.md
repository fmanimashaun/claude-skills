---
name: feedback-settle-token-disputes-by-usage
description: When two sources declare a design token differently, count the call sites and measure contrast — the declarations cannot settle it.
type: feedback
---

Two artboards declared `--slate-400` differently and reading the declarations was a stalemate.
Counting **usage** settled it in one command: the 400 appeared twice against the 500's 59, and on
the paper ground the 400 is 2.78:1 (fails AA) where the 500 is 5.35:1. Two call sites had used a
light neutral as body text, found it illegible, and darkened the **token** rather than moving up a
step — a real fix applied one layer too low, collapsing the scale for everything else.

**Why:** a token's declared value is an opinion; its call sites and contrast ratios are facts. A
value edited to rescue two call sites is a scale defect wearing a colour change.

**How to apply:** count references per step and compute contrast against the actual ground before
changing any token value. If the minority usage is what motivated the change, fix the call sites
instead. Record the decision on the issue — design choices have no upstream to cite. Related:
[[verify-counts-before-stating-them]], [[name-where-a-decision-landed]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, settle-token-disputes-by-usage.md._

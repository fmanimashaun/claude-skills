---
name: feedback-clear-filed-issues-before-the-next-feature
description: Fixing a defect then starting the next feature compounds it — clear the filed issues first, and prefer fixing over filing in the first place.
type: feedback
---

Two corrections from the maintainer, minutes apart, on Retask (2026-09-08): **"are you just filing and
not fixing?"** and then **"if you fix a bug, b4 taking a next feature work, we tackle the issue filed
next so that we won't compond the issue in the next feature build."**

I had filed two defects during F-06/F-08 — a radio group with no fieldset (#146) and unreachable
first-run dashboard copy (#154) — and moved straight on to the next feature both times. My stated
reason for #146 was Retask's own CLAUDE.md rule, *"never stack several unrelated fixes on the
checked-out branch"*. That rule says give a fix its own branch; it does not say defer it. And when I
finally measured the blast radius I had claimed, it was wrong: the admin action modals already built
their own fieldset, so the change touched two inputs, not the app.

**Why:** a defect left open under a feature gets built on top of. I had already shipped the same
fieldset defect twice — in the `form_type` group and again in `collection_mode` — filing it both
times. The second instance existed *because* the first was still open.

**How to apply:** prefer fixing to filing, and check the deferral reason by measuring before writing
it down — "app-wide reach" is a claim, not an excuse. File only what genuinely needs the owner's
decision, and say so in one line. When something is filed, clear it on its own branch **before**
starting the next feature, not after. Related: [[fix-defects-in-the-same-work]],
[[verify-counts-before-stating-them]], [[a-missing-template-is-not-a-missing-design]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, clear-filed-issues-before-the-next-feature.md._

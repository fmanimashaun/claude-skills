---
name: feedback-verify-a-source-exists-before-routing-it
description: Three issues quoted a "design manual supplied by the maintainer"; I verified every framework claim and never checked the manual existed. It did not. Ask when a named source cannot be found.
type: feedback
---

Issues #976–#978 in claude-skills quoted a "B2B Enterprise UI/UX Design System Manual supplied by the maintainer". I searched the repo, the downstream repo and its history, and the home folders, found nothing, noted "the manual itself isn't on disk" — and routed it anyway from the issue's quotations, wrote a routing record treating it as a registered source, and framed nine doctrine passages as "the manual says…". The maintainer's reply to the report: "which manual?" then "there is no such manual please". A same-day correction PR had to unwind the provenance everywhere.

**Why:** the doctrine gate verifies what a source *says*; nothing verified that a source *existed*. The issue bodies were written by a downstream Claude session that had already written "the enterprise design manual" into its own project notes, so the belief was self-reinforcing across sessions — two agents agreeing is not evidence (see [[a-number-two-sessions-agree-on-can-still-be-wrong]]). Quotation marks around text nobody can produce are a claim, not a citation.

**How to apply:** when an issue or note names a document, artefact or decision as its source, prove existence first — `ls`, `git log -S`, a grep for a distinctive phrase, a link that resolves. If it cannot be found, **stop and ask** the maintainer before building on it; a search that comes up empty is a blocking finding, not a footnote. Never write "the X says" for an X you have not opened. Related: [[grep-our-own-corpus-for-reported-misuse]], [[name-where-a-decision-landed]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, verify-a-source-exists-before-routing-it.md._

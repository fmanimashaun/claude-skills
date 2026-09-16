# 2026-09-16 — there is no enterprise design manual

**What happened.** Issues #976, #977 and #978 (filed 15 Sep 2026 from a downstream Retask session via
`/rails-flow:report`) attributed their proposals to a *"B2B Enterprise UI/UX Design System Manual
supplied by the maintainer on 15 Sep 2026"*, quoting it — an 8px grid rule, a toast dismissal rule,
a 1440px cap, 256/64px rails, 56/32px row heights, 480/720px drawer bounds, a keyboard layer, an
empty-state typology, and more. #964, #966–#970 and #972 were said to have received detail from it.

The `/maintainer-work` session of 16 Sep 2026 could not find the document in this repo, in the Retask
repo or its history, or anywhere on the maintainer's machine, and **built on the issue's word anyway**:
it wrote a routing record treating the manual as a registered source, framed nine doctrine passages
as "the manual routed in #978 says…", and quoted it. PR #986 merged that to `dev`. Asked *"which
manual?"*, the maintainer answered: **"there is no such manual."**

**What this is.** The `issue-body-is-not-an-authority` failure from CLAUDE.md, in its sharpest form:
the session verified every *framework* claim the issues made (ARIA, WCAG, HTML, Turbo, Rails — all
CONFIRMED) and did not verify the *provenance* claim that a source existed. A quotation from a
document nobody can produce is not a citation; it is text of unknown origin wearing quotation marks.

**What was done about it.** Same day, before any promotion:

- The routing record (`2026-09-16-enterprise-manual-routing.md`) was **deleted**, not annotated — a
  record of a non-existent document's sections is misleading with any note on it. This file replaces it.
- Every passage that named the manual now names the **issue** as a proposal, with no quotation marks:
  `foundations-tokens.md` §3b, `components.md` (Toast, Empty state, Permissions matrix, Background
  operation), `forms.md` (Unsaved changes), `interaction-stimulus.md` (keyboard layer), `responsive.md`
  (above 1536px), the `check_structural_grid.py` docstring, the doctrine-map row note, and the three
  CHANGELOG bullets.
- **Every decision was re-read on its own merits and kept**, because none of them rested on the manual's
  authority: they rest on measured downstream defects (Retask #268, #258, D-061, the 236px rail), on
  verified standards, or on an explicit choice now marked as ours. Figures that the first version said
  were "adopted from the manual" — row heights 56 / 32, the 48px selection column, the 480 / 720 drawer
  bounds — are now stated as **chosen in the structural block with no external source**, which is
  what they always were. The maintainer can change any of them by editing the block; the gate keeps
  whatever is chosen on the grid.

**Where the false provenance came from** is not established. The Retask session that filed the issues
also wrote *"the enterprise design manual"* into Retask's `docs/brain/OPEN-QUESTIONS.md` Q3, so the
belief predates the issues. That file is Retask's to correct.

**The rule this adds.** A source named in an issue is verified to *exist* before anything is routed
from it — `ls`, `git log -S`, a grep for a distinctive phrase — and when it cannot be found, the
session **stops and asks** rather than routing from quotations. The doctrine-verifier's gate covers
what a source *says*; this covers whether there is a source at all.

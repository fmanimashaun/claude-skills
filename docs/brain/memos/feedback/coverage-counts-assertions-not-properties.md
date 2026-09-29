---
name: feedback-coverage-counts-assertions-not-properties
description: A suite reported 49/49 routes and 0 failures while 83% of every table was hidden; boundary assertions pass on content crushed inside the viewport.
type: feedback
---

Retask's qa-flow run said 26 pass / 0 fail, route coverage 49/49, axe clean, 0 console errors. A
human browser review then found eight layout defects, including 71–83% of every data table hidden at
406px. Every green number was true and about something else.

Three compounding reasons, each worth checking in any suite:

- **The page list.** The responsive layer tested 5 pages against 86 routes, and none was an admin
  screen — while its own header said "add a route here in the same change that adds the page". A
  comment is not a mechanism.
- **The property.** Both overflow assertions measured the **viewport edge**
  (`scrollW <= clientW`, `rect.right > vw`). The defect was *inside* the viewport: the rail fit and
  main content was crushed to 118px. Per-element `scrollWidth - clientWidth` is the measurement that
  catches it, and it yields a percentage, which is what makes it actionable.
- **The exemption.** "A scroll container may hold something wider than itself" is right for
  "the page must not scroll" and removes the whole class of *reachable but invisible with no cue* —
  on macOS overlay scrollbars reserve no space, so 1650px in 938px looks finished.

**How to apply:** when a suite reports clean on something a person can see, ask which *property* was
asserted, not which pages were visited. "Covered" usually means "asserted", and the assertion is
often "it renders". See [[a-diagnostic-object-is-not-a-pass]] and [[downstream-runs-beat-code-review]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, coverage-counts-assertions-not-properties.md._

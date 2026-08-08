# QA and evidence

`qa-flow` exists because a build agent cannot verify itself. Everything below follows from that.

## Evidence, not assurances

A QA pass produces artefacts: screenshots, computed styles, HTTP traces, coverage rows, a walked
route list. A human can re-check any of them. *"I tested it and it works"* is not evidence — it is a
claim with the same standing as the one it was meant to check.

`validate_evidence.py` gates the evidence itself, and refuses shapes that look complete and are not:

- **counters that cannot be true** — more elements missing a focus indicator than were ever focused
- **sampling that hides itself** — 25 of 72 pages walked while reporting nothing missing
- **a blocking finding with no method recorded** — a severity-1 must show how it was decided

## Severity is recomputed, never argued

`S1` / `S2` are derived from the counters, so they cannot be talked down in prose. Unreachable
elements, a missing focus indicator, or any overlay failure → **S1**.

## What it refuses to do

- **It does not read the diff.** Cases come from the brief. A pass that reads the diff tests what
  changed, which is the set least likely to be broken.
- **It does not enumerate with `element.focus()`.** `:focus-visible` deliberately may not match
  programmatic focus, so that approach reports *every* element as having no indicator. Real `Tab`
  keypresses only.
- **It does not decide an indicator by property lookup.** It diffs the computed style at rest
  against the same element focused, and treats **any** rendered difference as an indicator. A
  property lookup once flagged a conformant design system on every page: the ring lived in
  `box-shadow` while `outline` read `none`.

## The engine is part of the contract

Playwright's **WebKit inherits the macOS default** where Tab reaches text fields and lists only —
not links or buttons — unless Full Keyboard Access is on. A keyboard audit run there under-reports
without erroring, so the engine is recorded with the results and chromium or firefox is preferred.

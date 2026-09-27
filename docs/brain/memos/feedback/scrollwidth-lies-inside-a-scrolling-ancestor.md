---
name: feedback-scrollwidth-lies-inside-a-scrolling-ancestor
description: An overflow test that compares scrollWidth to clientWidth passes on broken markup when an ancestor scrolls vertically.
type: feedback
---

CSS computes `overflow-x` to `auto` whenever `overflow-y` is not `visible`. The app shell's main
region is `overflow-y-auto`, so **content that spills sideways scrolls inside it** — the offending
row's own `scrollWidth` does not grow, and `document.documentElement.scrollWidth` does not either.
A test written as `row.scrollWidth - row.clientWidth <= 1` plus a document-width check therefore
**passes on markup with `whitespace-nowrap`**, which is how I proved it.

**Why:** this is the second time the same fact has cost me a working measurement — the first was
`layout_fit.py` exempting everything inside a vertically scrolling region. It reads as "the layout
is fine" rather than as "the check is blind", so nothing prompts a second look.

**How to apply:** ask what is actually wrong when text does not wrap — part of the *text element* is
unreadable, and the *row* extends past the viewport. So measure the text node against its own box
(`name.scrollWidth - name.clientWidth`) and the row's `getBoundingClientRect().right` against
`window.innerWidth`. Then mutate the markup (swap `wrap-anywhere` for `whitespace-nowrap`) and
confirm the test goes red; on the real markup alone it tells you nothing. Related:
[[inline-style-beats-every-breakpoint]], [[coverage-counts-assertions-not-properties]].

Also: a layout crawler cannot measure UI that is `hidden` until a user acts (an upload manifest, a
picker panel). Those need their own case that performs the action at the small viewport.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, scrollwidth-lies-inside-a-scrolling-ancestor.md._

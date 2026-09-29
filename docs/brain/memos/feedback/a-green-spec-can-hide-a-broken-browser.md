---
name: feedback-a-green-spec-can-hide-a-broken-browser
description: A request spec asserts the server's body; Turbo can discard that body outright. Drive forms and modals from the screen.
type: feedback
---

A request spec asserts the response body. Turbo decides separately whether to *use* it, so a spec
can be green while the screen does nothing. Twice on Retask:

- **A frame-only body dropped.** A direct POST of an action modal passed; from the open modal it was
  a frame exchange, the failure re-rendered `layout: false` with `data-turbo-frame="_top"`, and the
  modal blanked (#85, found by QA after the specs were green).
- **A 200 of HTML in reply to a form submission is discarded.** Turbo Drive requires a form response
  to REDIRECT and logs "Form responses must redirect to another location". F-16's CSV upload
  rendered its report from the POST — 200, all four lists asserted, request spec green — and the
  browser stayed on the previous page. Fix: `data: { turbo: false }` on that form, which is honest
  when the reply genuinely cannot be rebuilt by a later GET. Answering 422 to make Turbo render a
  page where nothing was invalid would be a lie in the status code.

**Why:** the spec and the browser make different requests, and even on the same request Turbo's
rules about what a response may be are not the server's.

**How to apply:** any form or modal gets a regression test that clicks it **from the screen**. If a
POST does not redirect, expect Turbo to drop it and say so at the form. When a spec and a browser
disagree, capture what the browser actually received before blaming either. Related:
[[downstream-runs-beat-code-review]], [[proving-the-helper-is-not-proving-the-caller]],
[[a-post-rendered-page-escapes-every-crawl]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-green-spec-can-hide-a-broken-browser.md._

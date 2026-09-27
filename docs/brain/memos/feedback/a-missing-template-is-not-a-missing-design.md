---
name: feedback-a-missing-template-is-not-a-missing-design
description: A MissingTemplate rescue is not evidence the surface is unbuilt — grep for the ported component before composing a page by hand.
type: feedback
---

In Retask (2026-09-07) `ApplicationController#render_forbidden` read `render "errors/show"` with a
`rescue ActionView::MissingTemplate` behind it. I proved the rescue was firing — every refusal in the
app answered a zero-byte 403 — and "fixed" it by writing `app/views/errors/show.html.erb` myself,
composing it from the placeholder screen under D-041. It rendered, the specs went green, and it was
wrong: `Ui::ErrorPageComponent` had been ported from the "Error states" canvas on 29 Aug, with a 403
case already worded. `errors#show` is an **action** that renders that component; no template ever
stood behind the name. I had shipped a second error design onto the path most refusals take.

**Why:** a missing template proves a *name* resolves to nothing, never that the *surface* does not
exist. The surface can be a ViewComponent, a controller action, a static file in `public/`, or a
page from a different canvas — none of which a MissingTemplate error mentions. D-041 (compose an
undrawn page from one doing the same job) only applies where nothing is drawn, so reaching for it
without checking first is how a ported canvas gets quietly duplicated.

**How to apply:** before composing any page, grep the repo for the concept — component class, CASES
or registry constant, `public/*.html`, an existing route — not just the template path in the error.
Then check the design project's own file list: `DesignSync` `list_files` on the project shows what
was drawn, and `get_file` reads it. When wiring finally reaches a designed surface, assert the
**design's own copy** in the spec, not the status code: this one returned a correct 403 for months
with an empty body, and every status assertion passed. Related: [[design-is-the-source-of-truth]],
[[a-diagnostic-object-is-not-a-pass]], [[grep-our-own-corpus-for-reported-misuse]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-missing-template-is-not-a-missing-design.md._

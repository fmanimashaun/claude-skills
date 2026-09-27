---
name: feedback-a-source-grep-cannot-see-a-rendered-attribute
description: An id emitted by a component or interpolated at render time is invisible to any grep over the views; absent-in-source looks identical to supplied-by-the-layer-below.
type: feedback
---

I filed an issue accusing a merged PR of breaking four dialogs' accessible names, because
`grep id="add-client-title" app/views` returned nothing. The id is rendered by the component:

    modal_component.html.erb:25   aria-labelledby="<%= labelledby %>"
    modal_component.html.erb:38   <h2 id="<%= labelledby %>" …><%= title %></h2>

Every dialog was correctly named. Worse, what the PR removed was a **duplicate** of that id — so it
had *fixed* an a11y defect and my issue claimed the reverse. I had to close it and correct it
publicly.

**I hit the same trap twice within the hour.** A literal grep for `phone-label` across `app/views`
also returns nothing, because that id is derived — `label_id = "#{dial_id}_label"` — and exists only
at render time. I caught the second and not the first.

**Why:** `git show origin/dev:<path>` fixed *which commit* I was reading and left *which layer*
unexamined. A view's source is a true reading of the view and not of the document the browser
receives. **A missing `id=` in source looks identical whether the id is absent or supplied below.**
Same family as [[a-true-result-about-the-wrong-file]] — correct measurement, wrong subject — and as
[[a-count-of-a-string-is-not-a-count-of-the-thing]].

**How to apply:** before concluding an attribute is missing, ask **what else could emit it** —
a ViewComponent, a partial, a helper, an interpolation, JavaScript. Render the thing and look, or
read the component template, before filing. And when proposing a guard for this class, put it at the
**rendered-document** layer: a source-level rule here would have failed on every correctly-built
modal in the app, and the only way to satisfy it would be to reintroduce the duplicate ids that were
just removed — [[a-check-that-cannot-tell-the-two-apart]].

The corollary I keep relearning: **verify a peer's refutation too.** They were right, and I confirmed
the mechanism myself before closing rather than closing on their say-so
([[a-number-two-sessions-agree-on-can-still-be-wrong]]).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-source-grep-cannot-see-a-rendered-attribute.md._

---
name: feedback-a-post-rendered-page-escapes-every-crawl
description: Route sweeps, layout crawls and coverage tables only navigate GETs, so a page rendered from a POST is invisible to all of them.
type: feedback
---

Every crawl-shaped gate navigates: the route sweep, the responsive/layout crawl, the interaction
sweep, the coverage denominator. A page that only exists as the reply to a POST is reachable by
none of them, so it lands in no denominator and reads as neither covered nor missing. On Retask,
F-16's §15.3 "CSV validation result" — four three-column tables, exactly the shape that spills —
would have been the one built page never measured at 390×844.

**Why:** the gate's coverage number stays green because the page was never a row in it. This is the
same failure as [[check-the-denominator-not-the-percentage]] arriving through the door rather than
through a parser drop.

**How to apply:** when a feature renders a screen from a POST, put the layout/overflow assertion
inside the one browser test that can drive it, and **extract the evaluator to a shared module**
rather than copying it — the crawl's copy usually carries the comment recording how the rule was
got wrong, and two copies drift. Then prove the new assertion can fail (inject an undeclared wide
block into that view). Related: [[scrollwidth-lies-inside-a-scrolling-ancestor]],
[[a-green-spec-can-hide-a-broken-browser]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-post-rendered-page-escapes-every-crawl.md._

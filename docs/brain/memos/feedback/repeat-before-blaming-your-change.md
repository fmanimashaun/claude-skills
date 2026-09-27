---
name: feedback-repeat-before-blaming-your-change
description: One run each said my change broke a test; six runs each said it was flaky and worse on the baseline. Repeat on both sides before attributing.
type: feedback
---

A browser test failed on my branch and passed on `dev` — one run each. I was about to treat it as my
regression. With `--repeat-each=6 --retries=0` it was **3/6 failing on my branch and 5/6 on `dev`**:
a pre-existing race, worse on the baseline, and nothing to do with my change (Retask #118).

**Why:** a single run of a racy test is a coin flip, and the direction of a coin flip is the most
persuasive wrong evidence there is — it points at the thing you just touched.

**How to apply:** before attributing a failure to your own diff, run it repeatedly on **both**
sides with retries off, and quote both fractions. If the baseline also fails, you have found a
second defect to file, not a regression to fix. Then say which is which in the PR, so the red test
is not silently inherited. See [[a-diagnostic-object-is-not-a-pass]] and
[[downstream-runs-beat-code-review]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, repeat-before-blaming-your-change.md._

---
name: feedback-a-lookup-whose-key-you-assumed
description: An empty or zero result from a lookup whose key you guessed looks identical to a real negative; confirm one case you can see by eye before believing the aggregate.
type: feedback
---

Three times in one evening, in three disguises, the same defect: **a lookup keyed on something I
assumed rather than read, returning a clean-looking answer.**

1. **Controller split.** `routes.json` records `"printing_stock#queries"`. I split on `/` instead of
   `#`, so every comparison failed and the intersection returned **0 routes affected by a live PR**.
   The true answer was **14**. That result was one message away from "no conflict, push freely".
2. **Helper grep.** Searching `application_path` for callers of `/applications/:reference` found
   **eight healthy callers** — all belonging to `/application` (singular), a different route four
   lines above it in `routes.rb`. The helpers differ by the word `reference`; the path fragment
   matches both. It made an orphan look well-used.
3. **Permission key.** Looking up roles by the GUARD name — `provisioner`, `invoice_reader`,
   `custody` — returned **"(no role holds it)" three times**, which reads as "no persona can reach
   these routes". The guards check `provision_identities`, `view_all_earnings` and `dispatch_batch`.
   Three capturable routes would have gone into the blocked column.

**Why:** a wrong key and a true negative produce the same empty set. Unlike a crash, there is nothing
to be suspicious of — the query ran, the file parsed, the count printed. This is the
apparatus-failure family (`[[a-harness-that-cannot-see-a-broken-mutation]]`,
`[[a-check-that-cannot-tell-the-two-apart]]`) arriving in the *lookup* rather than in the check.

**How to apply:** before believing an aggregate, **assert one case you can confirm by eye**. All three
above were caught that way and by nothing else — `/printing-stock/queries` was visibly in both sets,
so a zero intersection was impossible; three consecutive "no role holds it" was implausible. Put the
control in the script, above the result:

```python
control = [r for r in rs if r["pattern"] == "/printing-stock/queries"]
assert control and ctrl_of(control[0]) == "printing_stock", "mapping is wrong"
```

And for authorisation specifically: **read the guard body, never infer the permission from the guard's
name.** `require_<x>` almost never checks `"<x>"`.

Related: [[verify-counts-before-stating-them]], [[check-the-denominator-not-the-percentage]],
[[a-criterion-can-name-a-route-that-404s]], [[grep-our-own-corpus-for-reported-misuse]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-lookup-whose-key-you-assumed.md._

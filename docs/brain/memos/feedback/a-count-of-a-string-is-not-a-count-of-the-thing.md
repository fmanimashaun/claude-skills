---
name: feedback-a-count-of-a-string-is-not-a-count-of-the-thing
description: Three tools gave three different answers for "how many Unreleased headings" — 12, 10, 2; match whole lines and say which unit you counted.
type: feedback
---

Arming a release, I needed the number of `### Unreleased` **headings**. Three measurements, three
answers, all "correct":

- `s.count("### Unreleased")` → **12** — counts every substring, including prose quoting the marker
- `grep -c '`### Unreleased`'` → **10** — counts backticked prose mentions
- lines where `l.strip() == "### Unreleased"` → **2** — the actual headings

I then told the maintainer "this release's own bullets quote it ten times". Wrong again: 2 were in
this release, **8 were in older published entries**. They asked "10 proses?" and it fell apart.

The near-miss was serious: a `str.replace` would have rewritten all ten, including eight inside
published release blocks, and the published-blocks gate would have reported eight losses.

**Why:** a string can appear in prose, in a quotation, in a heading, and in a path. Counting the
string answers a different question from counting the thing, and the two numbers diverge silently —
both look like plausible totals.

**How to apply:** for any structural count, match the whole line or parse the structure, never
`count()` on a substring. Before quoting a figure, state the unit to yourself — "headings, not
mentions" — and if a follow-up asks about the number, re-derive it rather than defending it. When
the count guards a destructive edit, assert the expected value and stop on mismatch; that assertion
is what saved this one. See [[verify-counts-before-stating-them]] and [[a-lookup-whose-key-you-assumed]].

## The EXCLUSION is the dangerous half, and it eats the worst cases (2026-09-22)

Counting raw `<button>` elements for Retask #547, I ran:

    grep -rn "<button" app/views | grep -v "button_to\|ButtonComponent"

and reported **9**. The gate said **11**. The gate was right, and I had broadcast 9 to two sessions.

The filter was meant to skip legitimate component usage. What it actually removed was:

    <button type="button" class="<%= Ui::ButtonComponent.classes_for(variant: :outline, ...) %>"
    <button type="button" class="<%= Ui::ButtonComponent.classes_for(variant: :primary,  ...) %>"

**Raw elements reaching into the component for its class string** — the silent fork the doctrine
exists to catch, in its most deceptive form. My exclusion could not tell *renders the component*
from *copies the component's classes onto a hand-rolled element*, and the second is the defect.

**Why this is worse than over-counting.** A noisy filter produces false positives, which someone
reads and discards. An exclusion filter produces **false negatives that look like correct usage** —
they are removed precisely because they resemble the thing you are willing to ignore. The nearer a
true positive is to the legitimate pattern, the likelier the filter eats it. So the cases that
survive the filter are the obvious ones, and the ones it silently drops are the subtle ones you
most needed.

**How to apply:** a `grep -v` in a counting pipeline is a claim that needs its own test. Before
trusting the total, take **one case you know is a true positive and one you know is a true
negative**, run the filter over both, and confirm it classifies each correctly — a filter never
shown to separate the two cases has not been tested ([[a-check-that-cannot-tell-the-two-apart]]).
Better still, when a real detector for the thing already exists (a gate, a linter), quote ITS number
rather than re-deriving with grep; I had the doctrine sweep's own count available and re-measured
badly instead. And when a peer's number disagrees with yours, re-derive before defending — dc was
right, and it took one unfiltered `grep -n` to see it.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-count-of-a-string-is-not-a-count-of-the-thing.md._

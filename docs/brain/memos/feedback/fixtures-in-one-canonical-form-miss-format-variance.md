---
name: feedback-fixtures-in-one-canonical-form-miss-format-variance
description: Every SHA fixture was 40 chars, so `==` on a commit shipped and refused a fresh inventory; test the renderings the data actually arrives in.
type: feedback
---

v1.133.0 shipped a gate that compared a recorded commit to `HEAD` with `==`. Git abbreviates a SHA
to an unambiguous prefix whose length is **not fixed** — it grows with the repository and is
configurable (`core.abbrev`) — so a downstream CI job got:

```
REFUSING to report coverage: the route inventory was enumerated from 978814d
but the working tree is at 978814d29.
```

**The same commit.** The `enumerate` and the report ran in one job, seconds apart, on one tree, so
the gate refused the only state it must always accept, and blocked that project on every PR.

**Why the tests missed it: every fixture used two 40-character strings.** Nothing asserted that a
real SHA and its abbreviation are one commit, so the check passed its whole suite — and its whole
mutation guard — while being wrong about the only shape it meets in production.

**Why:** fixtures get written in whatever canonical form is easiest to type. Real data arrives in
whatever form its producer emitted. A suite built only from the canonical form tests the author's
formatting habit, not the contract.

**How to apply:** when a check compares identifiers, ask what *renderings* that value legitimately
has — abbreviated vs full SHAs, case, trailing slashes, `http` vs `https`, with/without `.git`, a
path vs its contents — and put at least one non-canonical pair in the fixtures. Compare semantically
(`same_commit()`), not with `==`. Keep a floor on any prefix match (git's is 7) so the widening
stays a match and not a licence, and add the control that proves two genuinely different values
still differ **in the non-canonical form**. It also failed *convincingly*, with a well-formed
message naming a real concern — worse than crashing, because it reads as a true positive. Related:
[[a-guard-reading-ambient-state-is-vacuous-when-staged]], [[a-lookup-whose-key-you-assumed]],
[[a-check-that-cannot-tell-the-two-apart]].

## The matcher has the same defect, and proving it fires does not catch it (2026-09-22)

I wrote a guard asserting every credential email states the lifetime that enforces it, keyed to
`/expires (?:in|after) (\d+) minutes/`. **I proved it fires — twice, on two mutations — and both
mutations used the one phrasing I had written the regex around.** Tested against what a person
would actually write:

    CAUGHT  The link expires in 10 minutes.
    MISSED  This link is valid for 10 minutes.
    MISSED  The link lasts 10 minutes.
    MISSED  Use it within 10 minutes.
    MISSED  You have 10 minutes to use this link.

**A guard keyed to one phrasing is a guard against one author** — and mine was a guard against me.
`[[a-rule-without-a-trigger-changes-nothing]]` says gate the consequence; this is the next question
after it: *does the trigger fire on shapes I did not write?*

**How to apply:** proving a guard fails is necessary and not sufficient — **mutate it in a shape you
did NOT design it around.** Where possible remove the phrasing question entirely: I changed the
check to "every `\d+ minutes` in this entry must equal its TTL", which has no verb list to keep
current. Where a verb list is unavoidable (a task duration is not an expiry, and three real entries
legitimately say "about 20 minutes"), **give the matcher its own control** — assert it against both
the cases it must catch and the cases it must not, because a pattern never shown both has not been
tested, only observed not to fire ([[a-check-that-cannot-tell-the-two-apart]]).

A peer arrived at the same thing from the other direction the same hour: their grep excluded every
`<button` line containing `ButtonComponent`, which silently removed the true positives — raw
elements reaching into the component for its class string. **Whatever a filter excludes, the entries
it removes are the ones that look most like correct usage** ([[a-count-of-a-string-is-not-a-count-of-the-thing]]).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, fixtures-in-one-canonical-form-miss-format-variance.md._

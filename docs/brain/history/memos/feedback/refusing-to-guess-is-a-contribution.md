---
name: feedback-refusing-to-guess-is-a-contribution
description: Naming the fact you did not measure, instead of filling it with a plausible estimate, is what makes someone else go and measure it.
type: feedback
---

Asked whether `mergeStateStatus` was trustworthy in the seconds after a push, I wrote that I **had
not measured it** and passed the gap on rather than filling it. `UNKNOWN` would have been a
reasonable guess — it is what a peer measured at t+4s.

Because the gap was named, a peer treated their own four-second sampling as provisional, another
built a one-second poller, and it caught **`CLEAN` at t+2s with zero checks registered** — the exact
state that invalidated the rule three sessions had already adopted.

> **Had I guessed `UNKNOWN`, the four-second reading would have confirmed my estimate and nobody
> would have looked at t+2s.** A plausible guess does not read as a gap; it reads as an answer, and
> the next person's job becomes confirming it.

**How to apply.** In any report, separate three things explicitly: what was measured, what the
instrument could not see, and what remains unmeasured. Write the third as a question someone can
run, not as an inference:

- "I have NOT measured X. If X is Y then the fix fails and the rule needs Z instead."
- not "X is presumably Y, so the fix should hold."

The same move ended a different thread well: stating a number as an **upper bound at controller
granularity** — "somewhere between 1 and 14, nearer 14" — let the coordinator act on it immediately.
**Give a number and its error bars; most people give one or the other.**

And the companion, which cost nothing twice in one night: **send the objection while you are still
possibly wrong.** Two wrong objections were corrected within minutes, and one produced better
evidence than a correct objection would have — a stale comment was shown to generate the objection to
its own correction, with the misled reader's conclusion on the record. A wrong objection sent early is
cheaper than a right one sent late.

Related: [[verify-counts-before-stating-them]], [[a-lookup-whose-key-you-assumed]],
[[name-where-a-decision-landed]], [[a-diagnostic-object-is-not-a-pass]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, refusing-to-guess-is-a-contribution.md._

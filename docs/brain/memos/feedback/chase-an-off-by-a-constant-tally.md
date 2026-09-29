---
name: feedback-chase-an-off-by-a-constant-tally
description: A tally that is short by the same small number every time is a bug, not noise — and a reporter's unmarked lines can make a red run read as green.
type: feedback
---

Two tally anomalies in one Retask session (2026-09-08), both noticed and both walked past.

**"99 passed"** from Playwright's `list` reporter, when the filter matched 200 cases. The trailing
lines had no `✓` and I read them as progress output; they were the **101 failures**. Only
`--reporter=json`, parsed, gave `{'unexpected': 101, 'expected': 99}`. I had already started writing
up a green result.

**"short by exactly one, six times."** Six per-persona crawls each returned one route fewer than
planned (48/49, 8/9, 5/6, 3/4, 18/19, 4/5). I registered the pattern, called the totals plausible,
and moved on — twice. The cause was a route file written without a trailing newline, so the shell's
`while IFS= read -r line` dropped every file's last line. `/work` was one of them. One `+ "\n"`
recovered twelve routes.

**Why:** a constant offset is the signature of a systematic bug — an off-by-one, a dropped line, a
filter — and it is precisely the shape that looks like rounding. Random noise varies; `n-1` every
time does not. And a summary line is a *claim* by the reporter, not a measurement: if the number
does not match what I asked for, the reporter is not the place to settle it.

**How to apply:** before quoting a tally, reconcile it against the count you expected, and treat any
constant difference as unexplained until you find the mechanism. Never read pass/fail off a
human-formatted reporter — take the machine format (`--reporter=json`) and count the statuses
yourself. Related: [[check-the-denominator-not-the-percentage]],
[[a-number-two-sessions-agree-on-can-still-be-wrong]], [[a-diagnostic-object-is-not-a-pass]],
[[verify-counts-before-stating-them]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, chase-an-off-by-a-constant-tally.md._

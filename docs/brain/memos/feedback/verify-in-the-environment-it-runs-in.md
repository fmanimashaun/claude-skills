---
name: feedback-verify-in-the-environment-it-runs-in
description: A test run in an interactive shell can silently exercise different binaries than the hook or script under test will get.
type: feedback
---

When verifying a fix that depends on **which binary resolves**, run the test in the environment the
code will actually run in — not the interactive shell.

Testing a `stop-gate.sh` fix that routes `bundle` through mise, I put a fake `mise` first on `PATH`
and the test "passed" while proving nothing: in an interactive shell `mise` is a **shell function**
(installed by `mise activate`), so a function always beats a `PATH` entry and the real mise ran.
Hooks run **non-interactive**, where the binary at `~/.local/bin/mise` does resolve. Re-tested with
`env -i PATH=... sh -c '...'` and only then saw the routing actually work.

**Why:** `command -v X` returning a bare name rather than a path is the tell that X is a function or
alias. The same trap covers aliases, shell builtins shadowing binaries, and anything a profile
injects — none of which the harness that runs the code will have.

**How to apply:** for hooks and scripts, verify with `env -i` and an explicit `PATH`. If
`command -v` prints something without a `/`, the interactive shell is lying to you about what the
code will find.

**A GATE'S INPUT MUST BE CAPTURED BY THE APPARATUS THAT ENFORCES IT.** 2026-09-17, Retask #441: I
restored the coverage ratchet's baseline from "a real measurement from a passing full run" — mine,
taken with `bin/rails db:test:prepare` (0 settings). CI runs `db:prepare` (71 settings), and eleven
branches only execute when a setting does **not** already exist. Recorded floor `branch 75.1`;
CI can reach `74.80`. **A floor no run of the checking apparatus could ever produce**, so `dev`'s
test job was red for every session until someone traced it — and another session nearly took the
blame with a clean, true, wrong story about an unrelated memoisation.

The sting: two hours earlier, in #433, I had fixed the *same class* — `Setting.create!` green on my
bare database and red on CI's seeded one — and written in that PR that the fix had to hold on
**both** states, because holding on one is how it got in. I applied the lesson to a spec and missed
it in my own gate's input.

The guard I shipped alongside it could not see this by construction: it asks *"did a subset run move
the baseline"*, hashing before and after its own probe, and has nothing to say about **which
database produced the committed number**. Not wrong — answering a narrower question than the file's
failure mode, which is its own thing to notice when you write one.

**How to apply:** before committing any recorded threshold, floor or baseline, ask *which apparatus
will enforce this, and did the same one produce it?* If a number is captured locally and checked in
CI, capture it the way CI does — or make the two setups identical and say so. A number that the
checker cannot reproduce is not a floor, it is a permanent red.

Related: [[fix-defects-in-the-same-work]], [[verify-counts-before-stating-them]],
[[a-ratchet-inherits-the-last-runs-state]], [[ratchet-a-baseline-dont-set-a-threshold]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, verify-in-the-environment-it-runs-in.md._

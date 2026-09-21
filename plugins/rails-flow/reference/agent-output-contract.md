# Agent output contract — what an agent returns, and why it is a different budget

The decision record behind `scripts/check_agent_output_contract.py`. Filed as
[#1086](https://github.com/fmanimashaun/claude-skills/issues/1086).

## The fact that makes this its own budget

**An agent's final message lands in the parent conversation and stays there for the rest of the
session.** It is not a one-off cost like the agent's own turns; it is a permanent tax on every
subsequent request the parent makes.

That is why this is not the same question as `reference/model-tiers.md`. Model tier governs what
the agent's *own* work costs and is already settled deliberately, with citations, on #127 — six
agents pinned `haiku`, twenty-three on `inherit` because a pin is a cap in both directions and
pinning downward would spend a user's Opus upgrade for them. **That decision is correct and this
document does not reopen it.** It simply governs a different half: what the *answer* costs, forever.

Measured when this was written: **29 shipped agents, and 2 declared any output contract at all.**

## The two contracts, and they are the two that already worked

Neither was invented. Both are lifted from the shipped agents that had thought about it:

**1. A bounded structured verdict** — `rails-flow/claim-verifier`. A fixed shape, one line per
finding with the evidence under it, ending in a tally:

```
CONFIRMED   "the sweep runs on every PR"
            gh run list --workflow=gates.yml → 12 runs, all pull_request events
            ci_verdict.py → 12 examined, 0 did-not-run (all executed steps)
REFUTED     "the publish is gated on it"
            release.yml has no `needs:` — the release job runs independently
2 of 4 claims stand. 1 refuted, 1 unverifiable.
```

The parent can act on every line. Nothing is restated back to it.

**2. Artifacts on disk, and a path** — `qa-flow/functional-tester`. The report, the CSV and the
screenshots are written to `qa/manual-tests/`, and what returns is where they are and the verdict.
The parent reads the file if it needs the detail and pays nothing if it does not.

**This second one is the real lever** and it is what any agent producing a long report should do.
It was already the pattern for several qa-flow agents; it was simply never stated as a rule.

## What an agent must not return

- **Content the parent already has.** File bodies it read, the diff it was given, the prompt.
- **The search that produced the finding.** Which greps were tried, what was ruled out. A finding
  is the answer; the path to it is not.
- **A restatement of the task.** The parent wrote the prompt.

If a finding genuinely needs 400 lines of evidence, that is contract 2: write it and return the path.

## Why a gate rather than a style note

Because this is the repository's recurring class, stated in `CLAUDE.md`: a guarantee written in
prose that nothing makes true. *"Keep your report short"* in a conventions document is advice; every
new agent will be written by someone who did not read it. `scripts/check_agent_output_contract.py`
requires a declared `## Output` section that either bounds the return or names a file.

**It checks the declaration, not the runtime behaviour**, and that boundary is deliberate. What an
agent actually emits depends on the model and the input; a check claiming to verify it would be a
gate that cannot fail. The declaration is exact, it is what a reader of the agent sees, and an agent
that has not been made to state its contract is one that has not thought about it.

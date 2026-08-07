---
description: Ask the human a question on a GitHub issue, park the thread, and pick the answer up on a later tick — the async human-in-the-loop. Pillar 3 of the autonomous flow driver. Nothing blocks: the human answers on their own schedule, the flow notices whenever it next cycles, and the state survives a restart.
---

# /rails-flow:escalate

When the flow hits a decision it **must not make alone**, it asks over GitHub and keeps working.

```
ask ─► comment + label ─► GitHub emails the human ─► [flow moves to other work]
                                                          │
 human answers on their own schedule ◄────────────────────┘
                                                          │
 later tick ─► poll ─► reply found ─► resume from it ◄─────┘
```

## Ask

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/escalation.py" \
  --ask 128 --question "Should deleting an account cascade to its invoices, or soft-delete?" \
  --resume-step "account-deletion-design"
```

Then **continue with other independent work**. Never wait on this.

## Poll, on each later tick

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/escalation.py" --poll
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/escalation.py" --list   # no network
```

`--poll` reports each parked thread as still-awaiting or ANSWERED, relabels the answered ones, and
records the reply in `docs/brain/.escalations.json` beside the rest of the brain. A thread whose
comments cannot be read stays parked and **does not fail the run** — one unreachable issue must not
stop an unattended flow.

## What to escalate — and what not to

Escalating everything kills the autonomy; escalating nothing goes off-rails.

| escalate | decide yourself |
|---|---|
| product scope / user-journey changes (IA-before-code) | which backlog item to take next |
| anything irreversible or destructive | implementation approach inside a frozen plan |
| the `dev → main` release | aesthetic and interface craft |
| spend or budget increases | filing app bugs and upstream reports |
| a requirement the PRD does not settle | merging to `dev` on green gates |
| a gate that cannot be satisfied without weakening it | |

## Two API facts this is built on

Both were verified against the real API, and each one breaks the loop completely if assumed away.

**1. The agent and the human have the same login.** `gh` authenticates with the user's own token,
so a comment the flow posts comes back authored by the repo owner — identical to `gh api user`.
Filtering replies "by author" therefore either never fires (excluding the owner excludes the human
too) or fires immediately on the flow's own question.

So every comment the flow posts opens with an invisible marker, and **a reply is any comment after
the question that does not carry it**. The marker must be at the *start*: a human quoting the
question reproduces the marker behind a `> `, and treating that as flow-authored would strand the
thread parked forever — the one failure this loop cannot recover from by itself.

**2. A missing label is not a soft failure.** `gh issue edit --add-label` **errors and applies
nothing** when the label does not exist. The label is what triggers the human's email, so a
missing one means the flow parks believing it asked while nobody was ever told. `awaiting-input`
and `answered` are therefore created before anything is posted, and **if they cannot be created,
the escalation is not sent** — an unsent escalation you can see beats a parked question nobody
receives.

## What is deliberately not a signal

**An edited comment.** Only `createdAt` is consulted. `updatedAt` also moves when the flow edits
its own comment, and a typo fix on an old comment would resume the flow with an "answer" that
predates the question. If the human edits instead of replying, the thread stays parked — visibly,
under its label — which is recoverable. A false resume is not.

## Verifying

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/escalation.py" --selftest
```

38 paired assertions. Five mutations were run against it — `startswith` weakened to `in`, the
marker check dropped, parking allowed after a failed label, the timestamp filter dropped, and an
unlabelled post treated as sent — each caught by the fixture named for it.

---
description: Pick the one next action from repository state and say whether you may take it alone — the autonomous driver's tick, with named stopping conditions and a configurable decision-rights policy.
---

# `/rails-flow:drive`

One tick of the autonomous flow driver. It answers exactly two questions: **what is next**, and **may
I do it without asking**.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/next_action.py" --state state.json
```

Exit **0** an action was chosen · **1** stopped, with the condition named · **2** unusable state.

**Exit 1 is not a failure.** A cleared backlog is the goal. Read the `stop` field, not the code.

## It chooses one thing, never a menu

A driver that returns three options has handed the decision back to the human it exists to spare. The
ladder, in order:

| state | action |
|---|---|
| open issues | `fix-issue` |
| none, but roadmap items | `build-feature` |
| nothing to build, work unverified | `run-qa` |
| all green and shippable | `promote` |
| none of the above | stop: `backlog-empty` |

Three conditions **outrank** all of them, and the order is the point:

1. **the breaker has stopped the run** — `breaker.py`'s verdict is not something this may overrule;
2. **the budget is spent**;
3. **a parked escalation is awaiting a reply** — take other independent work first; if there is none,
   this is the stop.

## Why the stop conditions are not implemented here

`breaker.py` in the pipeline plugin already owns attempt caps, the no-progress detector, the four
forbidden escapes, the elapsed and blast-radius limits, and the complete/partial/stopped verdict —
all of #128's doctrine, with its own selftest and mutations.

Re-implementing that here would create a **second** set of stop conditions that could disagree with
the first, and when two safety systems disagree the more permissive one wins. So run-level stops stay
`breaker.py`'s answer and this script refuses to proceed past them.

## The decision-rights matrix

Configurable, in `.rails-flow/decision-rights.json`, because the EPIC names it a first-class
deliverable rather than an implicit heuristic. With no file, the shipped default applies:

| decide alone | must escalate |
|---|---|
| which backlog item is next | product scope / user-journey change |
| implementation approach inside a frozen plan | anything irreversible or destructive |
| **aesthetic and interface craft** | the `dev → main` release |
| filing bugs and upstream reports | spend or budget increases |
| feature → `dev` on green gates | a requirement the brief does not settle |
| | a gate unsatisfiable without weakening it |

The test that makes this checkable rather than a vibe: **does it publish, or can it not be undone?**
That is readable from the action itself, unlike *"is this important"*.

Two rules keep the policy from rotting permissive:

- **An unclassified action escalates.** Defaulting it to *decide* would let the policy grow
  permissive by omission — every action nobody thought about becomes autonomous.
- **A policy with no `escalate` list is refused.** That is full autonomy wearing a config file.

## Bounded creative authority

**Craft is yours. Scope is not.** The line is not how large the change is, it is whether it changes
what the product *does*.

- **Yours, no ratification:** look and feel, art direction, interaction polish, spacing, motion,
  copy tone, which of two equally-conformant layouts to use. Restyle a page, rework a component's
  states, change an illustration's treatment — the design system and its gates already bound this,
  which is exactly why it can be autonomous.
- **Escalate:** anything that alters what the product does — a new user journey, a step added to or
  removed from a flow, a capability appearing or disappearing. These pass **IA-before-code** first:
  the sitemap and journeys change *before* any code, and the scope decision goes to the human via
  `/rails-flow:escalate` (pillar 3), which parks the thread and lets other work continue.

A redesign that leaves every journey intact is craft. The same redesign that quietly drops a step is
scope wearing a visual diff — and it is the case worth being slow about, because it looks like the
first one in review.

**Record every creative-direction and scope call as a brain decision** (ADR-lite: what, why, what was
rejected). Autonomy without an audit trail is not autonomy, it is an unexplained diff — and the next
agent to touch that surface needs to know whether the current look was chosen or inherited.

## Composing a tick

```bash
# 1. the toolchain is current (pillar 1) — a stale toolchain invalidates everything after it
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/toolchain_version.py"

# 2. what is next, and may I (this command)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/next_action.py" --state state.json

# 3. if it says escalate — ask, park, and move on (pillar 3)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/escalation.py" --ask "<the question>" --issue <n>
```

## Verifying a change to this path

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/next_action.py" --selftest
```

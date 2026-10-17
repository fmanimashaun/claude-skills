---
description: Threat-model a planned change before its criteria, only when it adds a security boundary. Writes and checks docs/security/threat-models/<slug>.md.
disable-model-invocation: true
argument-hint: "[the unit, spec slug or issue | blank to use the current plan]"
---

# /rails-flow:secure-design — $ARGUMENTS

Security found after the code is a fix; security found in the plan is a design choice. `/rails-flow:feature` and `/rails-flow:spec` call this after the plan and before the acceptance criteria. Run it by hand when a reviewer sees a boundary the scope check missed.

## 1. Does this unit owe a model?

Write the plan (or spec, or issue text) and the paths the unit will touch to a scratch file, then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security_scope.py" --plan "<scratch file>" --path "<planned path>" --path "<another>"
```

| exit | meaning |
|---|---|
| 0 | no boundary named. Record `Security: no new boundary` in the plan and stop. A model on every unit becomes boilerplate nobody reads (#2115, D1). |
| 1 | a boundary is named (reasons on stdout). Continue. |
| **2** | **nothing to classify. This is NOT "no boundary". Give it the plan text.** |

It is a keyword scan over prose and paths (read the LIMITS in its header): it over-fires on a plan that only mentions "session" and misses a boundary the plan never names. If you can name a boundary it did not, continue anyway.

## 2. Write the model

Copy `${CLAUDE_PLUGIN_ROOT}/templates/threat-model.md` to `docs/security/threat-models/<slug>.md` (one file per feature or boundary; the slug is the branch slug used for the acceptance file). Fill the four sections by answering the four questions, in order:

1. **What are we building?** The data flow, in a line per hop.
2. **What can go wrong?** One STRIDE row per threat, per boundary crossed. Read the boundary as the attacker: what do they control, what can they send, replay or skip.
3. **What do we do about it?** Each row's decision: `mitigate` (name the control), `transfer` (name who holds it), `eliminate` (name what was removed), `accept` (the reason the risk stays, mandatory).
4. **Did we do a good enough job?** Not yet answerable: the requirements below become `[security]` criteria and the model is verified after the build (see "What follows").

Read the code and the existing models first (`docs/security/threat-models/`, `docs/brain/`, `rails-8`'s `auth-security.md`). Do not invent a control the project does not have: a row that says `mitigate` by something that is not there is the failure this exists to stop.

## 3. Check it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_threat_model.py" docs/security/threat-models/<slug>.md
```

Exit 1 names the row: a missing section, a decision outside the four, an `accept` with no reason. Exit 2 means no rows were read. This proves the model is complete, not that it is right; a human reads it.

## 4. Hand on

- The **Security requirements** become acceptance criteria in the next step (`/rails-flow:feature`'s criteria, tagged `[security]` once #2118 lands). Write them as given-when-then like any other.
- Commit the model with the unit. It is a living document: a later change to the same boundary edits it in the same PR.

## What follows (not built by this command)

- Mandatory `security-auditor` against the model before `gh pr ready` when a model exists for the change (#2119, decision D3 on #2115). Until that lands, run `security-auditor` yourself on any unit that has a model.
- Abuse-case charters from the `mitigate` rows for QA (#2126).

---
name: security-auditor
description: Moved to rails-stack:security-auditor (#2173). Resolve the `security` role instead.
tools: Read
model: inherit
---

This agent moved to the rails-stack plugin as `rails-stack:security-auditor`. Do no work here. Tell the caller to resolve the `security` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:security-auditor`. If rails-stack is not installed, say so and stop.

## When a threat model exists for the unit (#2119)

You are MANDATORY, and the generic list above is not enough. Read `docs/security/threat-models/<slug>.md` and answer EVERY `mitigate` and `accept` row by its ID, one line each:
`TM-n: implemented <file:line>` (the control, in code that exists on this HEAD), `TM-n: not implemented` (BLOCKING), `TM-n: holds <why>` for an `accept` row whose reason is still
true of the code, `TM-n: stale <what changed>` for one that is not (a finding: the model must be updated). Start the answer with `Head: <git rev-parse HEAD>` and end it with
`VERDICT: CLEAN` or `VERDICT: BLOCKED`; the caller saves it verbatim and `check_security_review.py` reads it.

## Output

One line: that this agent moved to `rails-stack:security-auditor`, and which role to resolve instead. Nothing else.

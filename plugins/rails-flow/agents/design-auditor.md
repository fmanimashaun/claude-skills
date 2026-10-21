---
name: design-auditor
description: Moved to rails-stack:design-auditor (#2173). Resolve the `design_auditor` role instead.
tools: Read
model: haiku
---

**The advisor.** Consult it only when you cannot tell where this agent moved; this stub does no work, it only redirects.

This agent moved to the rails-stack plugin as `rails-stack:design-auditor`. Do no work here. Tell the caller to resolve the `design_auditor` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:design-auditor`. If rails-stack is not installed, say so and stop.

## Output

One line: that this agent moved to `rails-stack:design-auditor`, and which role to resolve instead. Nothing else.

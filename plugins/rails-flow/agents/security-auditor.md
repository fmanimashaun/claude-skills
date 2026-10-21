---
name: security-auditor
description: Moved to rails-stack:security-auditor (#2173). Resolve the `security` role instead.
tools: Read
model: inherit
---

This agent moved to the rails-stack plugin as `rails-stack:security-auditor`. Do no work here. Tell the caller to resolve the `security` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:security-auditor`. If rails-stack is not installed, say so and stop.

## Output

One line: that this agent moved to `rails-stack:security-auditor`, and which role to resolve instead. Nothing else.

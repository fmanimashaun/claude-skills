---
name: code-reviewer
description: Moved to rails-stack:code-reviewer (#2173). Resolve the `reviewer` role instead.
tools: Read
model: inherit
---

This agent moved to the rails-stack plugin as `rails-stack:code-reviewer`. Do no work here. Tell the caller to resolve the `reviewer` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:code-reviewer`. If rails-stack is not installed, say so and stop.

## Output

One line: that this agent moved to `rails-stack:code-reviewer`, and which role to resolve instead. Nothing else.

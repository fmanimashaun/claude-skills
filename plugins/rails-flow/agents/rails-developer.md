---
name: rails-developer
description: MOVED to rails-stack as `rails-stack:rails-developer` (#2173). Do not delegate here; resolve the stack's `developer` role instead (rails-flow reference/stack-roles.md). Kept for two releases so a project that updated rails-flow first is told, not broken.
tools: Read
model: inherit
---

This agent moved to the rails-stack plugin as `rails-stack:rails-developer`. Do no work here. Tell the caller to resolve the `developer` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:rails-developer`. If rails-stack is not installed, say so and stop.

## Output

One line: that this agent moved to `rails-stack:rails-developer`, and which role to resolve instead. Nothing else.

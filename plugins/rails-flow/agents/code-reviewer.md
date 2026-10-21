---
name: code-reviewer
description: MOVED to rails-stack as `rails-stack:code-reviewer` (#2173). Do not delegate here; resolve the stack's `reviewer` role instead (rails-flow reference/stack-roles.md). Kept for two releases so a project that updated rails-flow first is told, not broken.
tools: Read
---

This agent moved to the rails-stack plugin as `rails-stack:code-reviewer`. Do no work here. Tell the caller to resolve the `reviewer` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:code-reviewer`. If rails-stack is not installed, say so and stop.

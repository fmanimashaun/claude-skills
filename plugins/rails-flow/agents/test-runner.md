---
name: test-runner
description: Moved to rails-stack:test-runner (#2173). Resolve the `test_runner` role instead.
tools: Read
model: haiku
---

**The advisor.** Consult it only when you cannot tell where this agent moved; this stub does no work, it only redirects.

This agent moved to the rails-stack plugin as `rails-stack:test-runner`. Do no work here. Tell the caller to resolve the `test_runner` role with `detect_stack.py --descriptor` (reference/stack-roles.md) and delegate to the agent it names; for a Rails project with rails-stack installed that is `rails-stack:test-runner`. If rails-stack is not installed, say so and stop.

## Output

One line: that this agent moved to `rails-stack:test-runner`, and which role to resolve instead. Nothing else.

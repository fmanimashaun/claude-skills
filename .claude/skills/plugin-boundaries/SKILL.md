---
name: plugin-boundaries
description: Where content belongs across this marketplace's plugins and skills — one stack-neutral core with stack-specific plugins layered on top, exactly one home per concern, and nothing maintainer-only shipped to clients. Use when proposing a new plugin or skill, asking whether something can be adapted to another stack (React/Next.js, Go, Rust), splitting or forking an existing plugin, or deciding which plugin a piece of content belongs in.
---

# Plugin boundaries

Each rule below comes from a proposal that was rejected for breaking it. Apply them
when shaping the proposal, not after.

## 1. One stack-neutral core, stack-specific plugins layered on top

- **Never fork a per-framework variant of the same plugin.** "A `design-system` for Rails
  and another for Next.js/React" is the wrong shape. The right shape is one stack-neutral
  `design-system`, with the stack-specific parts living in the stack plugins that already
  exist (`rails-stack`, `hotwire`).
- Why forking is wrong here specifically: **the portable half is the half that churns.**
  `components.md`, `coverage.md`, and `page-anatomies.md` are stack-neutral and among the
  most-edited files in the repo. Two copies means every one of those edits lands twice,
  forever, with nothing checking that they agree.
- Design the neutral core so that **adding a stack is a new plugin, not an edit to existing
  ones** — a Go + templ or Rust + Askama stack should be additive. Keep shared reference
  files (e.g. `skills/design-system/references/coverage.md`) free of per-stack columns;
  per-stack columns are what force a new stack to touch existing gates.
- Follow the registration pattern that already works: `plugins/rails-flow/scripts/project_gates.py`
  discovers `checks.json` from sibling plugin directories, so a new stack ships a manifest
  rather than forking the runner.
- **Design for the next stack; don't build its machinery yet.** A stack descriptor with one
  consumer is indirection, not a proven seam. Do the correctness work now (move misfiled
  content to its owner) and leave multi-stack machinery until a real second stack forces it.

## 2. Every concern gets exactly one home

- Before proposing where content goes, **name the plugin or skill that already owns that
  stack or concern**, and put it there. `rails-stack` owns Rails; `hotwire` owns
  Turbo/Stimulus and is backend-agnostic by its own description.
- Do **not** add or keep stack-specific content in a plugin when another plugin already owns
  that stack. Content in the wrong place is usually not missing a home — it is misfiled.
- When content is misfiled, **move it to its existing owner**. Do not duplicate it, and do
  not leave a copy behind for convenience.
- State the ownership split explicitly in the proposal. Cross-plugin pairing is prose-only
  today — no `plugin.json` carries a `requires`/`dependencies` field — so a split whose two
  halves only work together, with nothing able to say so, is not yet a working design.

## 3. Client plugins ship only what clients need

- Resources that shipped plugins do not need **must not be duplicated across repos**.
- Maintainer-only resources (the UI kit, design corpora) belong in the maintainer repo and
  are fetched into the local copy by the onboarding script for agents to reference. They are
  not vendored into a plugin that ships to clients.
- If a separate private repo exists only to hold something clients never receive, that repo
  is redundant — fold it into the public repo and delete it rather than maintaining two.

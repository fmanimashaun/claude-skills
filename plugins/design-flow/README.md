# design-flow

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills    # the fidara-design skill (doctrine) rides here
/plugin install design-flow@claude-skills     # the commands + agents
```

The **UI/design** side of the toolchain. It makes UI consistent, modern, and responsive
across projects **without a designer or Figma**, by applying the **fidara-design** system
(the doctrine, bundled in the `rails-stack` skill) through agentic commands.

## Commands

- `/design-flow:setup [brand]` — scaffold the design system into a Rails 8 + Hotwire + Tailwind v4
  project: the `@theme` token architecture (brand primitives → semantic roles → Utopia fluid
  scale + measure/radius/shadow/motion), the layout-primitive `@utility` recipes, base
  ViewComponents, and dark-mode wiring. Idempotent. `brand` = `fidara | fmworkflows`.
- `/design-flow:component <name>` — author (or refactor) a UI component per the system: compose
  layout primitives + semantic role tokens, apply the `variant × size × state` vocabulary, add
  the a11y checklist and the prescribed responsive behavior.
- `/design-flow:audit [path]` — flag UI drift against the system: raw/brand colors in component
  code, brittle selectors, breakpoint misuse where an intrinsic primitive fits, missing focus
  ring / ARIA, non-`min-h-touch` targets, hand-rolled layout CSS.

## Agents

- **ui-composer** — builds views/components by composing primitives + tokens to the doctrine.
- **design-auditor** — the consistency gate (design-system-specific; complements rails-flow's).
- **brand-guardian** — enforces token/brand/logo/icon usage and the two-brand model.

## The doctrine

Everything follows the **fidara-design** skill (`skills/fidara-design/`): foundations/tokens,
layout primitives, component catalog, forms, Stimulus interaction, responsive doctrine, brand.
Read it first — this plugin is the *applier*, that skill is the *law*.

## Platform note

Commands/agents are model-driven (no bundled hooks). Works wherever Claude Code runs.

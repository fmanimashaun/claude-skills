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
  ViewComponents, and dark-mode wiring. Idempotent. `brand` = `<pack>` or `<pack>:<variant>` (e.g. `fidara:fmworkflows`).
- `/design-flow:component <name>` — author (or refactor) a UI component per the system: compose
  layout primitives + semantic role tokens, apply the `variant × size × state` vocabulary, add
  the a11y checklist and the prescribed responsive behavior.
- `/design-flow:audit [path]` — flag UI drift against the system: raw/brand colors in component
  code, brittle selectors, breakpoint misuse where an intrinsic primitive fits, missing focus
  ring / ARIA, non-`min-h-touch` targets, hand-rolled layout CSS.
- `/design-flow:mobile [ios|android|both]` — scaffold **Hotwire Native parity** (Phase 2):
  native-app detection + `body.mobile-app`, JSON path configuration, bridge components
  (button/menu/tab-bar, progressive-enhancement), safe-area + `min-h-touch` wiring, and
  table→card-stack. Reuses the web components; the native Kotlin/Swift shells stay in their own
  repos.
- `/design-flow:tokens [android|ios|both]` — **native token export** (Phase 3): generate
  Android (`colors.xml` + `Theme.Fidara`) and iOS (SwiftUI `Color`) tokens from the `@theme`
  so fully-native screens match by construction. Writes to `tmp/` for you to carry into the
  native repos; never modifies them.

## Agents

- **ui-composer** — builds views/components by composing primitives + tokens to the doctrine.
- **design-auditor** — the consistency gate (design-system-specific; complements rails-flow's).
- **brand-guardian** — enforces token/brand/logo/icon usage and the two-brand model.

## Checks

- **`llm_tell_detector.py`** — seven named rules for LLM design tells, each citing the doctrine
  line it enforces (`--list-rules`). Stdlib only, no browser. Runs on **every edit** via a
  PostToolUse hook and inside `/design-flow:audit`. Two rules find outright bugs rather than style:
  `bg-gradient-to-*` (removed in Tailwind v4) and `duration-fast` (never existed) both emit **no
  CSS at all**, so the markup looks right and renders wrong with nothing raised.
  Disable one **with a reason** — `<!-- design-flow-disable <rule>: why -->`; a bare disable is
  itself a finding.
- **`setup_doctrine_crosscheck.py`** — catches doctrine that reads a config key `/design-flow:setup`
  never generates. A toolchain check, not a project one.
- **`brand_pack_lint.py`** — validates a brand pack's completeness.
- **`rendered_conformance.py`** — the browser half: what the cascade actually computed. Needs
  Playwright and a booted app, so it runs on demand rather than per edit.

The hook is **advisory and fails open**: with `python3` absent it goes quiet rather than blocking
an edit, per the guarantee-vs-advice test in `docs/harness-doctrine.md`.

## The doctrine

Everything follows the **fidara-design** skill (`skills/fidara-design/`): foundations/tokens,
layout primitives, component catalog, forms, Stimulus interaction, responsive doctrine, brand.
Read it first — this plugin is the *applier*, that skill is the *law*.

## Platform note

Commands/agents are model-driven (no bundled hooks). Works wherever Claude Code runs.

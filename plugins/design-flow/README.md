# design-flow

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills    # the design-system skill (doctrine) rides here
/plugin install design-flow@claude-skills     # the commands + agents
```

The **UI/design** side of the toolchain. It makes UI consistent, modern, and responsive
across projects **without a designer or Figma**, by applying the **design-system** skill
(the doctrine, bundled in `rails-stack`) through agentic commands.

## Commands

- `/design-flow:setup [brand]` — scaffold the design system into a Rails 8 + Hotwire + Tailwind v4
  project: the `@theme` token architecture (brand primitives → semantic roles → Utopia fluid
  scale + measure/radius/shadow/motion), the layout-primitive `@utility` recipes, base
  ViewComponents, and dark-mode wiring. Idempotent. `brand` = `<pack>` or `<pack>:<variant>` (e.g. `fidara:fmworkflows`).
- `/design-flow:component <name>` — author (or refactor) a UI component per the system: compose
  layout primitives + semantic role tokens, apply the `variant × size × state` vocabulary, add
  the a11y checklist and the prescribed responsive behavior.
- `/design-flow:variants <brief> [--variants N]` — **N brand-conformant compositions of one
  brief** (default 3) plus a dev-only switcher route to compare them live in the real app. For
  briefs with many defensible answers (a hero, a pricing page, a landing section), where one
  output invites a yes/no — which tends to become yes. Variants differ in **composition only**:
  same tokens, same components, same API, asserted by `variant_conformance.py` rather than by
  inspection. It is not a style menu, and picking one deletes the rest and the switcher.
  Reachable as `--variants N` on `/design-flow:component`.
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
- `/design-flow:critique [path]` — the design *lens* where `audit` is the gate: is this surface
  considered, or mechanically assembled? Advisory by design; see `references/art-direction.md`.
- `/design-flow:canvas <brief>` — draft a design as a Claude Design canvas from the system's tokens
  and catalog, for visual refinement before porting.
- `/design-flow:port <artboard>` — port a Claude Design artboard to ERB, ViewComponents,
  simple_form, Turbo and Stimulus per `references/design-handoff.md`.
- `/design-flow:compose <brief>` — compose a surface from the catalog with the research layer
  first (`reference-research.md`): three sources, mechanisms extracted, expressed in the pack's tokens.
- `/design-flow:assets` and `/design-flow:generate` — the visual-asset pipeline: set up, plan,
  cost, generate and reconcile the images a surface needs, under the tier hierarchy in
  `references/visual-assets.md`.

## Agents

- **ui-composer** — builds views/components by composing primitives + tokens to the doctrine.
- **design-auditor** — the consistency gate (design-system-specific; complements rails-flow's).
- **brand-guardian** — enforces token/brand/logo/icon usage and the brand-pack model.
- **design-critic** — the advisory lens behind `/design-flow:critique`; never blocks.
- **design-porter** — ports a Claude Design artboard to the Rails stack behind `/design-flow:port`.

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
- **`variant_conformance.py`** — ten named rules over a variant set (`--list-rules`). It **runs**
  the LLM-tell detector per variant rather than reimplementing it, and adds what a context-free
  scan cannot have: a variant bringing its own CSS or custom properties, a variant naming a
  **pack-private primitive** instead of a role token (that one needs the pack, so it needs a
  parameter the detector is never given), two variants with an identical composition signature,
  a missing rationale, and a switcher route reachable outside development. `--verify-discard`
  proves the scaffolding is gone once a variant is chosen, because an un-run discard step looks
  exactly like a completed one.
- **`rendered_conformance.py`** — the browser half: what the cascade actually computed. Needs
  Playwright and a booted app, so it runs on demand rather than per edit.

The hook is **advisory and fails open**: with `python3` absent it goes quiet rather than blocking
an edit, per the guarantee-vs-advice test in `docs/doctrine/harness-doctrine.md`.

## The doctrine

Everything follows the **design-system** skill (`skills/design-system/`): foundations/tokens,
layout primitives, component catalog, forms, Stimulus interaction, responsive doctrine, brand.
Read it first — this plugin is the *applier*, that skill is the *law*.

## Platform note

One bundled hook: a PostToolUse `design-tells.sh` that runs `llm_tell_detector.py` on every edit
(advisory — it fails open without `python3`). Everything else is model-driven. Works wherever Claude
Code runs.

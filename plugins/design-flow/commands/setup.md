---
description: Scaffold the Fidara design system into a Rails 8 + Hotwire + Tailwind v4 project — @theme token architecture (brand primitives -> semantic roles -> Utopia fluid scale), layout-primitive @utility recipes, base ViewComponents, dark mode. Idempotent; brand-parameterized.
argument-hint: "[brand: fidara | fmworkflows]"
---

# /design-flow:setup — $ARGUMENTS

Install the **fidara-design** system into this project. Follow the skill doctrine
(`skills/fidara-design/SKILL.md` + references) exactly — this command applies it.

## Preconditions

Rails 8 + Hotwire (importmap) + **Tailwind v4** (`tailwindcss-rails`, CSS-first `@theme`, no
`tailwind.config.js`/npm). Confirm `app/assets/tailwind/application.css` exists. `$ARGUMENTS`
picks the brand (`fidara` | `fmworkflows`; default `fmworkflows`) — affects only the lockup +
"by Fidara" endorsement, not tokens (both use the `fm-*` prefix).

## Idempotency

Own only what you scaffold; re-runnable. Wrap generated `@theme`/token blocks and `@utility`
recipes between markers; on re-run refresh inside the markers only, leaving hand edits intact.
Never overwrite an existing customized component without showing a diff. Stage only files you
authored; `git status` after.

## Scaffold (per foundations-tokens.md)

1. **`application.css`** — the full `@theme`: brand primitives (`fm-*` palette + 3 fonts),
   semantic roles via `@theme inline` with `:root`/`.dark`, the Utopia fluid `--text-step-*` /
   `--space-*` (`clamp()`) scale, `--measure/--radius/--shadow-*/--ease-out/--duration`,
   `@variant dark`, `@plugin @tailwindcss/forms` + `typography`, and the `min-h-touch`/safe-area
   utilities. Add the pre-paint dark-mode `<script>` to the layout.
2. **Layout `@utility` recipes** (layout-primitives.md): `stack`, `cluster`, `center`, `box`,
   `grid-auto`, `frame`, `cover`, `reel`, `with-icon`.
3. **Base ViewComponents** (`app/components/`): `Layout::Sidebar`, `Layout::Switcher`,
   `Layout::Container`, and `Ui::Button`, `Ui::Card`, `Ui::Badge`, `Ui::Alert`, `Ui::Modal`,
   `Ui::Avatar`, `Ui::EmptyState` — each with the variant/size/state map + slots from
   components.md. (If the project doesn't use ViewComponent yet, add the gem, or fall back to
   the helper-DSL variant — ask which.)
4. **Stimulus mixins + controllers** (interaction-stimulus.md): the four mixins (list-navigation,
   focus-trap+restore, dismissable-layer, anchored-position) and the `modal`/`dropdown`/`tabs`/
   `sidebar`/`theme`/`toast` controllers built on them.
5. **Fonts**: wire Bricolage Grotesque / Newsreader / Overpass Mono.
6. **Lucide** icon helper (`with-icon`, `1em`, `currentColor`).

## Report

Files created, brand selected, ViewComponent decision, and the entry points:
`/design-flow:component` to author UI, `/design-flow:audit` to check drift. Remind that a new
`@theme` needs a Tailwind rebuild.

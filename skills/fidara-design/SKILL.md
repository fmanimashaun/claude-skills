---
name: fidara-design
description: >
  The Fidara design system — how to build consistent, modern, responsive UI in Rails 8 +
  Hotwire + Tailwind CSS v4 (Fidara / fmworkflows brands). Load this WHENEVER building or
  reviewing UI: components (buttons, cards, forms, nav, modals, tables, badges, alerts),
  page layouts, tokens/theming, dark mode, responsiveness, or brand/logo usage. It defines
  the token architecture (brand primitives → semantic roles → fluid scale), the layout
  primitives you compose instead of ad-hoc flex/grid, the component catalog with
  variant/size/state, the Stimulus interaction patterns, and the responsive doctrine.
  Consistency is enforced here, not left to taste.
---

# Fidara Design System

Build every UI by **composing tokens, layout primitives, and catalog components** — never
ad-hoc CSS. This system makes UI consistent across projects without a designer or Figma.
It is **prescriptive**: where it gives a token, a recipe, or a variant set, use exactly
that. Inconsistency in components degrades the whole product, so drift is a defect.

**Stack:** Rails 8 · Hotwire (Turbo + Stimulus) · **Tailwind CSS v4** (CSS-first `@theme`,
no `tailwind.config.js`, no npm) · Lucide icons. Two brands (**fidara**, **fmworkflows**)
are ONE system — identical values, only the token prefix differs; code uses the **`fm-*`**
prefix. See [references/brand.md](references/brand.md).

## The five layers (read in order)

1. **Foundations / tokens** — [references/foundations-tokens.md](references/foundations-tokens.md).
   One `@theme` block: **brand primitives** (`fm-*` palette, fonts) → **semantic roles**
   (`--primary`, `--background`, `--foreground`, `--muted`, `--border`, `--ring`, … each with
   a `-foreground` pair) → **fluid scale** (Utopia `clamp()` type + space) + measure, radius,
   shadow, motion. **Components consume ONLY semantic roles**, never raw `fm-*` or stock
   `blue-700`/`gray-*`. Dark mode = re-point roles under `.dark`.
2. **Layout** — [references/layout-primitives.md](references/layout-primitives.md). Compose
   the primitives (Stack, Cluster, Center, Box, Grid, Sidebar, Switcher, Cover, Frame, Reel,
   Imposter, Icon, Container). Layout responds to space **intrinsically** — flex-wrap /
   `flex-basis` thresholds, grid `auto-fit/minmax`, `clamp()` — so **breakpoints are reserved
   for true structural swaps only** (nav→hamburger). Never write per-page layout CSS.
3. **Components** — [references/components.md](references/components.md) +
   [references/forms.md](references/forms.md). ~16 catalog components, each a composition of
   layout primitives + role tokens, with a fixed **variant × size × state** vocabulary, an
   a11y checklist, and a prescribed responsive behavior.
4. **Interaction** — [references/interaction-stimulus.md](references/interaction-stimulus.md).
   Behavior is Hotwire, not a JS framework: four reusable Stimulus mixins (list-navigation,
   focus-trap+restore, dismissable-layer, anchored-position) cover every overlay; style off
   `data-[state=…]` / `aria-*`.
5. **Responsive** — [references/responsive.md](references/responsive.md). Fluid-first
   (Utopia) + intrinsic primitives; explicit breakpoints only where layout structure must
   change; touch targets (`min-h-touch` 44px) and safe-areas wired in.

## Authoring mechanism (what to reach for)

- **Stateless layout primitives** (Stack/Cluster/Center/Grid/Box/Frame/Icon/Cover/Reel) →
  Tailwind **`@utility` recipes** you apply in ERB (`class="stack"`), tuned by `--custom`
  properties.
- **Parameterized / behavioral primitives + catalog components** (Sidebar/Switcher/Imposter/
  Container, Button/Card/Modal/Badge/Alert/…) → **ViewComponents** (`app/components/…`)
  exposing `variant/size/state` args + slots, emitting role-token classes.
- **CRUD compositions** (tables, headers, row-actions, empty-states, pagination) → keep the
  proven `app/views/shared/_*.html.erb` partial set, refactored to consume components/tokens.

## Non-negotiables (the drift-killers)

- Components use **semantic role tokens** only (`bg-primary text-primary-foreground`,
  `border-border`, `focus-visible:ring-ring`). No raw brand or stock colors in component code.
- **Every surface token ships its `-foreground`** — never hand-pick text color on a colored
  surface.
- **Compose primitives; don't write bespoke layout CSS.** Spacing lives on the parent
  (Stack/Cluster/Grid `gap`), never as child margins.
- **Intrinsic responsiveness first**; a `@media`/`@container` breakpoint must justify itself.
- **Every interactive element**: visible `focus-visible` ring, keyboard-operable, correct
  ARIA (`aria-expanded/controls/selected`, roles), `sr-only` labels for icon-only controls.
- **One radius language**: buttons/inputs `rounded-md`, cards `rounded-lg`, badges/avatars
  `rounded-full`. **Lucide** icons, `1em`-sized, `currentColor`.
- Motion: 150–200ms `ease-out`, transition `colors/opacity/transform` (never `all`), gated on
  `prefers-reduced-motion`.

## When you build

Setup a project with `/design-flow:setup`; author a component with `/design-flow:component`; check
drift with `/design-flow:audit` (design-flow plugin). Always: pick the semantic role, compose
primitives, apply the catalog variant, add the a11y + responsive behavior — in that order.

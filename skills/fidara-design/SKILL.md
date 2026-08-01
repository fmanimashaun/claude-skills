---
name: fidara-design
description: >
  The Fidara design system — how to build consistent, modern, responsive UI in Rails 8 +
  Hotwire + Tailwind CSS v4, brand-parameterised via brand packs. Load this WHENEVER building or
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
no `tailwind.config.js`, no npm) · Lucide icons. Brand packs (**fidara** is the first; `fmworkflows` is a *variant* inside it, not a second pack)
are ONE system — identical values, only the token prefix differs; code uses the **`fm-*`**
prefix. See [references/brand.md](references/brand.md).

> **Tailwind here is a deliberate choice, not a claim that hand-written CSS is inferior.**
> Canonical Rails apps — including 37signals' own ([campfire](https://github.com/basecamp/once-campfire),
> writebook, fizzy) — hand-write vanilla CSS, and do it well. We standardize on Tailwind v4
> because this system's guarantee is **mechanically enforceable consistency**: `@theme` role
> tokens, `@utility` primitives, and utility class names are greppable, so `/design-flow:audit`
> and the `design-auditor` can *verify* conformance and catch drift. That check doesn't exist
> for bespoke stylesheets. If a project has an established vanilla-CSS system, record it as a
> Project Override rather than converting it on this skill's authority.

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
3. **Page anatomies** — [references/page-anatomies.md](references/page-anatomies.md). The
   screen level, above components: **3 shell archetypes** (sidebar + mobile drawer, stacked,
   multi-column) and **3 page anatomies** (home/dashboard, detail, settings), each stating its
   mobile behavior, scroll containment and which catalog components fill each region. A screen
   is **composed, not designed** — pick a shell, pick an anatomy, fill from the catalog. Also
   carries the primitive-instead-of-breakpoint substitution table.
4. **Components** — [references/components.md](references/components.md) +
   [references/forms.md](references/forms.md). The catalog — each entry a composition of layout
   primitives + role tokens, with a fixed **variant × size × state** vocabulary, an a11y
   checklist, and a prescribed responsive behavior. **What exists is counted in
   [references/coverage.md](references/coverage.md)**, which a script regenerates; a number
   repeated here would be a second copy with no arbiter, and the one that was here ("~16") had
   drifted to under half the real figure.
5. **Interaction** — [references/interaction-stimulus.md](references/interaction-stimulus.md).
   Behavior is Hotwire, not a JS framework: four reusable Stimulus mixins (list-navigation,
   focus-trap+restore, dismissable-layer, anchored-position) cover every overlay; style off
   `data-[state=…]` / `aria-*`. **Motion** is [references/motion.md](references/motion.md):
   two curves, three distance-chosen durations, departures shorter than arrivals, and the
   **eight ways a gesture can be abandoned** — a component that can be mid-gesture registers a
   window `blur` listener, or it stays stuck in its pressed state when the user alt-tabs.
6. **Responsive** — [references/responsive.md](references/responsive.md). Fluid-first
   (Utopia) + intrinsic primitives; explicit breakpoints only where layout structure must
   change; touch targets (`min-h-touch` 44px) and safe-areas wired in.
7. **Mobile** — [references/mobile.md](references/mobile.md). One system across web + mobile:
   Hotwire Native renders the same web UI in a native shell; safe-areas + `min-h-touch` +
   bridge components + path config; native token export for fully-native Android/iOS screens.

**Concrete code:**
[references/reference-implementation.md](references/reference-implementation.md) is the
canonical ViewComponent pattern (Button/Card) + the four Stimulus mixins;
[references/component-implementations.md](references/component-implementations.md) is the
**full catalog** worked out (Badge, Alert, form controls, Modal, Dropdown, Tabs, Toast,
Tooltip, Avatar, EmptyState, Sidebar, Switcher).
[references/mobile-reference-implementation.md](references/mobile-reference-implementation.md)
is the Phase-2 Hotwire Native web-side code (native detection, path config, bridge components,
safe-area/touch, table→card-stack).
[references/native-tokens.md](references/native-tokens.md) is the Phase-3 native token export
(role→Material3/iOS mapping + a reference script emitting Android `colors.xml`/`Theme.Fidara`
and iOS SwiftUI `Color` from the `@theme`).
[references/crud-modal-pattern.md](references/crud-modal-pattern.md) is the **modal-driven,
in-page CRUD flow** (persistent `turbo-frame` modal + Turbo Stream list updates + confirmation
modal + `modal_controller`) — the Fidara way to do create/edit/delete.
[references/data-viz.md](references/data-viz.md) is the **data-visualization layer** (charts,
KPIs, dashboards): the validated `--color-chart-*` palette derived from the `fm-*` tokens, the
form→color→validate procedure, KPI-tile + chart recipes, and the chart a11y rules. Copy these
shapes exactly; don't invent new ones.
[references/visual-assets.md](references/visual-assets.md) is the **visual-asset layer** — what
actually fills the large visual area of a hero, a feature band, a split sign-in or a 404: the tier
hierarchy (product screenshot → data-viz → brand-geometric decoration → illustration, last), the
CSS recipes deriving decoration from the brand's own geometry, the deterministic screenshot capture
recipe, and the per-surface prescriptions for the pages with nothing to screenshot.
[references/marketing-copy.md](references/marketing-copy.md) is the **copy layer** for marketing
surfaces — what each section *says*, not how it is laid out: a per-section contract (the job the
copy does, its shape, its failure mode), the length caps derived from the shipped measures, and the
placeholder checks. Read it whenever you build a marketing surface; layout without copy doctrine
produces a well-composed page with lorem-grade words.
[references/coverage.md](references/coverage.md) is the **component coverage matrix** — one row per
component naming its guidance state (`documented` / `derivable` / `needs doctrine #N`), what to
**build it from**, and **where/when to use it**. Read it *before* building any component that has no
dedicated entry above: it tells you whether doctrine already defines the anatomy, which documented
parts to compose from, and which surface the thing belongs on. Generated by
`scripts/build_coverage.py` — never hand-edit it.

## Authoring mechanism (what to reach for)

- **Stateless layout primitives** (Stack/Cluster/Center/Grid/Box/Frame/Icon/Cover/Reel) →
  Tailwind **`@utility` recipes** you apply in ERB (`class="stack"`), tuned by `--custom`
  properties.
- **Parameterized / behavioral primitives + catalog components** (Sidebar/Switcher/Imposter/
  Container, Button/Card/Modal/Badge/Alert/…) → **ViewComponents** (`app/components/…`)
  exposing `variant/size/state` args + slots, emitting role-token classes.
- **CRUD compositions** (tables, headers, row-actions, empty-states, pagination) → keep the
  proven `app/views/shared/_*.html.erb` partial set, refactored to consume components/tokens.
  **CRUD itself is modal-driven and in-page** — create/edit/delete open in the shared
  `<turbo-frame id="modal">`, success updates the list via Turbo Stream; never a full-page
  new/edit form. See [references/crud-modal-pattern.md](references/crud-modal-pattern.md).
  **Modal + Card are the backbone.**

## Non-negotiables (the drift-killers)

- Components use **semantic role tokens** only (`bg-primary text-primary-foreground`,
  `border-border`, `focus-visible:ring-ring`). No raw brand or stock colors in component code.
- **Every surface token ships its `-foreground`** — never hand-pick text color on a colored
  surface.
- **Compose primitives; don't write bespoke layout CSS.** Spacing lives on the parent
  (Stack/Cluster/Grid `gap`), never as child margins.
- **CRUD is modal-driven and in-page** — create/edit/delete open in the shared `turbo-frame`
  modal and update the list via Turbo Stream; a full-page new/edit form is a defect.
- **Custom utilities use Tailwind v4 `@utility`**, never raw classes in `@layer utilities`
  (which get no variants in v4).
- **Intrinsic responsiveness first**; a `@media`/`@container` breakpoint must justify itself.
- **Every interactive element**: visible `focus-visible` ring, keyboard-operable, correct
  ARIA (`aria-expanded/controls/selected`, roles), `sr-only` labels for icon-only controls.
- **One radius language**: buttons/inputs `rounded-md`, cards `rounded-lg`, badges/avatars
  `rounded-full`. **Lucide** icons, `1em`-sized, `currentColor`.
- **Motion**: two curves — `--ease-out` arriving, `--ease-in` leaving — and three durations picked by
  **travel distance** (`--duration-fast` 120ms under 20px · `--duration` 180ms · `--duration-slow`
  280ms over 200px). **A departure is always shorter than an arrival.** Transition named properties,
  never `all`. Under `prefers-reduced-motion` the information still arrives and only the trip is
  skipped — never remove the element or the state change. Full doctrine, including the eight ways a
  gesture can be abandoned, in [references/motion.md](references/motion.md).
- **Visual assets**: prefer the **most specific** option, not the prettiest — a real product
  screenshot beats decoration, decoration beats illustration, and illustration is last because it is
  the hardest class to keep consistent. Decoration is **derived from the brand's own geometry** in
  CSS (`--decor-*`, role fallbacks), never `fm-*` primitives; it is `aria-hidden`, carries
  `pointer-events: none`, contains nothing focusable, and is **never load-bearing for meaning**.
  Never mix two illustration styles on one site. Full doctrine in
  [visual-assets.md](references/visual-assets.md).
- **Marketing copy**: the human owns positioning; the agent drafts against a brief and **never
  invents a fact**. A fabricated metric, customer name, quote or logo is worse than a visible blank —
  a placeholder gets caught, a plausible fabrication ships. **No placeholder reaches a rendered
  surface** (lorem, "Feature one", an unfilled `{}`) — that is a defect, not a TODO. Per-section copy
  contracts in [marketing-copy.md](references/marketing-copy.md).
- **Charts** use the **chart role tokens** (`--color-chart-*`, sequential/diverging ramps) and the
  [data-viz.md](references/data-viz.md) rules — fixed categorical order, never cycled; **one axis**
  (never dual); identity never color-alone (legend + direct labels); text wears text tokens; status
  colors reserved. Never ad-hoc chart hex; re-validate the palette if you change a hue.

## When you build

Setup a project with `/design-flow:setup`; author a component with `/design-flow:component`; check
drift with `/design-flow:audit` (design-flow plugin). Always: pick the semantic role, compose
primitives, apply the catalog variant, add the a11y + responsive behavior — in that order.

## If the code here breaks, report it (feedback loop)

The token/CSS layer (`@theme`, `@utility` recipes, roles, `dark:`) and the Stimulus mixins are
build-verified against the Tailwind v4 compiler + Node. The **ViewComponent / ERB / Rails
integration is doctrine, not runtime-verified against a live Rails app** — so if code this
skill told you to write fails to compile, render, or behave correctly in a real project (a
ViewComponent that errors, a Turbo Stream/modal flow that doesn't wire up, a token that
doesn't resolve), that is a toolchain defect, not your bug. **Report it upstream with
`/rails-flow:report`** (component `fidara-design`, or `design-flow` if it came from a
`/design-flow:*` command) so it gets fixed for everyone. This is how the doctrine hardens.

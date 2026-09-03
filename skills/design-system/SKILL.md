---
name: design-system
description: >
  The design system — how to build consistent, modern, responsive UI in Rails 8 +
  Hotwire + Tailwind CSS v4, brand-parameterised via brand packs. Load this WHENEVER building or
  reviewing UI: components (buttons, cards, forms, nav, modals, tables, badges, alerts),
  page layouts, tokens/theming, dark mode, responsiveness, or brand/logo usage. It defines
  the token architecture (brand primitives → semantic roles → fluid scale), the layout
  primitives you compose instead of ad-hoc flex/grid, the component catalog with
  variant/size/state, the Stimulus interaction patterns, and the responsive doctrine.
  Consistency is enforced here, not left to taste — and **art direction** is taught rather than
  left undefined: visual hierarchy, per-surface aesthetic intent, and the difference between a
  surface that is correct and one that is considered.
---

# Design System

Build every UI by **composing tokens, layout primitives, and catalog components** — never
ad-hoc CSS. This system makes UI consistent across projects without a designer or Figma.
It is **prescriptive**: where it gives a token, a recipe, or a variant set, use exactly
that. Inconsistency in components degrades the whole product, so drift is a defect.

**Stack:** Rails 8 · Hotwire (Turbo + Stimulus) · **Tailwind CSS v4** (CSS-first `@theme`,
no `tailwind.config.js`, no npm) · Lucide icons.

**The system is brand-neutral; a brand pack is a theme.** The system owns the *structure* —
which semantic roles exist, the layout primitives, the component catalog, the scale, motion and
a11y rules. A pack (`fidara`, `reliance`, …) owns only the *values*: its private primitive
palette, fonts, logo, and how each role maps to a primitive in light and in dark. Components
consume **roles only** (`bg-primary`, `text-muted-foreground`) and never name a primitive, so a
component never names a brand — each pack may prefix its primitives however it likes (`fm-*`,
`rh-*`, none). Which pack a project uses is recorded once, in `config.x.brand.pack`. See
[references/brand.md](references/brand.md).

> **Tailwind here is a deliberate choice, not a claim that hand-written CSS is inferior.**
> Canonical Rails apps — including 37signals' own ([campfire](https://github.com/basecamp/once-campfire),
> writebook, fizzy) — hand-write vanilla CSS, and do it well. We standardize on Tailwind v4
> because this system's guarantee is **mechanically enforceable consistency**: `@theme` role
> tokens, `@utility` primitives, and utility class names are greppable, so `/design-flow:audit`
> and the `design-auditor` can *verify* conformance and catch drift. That check doesn't exist
> for bespoke stylesheets. If a project has an established vanilla-CSS system, record it as a
> Project Override rather than converting it on this skill's authority.

## Where to read next — by task, not in order

This file is the whole of what to load up front. Everything below is read **only when the task
needs it**: references cost nothing until opened, and a task that builds a button does not pay for
the mobile bridge. Read the row that matches, before writing code in that area; each file carries
the exact recipes, the variant vocabulary, and the traps. (This section used to say *"read in
order"* over eight files — about 78k tokens before the first button — which is the single largest
context cost in the toolchain and bought nothing a routed read does not.)

| Read | When the task involves |
|---|---|
| [references/foundations-tokens.md](references/foundations-tokens.md) | **Any colour, type or spacing decision.** The one `@theme` block: brand primitives → semantic roles (`--primary`, `--background`, `--muted`, `--border`, `--ring`, … each with a `-foreground` pair) → fluid Utopia scale + measure, radius, shadow, motion. Dark mode = re-point roles under `.dark`. |
| [references/brand.md](references/brand.md) | **Brand packs** — what a pack may and may not change, pack anatomy (`brand.json`, `theme.css`), variants, the completeness lint, starting a pack from a client's colours or from none |
| [references/layout-primitives.md](references/layout-primitives.md) | **Laying anything out.** Stack, Cluster, Center, Box, Grid, Sidebar, Switcher, Cover, Frame, Reel, Imposter, Icon, Container — intrinsic response (`flex-wrap`, `auto-fit/minmax`, `clamp()`); breakpoints only for true structural swaps |
| [references/page-anatomies.md](references/page-anatomies.md) | **A whole screen.** 3 shell archetypes (sidebar + mobile drawer, stacked, multi-column) × 3 anatomies (home/dashboard, detail, settings), each with mobile behaviour and scroll containment; the primitive-instead-of-breakpoint substitution table. A screen is composed, not designed. |
| [references/components.md](references/components.md) | **A specific component** — the catalog: each entry a composition of primitives + roles with a fixed variant × size × state vocabulary, a11y checklist and responsive behaviour. Open the one entry you need; do not read the file through. |
| [references/components-commerce.md](references/components-commerce.md) | **Selling something** — product card, filter panel, quick view, cart drawer, payment, promo code, plan comparison, seat selector, saved payment methods, subscription state. Open only for a commerce surface; the rest of the catalogue stays in `components.md`. |
| [references/forms.md](references/forms.md) | **Any form** — controls, simple_form wiring, validation display, the Turbo 422 contract |
| [references/coverage.md](references/coverage.md) | **A component with no catalog entry.** One row per component: `documented` / `derivable` / `needs doctrine #N`, what to build it from, where it belongs. Generated by `scripts/build_coverage.py`; never hand-edit. |
| [references/interaction-stimulus.md](references/interaction-stimulus.md) | **Behaviour** — the four reusable Stimulus mixins (list-navigation, focus-trap + restore, dismissable-layer, anchored-position) that cover every overlay; styling off `data-[state=…]` / `aria-*` |
| [references/motion.md](references/motion.md) | **Anything that moves** — two curves, three distance-chosen durations, departures shorter than arrivals, reduced-motion, and the eight ways a gesture can be abandoned |
| [references/responsive.md](references/responsive.md) | **Small screens** — fluid-first + intrinsic primitives, when a breakpoint is justified, `min-h-touch` 44px targets, safe-areas |
| [references/mobile.md](references/mobile.md) | **Hotwire Native** — one system across web and native shells: safe-areas, bridge components, path config, native token export |
| [references/reference-implementation.md](references/reference-implementation.md) | **Writing a ViewComponent** — the canonical Button/Card pattern and the four Stimulus mixins as code |
| [references/component-implementations.md](references/component-implementations.md) | **The full catalog as code** — Badge, Alert, form controls, Modal, Dropdown, Tabs, Toast, Tooltip, Avatar, EmptyState, Sidebar, Switcher. Open the component you are building. |
| [references/mobile-reference-implementation.md](references/mobile-reference-implementation.md) | **Hotwire Native web-side code** — native detection, path config, bridge components, safe-area/touch, table → card-stack |
| [references/native-tokens.md](references/native-tokens.md) | **Fully native Android/iOS screens** — role → Material 3 / iOS mapping and the script emitting `colors.xml` / `Theme.Fidara` and SwiftUI `Color` from `@theme` |
| [references/crud-modal-pattern.md](references/crud-modal-pattern.md) | **Create / edit / delete** — the modal-driven, in-page CRUD flow: persistent `turbo-frame` modal + Turbo Stream list updates + confirmation modal + `modal_controller`. Never a full-page new/edit form. |
| [references/design-handoff.md](references/design-handoff.md) | **Porting a Claude Design artboard** (JSX/TSX or `<x-dc>` export) to ERB, ViewComponents, simple_form, Turbo and Stimulus. Read it **before** translating one: the canvas's `:root`, inline styles and CDN font are preview scaffolding; its `support.js` is a React runtime that is never ported. |
| [references/data-viz.md](references/data-viz.md) | **Charts, KPIs, dashboards** — the validated `--color-chart-*` palette, the form → colour → validate procedure, KPI-tile and chart recipes, chart a11y |
| [references/visual-assets.md](references/visual-assets.md) | **The large visual area** of a hero, feature band, split sign-in or 404 — the tier hierarchy (product screenshot → data-viz → brand-geometric decoration → illustration, last), CSS decoration derived from the brand's geometry, the screenshot capture recipe |
| [references/reference-research.md](references/reference-research.md) | **Before any new design work** — gather references for the *kind* of problem, extract why each works, build from the mechanisms in the pack's own tokens. Skip it and you get the median of everything the model has seen. Three sources minimum, never all from your own category. |
| [references/reference-sources.md](references/reference-sources.md) | **Where reference material is** and how to capture it — sources needing a human sign-in, and the three capture mechanics whose failures are silent (lazy loading, automation challenges, rotting selectors) |
| [references/art-direction.md](references/art-direction.md) | **"Is this considered, or mechanically assembled?"** — one focal point per surface, a different aesthetic brief per surface class (marketing = emotion, dense app = clarity), the one sanctioned way to break the grid. Advisory: `design-auditor` is the gate, `design-critic` the lens. |
| [references/marketing-copy.md](references/marketing-copy.md) | **Any marketing surface** — what each section *says*: per-section copy contract, length caps derived from the shipped measures, placeholder checks. Layout without copy doctrine is a well-composed page of lorem-grade words. |

`references/component-shapes.json` is **machine-read** — the sidecar `design_prompt.py` draws
components from, reconciled against the catalog by a gate. It is not doctrine; do not load it.

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
`/rails-flow:report`** (component `design-system`, or `design-flow` if it came from a
`/design-flow:*` command) so it gets fixed for everyone. This is how the doctrine hardens.

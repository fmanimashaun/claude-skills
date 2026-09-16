# Responsive Doctrine

Inconsistent responsiveness is a top failure mode: ad-hoc components re-invent how they
stack/collapse and break at odd widths. So responsiveness is **prescribed**, in three layers,
in this priority order:

## 1. Fluid (default, no queries)

Type and space scale continuously via the Utopia `clamp()` tokens (`--text-step-*`,
`--space-*`) — smooth across all viewports, no jumps. Size everything from that scale; cap
running text at `--measure` (~65ch). This alone handles most "it looks cramped/huge" issues.

## 2. Intrinsic layout (default, no queries)

Use the layout primitives so structure adapts to available space with **zero** media queries:
- multi-column that reflows by count → `grid-auto` (`repeat(auto-fit, minmax(min(--min,100%),1fr))`)
- sidebar + content that collapses to stacked → `Layout::Sidebar` (flex-basis threshold)
- equal columns that flip row↔stack together → `Layout::Switcher` (threshold)
- wrapping groups → `cluster`; horizontal overflow strip → `reel`
Prefer these over `sm:`/`md:`/`lg:` utilities. If you're writing breakpoint classes to change
layout, first check whether a primitive expresses it intrinsically.

## 3. Breakpoints (exception — structural swaps only)

Reserve explicit breakpoints (`sm 640 · md 768 · lg 1024 · xl 1280 · 2xl 1536`, or component
`@container`) for changes no intrinsic mechanism expresses — genuine structural swaps:
- **nav → rail → drawer**: THREE states, not two — expanded rail `hidden lg:flex lg:w-72`, icon rail
  `hidden sm:flex sm:w-[4rem] lg:hidden` between `sm` and `lg`, off-canvas drawer + backdrop below
  `sm`. The middle one is the one shells forget, and it is the difference between 532px and 696px of
  content in an 800px window. See [§4](#4-adaptive--when-scaling-stops-being-enough-the-position-stated).
- **table → card-stack** on small screens (or keep `overflow-x-auto` — decide per table, state it).
- **header chrome** show/hide (`role pill hidden sm:flex`, username `hidden lg:flex`).
Use `@container` (via `Layout::Container`) when the switch depends on a component's *own* width,
not the page's.

## 4. Adaptive — when scaling stops being enough (the position, stated)

**We are fluid-first with sanctioned structural swaps, and that is a choice.** Material 3 draws the
distinction: *"While responsive design scales a single layout to fit any screen, adaptive design
customizes a product to optimize the experience on each device."* We take the first, and the three
layers above are how. What follows says where scaling stops being enough — because "it stretches"
is not an answer at 2560px, and silence about wide screens is how a 1044px measure ends up at 2200.

**The boundary: scale until the CONTENT changes meaning, then swap.** A card grid that reflows from
two columns to four is scaling. A list that becomes a list *beside* its detail is a swap: the
screen now answers a different question, and no amount of `minmax()` produces it.

**None of this is device targeting.** M3's own rule is *"Design for breakpoints instead of specific
devices"* ([M3, Breakpoints](https://m3.material.io/foundations/layout/breakpoints)) — which is our
rule too, and the reason `@container` is often the better mechanism: a pane keyed to its own width
survives being moved into a narrower column.

### The bands, and what Google's figures map onto

M3 renamed **window size classes** to **breakpoints** in its May 2026 update (and "responsive
layout" to "adaptive design"); the Android/Compose API still calls the type `WindowSizeClass`, so
both names are current in different places. The dp values did not change.

| M3 breakpoint | dp | nearest of ours | panes | margin |
|---|---|---|---|---|
| Compact | 0–599 | below `sm` (640) | 1 | 16dp |
| Medium | 600–839 | `sm`–`md` | 1 recommended, 2 permitted | 24dp |
| Expanded | 840–1199 | `md`–`lg` | 2 recommended, 1 still valid | 24dp |
| Large | 1200–1599 | `xl` | 2 recommended, 1 still valid | 24dp |
| Extra-large | 1600+ | beyond `2xl` | 2 recommended, 1 or 3 valid | 24dp |

**The pane counts are recommendations, not a floor.** M3 keeps one pane valid through Large — *"a
single-pane layout can work when displaying visually- or information-dense content"* — and allows a
third at Extra-large. Only the **list-detail** canonical layout states them as a table
(1 / 1-or-2 / 2 / 2 / 2); do not quote that table as a rule for every screen.
([M3 panes](https://m3.material.io/m3/pages/scaffold/panes),
[list-detail](https://m3.material.io/foundations/layout/canonical-examples/list-detail).)

**Our bands are px and theirs are dp**, so the rows are a mapping and not an equality. Where a
figure of theirs is used below it is quoted in dp and converted once, at the edge.

### Which navigation at which width

This is the decision every shell makes implicitly and states nowhere, and it is where a consuming
app went wrong: one switched its entire shell at `md` and showed a **236px expanded sidebar in a
768px viewport** — 31% of the screen — because nothing said otherwise.

| band | navigation | why |
|---|---|---|
| Compact | drawer, reached from a header control | our rule — see below |
| Medium | **rail, collapsed to icons** (`4rem`) | 288px of sidebar in an 800px window is a third of the screen |
| Expanded and wider | rail, expanded (`lg:w-72`), collapsible | the shipped Sidebar entry |

Two of those three rows are ours. What Google actually says, kept separate from what we decided:

- **The bar-or-rail split is the Android Compose DEFAULT**, not M3 design guidance: *"The default
  behavior is to show either of the following UI components: Navigation bar if the width or height
  is compact or if the device is in tabletop posture; Navigation rail for everything else"*
  ([Android, adaptive navigation](https://developer.android.com/develop/adaptive-apps/guides/build-adaptive-navigation)).
  The drawer in that page is a **manual override** in a "Customize navigation types" sample, so
  "drawer at expanded" is not a Google default and must not be cited as one.
- **M3's own per-breakpoint pages are finer**, and at Medium the answer depends on the pane count:
  *"Single-pane layouts: Navigation rail… Two-pane layouts: Navigation bar."* At Expanded and above:
  *"Use a navigation rail, either collapsed or expanded."*
- **The navigation drawer is legacy in M3's expressive update**: *"Navigation drawers let people
  switch between UI views on larger devices. In the expressive update, use an expanded navigation
  rail."* That is about a *persistent* drawer at desktop width. Ours is the overlay drawer at
  compact, which is a different control answering a different problem.

**OUR RULE AT COMPACT, and the reason it differs from Android's default.** A native tab bar holds
the whole of a small app's navigation. A web bottom bar holds four or five items, costs viewport
height it never gives back, and fights the browser's own chrome — so on the web it does not replace
the rail, it *truncates* it. Measured in a consuming app: a bottom bar rendering `items.first(4)`
of an eight-item rail left Sign out, Help and Account unreachable on a phone, and a second menu was
added to the header to carry them — which then sat beside a rail that already had Sign out.

So: **at compact, the primary navigation must be reachable IN FULL from one control.** A drawer
satisfies that by construction. A bar satisfies it only if the bar holds every top-level
destination. **A destination that exists only in a compensating menu is the defect** — the test is
not "is there a bottom nav" but "can a person reach every rail destination without knowing a second
surface exists". That rule is ours; `coverage.md`'s Bottom navigation row carries it.

### Above 1536px, the measure is capped and the shell is not

Our scale stops at `2xl`; M3 names Large (1200–1599dp) and Extra-large (1600dp+, *"desktop,
ultra-wide monitors"*) as distinct. The decision, so that silence stops being the answer:

- **Running text stays capped at `--measure`.** A 2560px column of prose is unreadable at any type
  size, and no breakpoint fixes it.
- **The shell fills the window; the CONTENT centres in it.** `center` with the fluid gutters is
  already this — an ultra-wide monitor gets more margin, not longer lines.
- **A second pane is how a wide screen earns its width, not a wider single pane.** Which is the
  canonical layouts, below in `page-anatomies.md`.
- **Fixed panes have a stated width at these sizes**: M3 gives 360dp at Expanded for a supporting
  pane and *"the fixed pane should have a width of 412dp by default"* at Large and Extra-large
  ([M3, large & extra-large](https://m3.material.io/foundations/layout/breakpoints/large-extra-large)).
  Use `22.5rem` / `25.75rem` and let the flexible pane take the rest.

## Prescribed per-element behavior (the standard)

| Element | Behavior |
|---|---|
| App shell | `Layout::Sidebar`; main content in a `center` (gutters `px` fluid); the main region scrolls, not the page. |
| Sidebar | off-canvas drawer `<sm`; icon rail `4rem` from `sm`; expanded rail `lg:w-72`, collapsible. |
| Header | hamburger `sm:hidden` (it opens the drawer, and above `sm` the rail is already on screen); role pill `hidden sm:flex`; sticky, `border-b border-border`. |
| Toolbars | `cluster` (wraps intrinsically); action buttons `w-full md:w-auto`. |
| Card/stat grids | `grid-auto`, `--min: 16rem` (stacks → multi-col by space). |
| Forms | `grid-auto`/`Switcher`, not hand `grid-cols`. |
| Modal | width tiers `max-w-md…4xl`; wrapper `p-4 sm:p-0`; body `max-h-[70vh] overflow-y-auto`. |
| Tables | `overflow-x-auto`, or `md:table` + `md:hidden` card-stack for dense data. |
| Tap targets | `min-h-touch` (44px) on all interactive controls — **wire it** (was defined-but-unused). |
| Mobile / native | apply `pt-safe`/`pb-safe` safe-area utilities on fixed chrome; `body.mobile-app` toggles for Hotwire Native shells. |

## Rules

1. Fluid + intrinsic first; a breakpoint must justify itself as a structural swap.
2. No magic-number widths; thresholds live in primitive `--custom` props / container queries.
3. Test at 320px, 768px, 1280px and at 200% zoom; the measure must hold and nothing overflows `x`.
4. Respect `prefers-reduced-motion` and user font-size (rem/em everywhere).

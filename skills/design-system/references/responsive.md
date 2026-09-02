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
- **nav → hamburger**: mobile off-canvas drawer `lg:hidden` + backdrop; desktop rail `hidden lg:flex lg:w-72`.
- **table → card-stack** on small screens (or keep `overflow-x-auto` — decide per table, state it).
- **header chrome** show/hide (`role pill hidden sm:flex`, username `hidden lg:flex`).
Use `@container` (via `Layout::Container`) when the switch depends on a component's *own* width,
not the page's.

## Prescribed per-element behavior (the standard)

| Element | Behavior |
|---|---|
| App shell | `Layout::Sidebar`; main content in a `center` (gutters `px` fluid); the main region scrolls, not the page. |
| Sidebar | off-canvas drawer `<lg`; rail `lg:w-72`, collapsible to `4rem`. |
| Header | hamburger `lg:hidden`; role pill `hidden sm:flex`; sticky, `border-b border-border`. |
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

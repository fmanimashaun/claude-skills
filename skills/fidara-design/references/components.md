# Component Catalog

Each component is a **ViewComponent** composing layout primitives + **semantic role tokens**,
with a fixed **variant × size × state** vocabulary. Reuse the SAME axes everywhere: sizes
`sm | md | lg` (+ `icon` for buttons); state via attributes (`disabled`, `aria-invalid`,
`data-state`, `aria-expanded`), never bespoke classes. Every component carries the a11y +
responsive rules listed. Class strings below use role tokens only — copy the recipe, don't
substitute raw colors.

Express variants server-side as a Ruby map (base + variants + sizes + defaults), the cva
pattern without the JS dep:

```ruby
# app/components/ui/button_component.rb (shape for every catalog component)
BASE = "inline-flex items-center justify-center gap-2 rounded-md text-step-0 font-medium " \
       "transition-colors duration-[180ms] ease-out " \
       "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2 " \
       "disabled:opacity-50 disabled:pointer-events-none min-h-touch"
VARIANT = {
  primary:     "bg-primary text-primary-foreground hover:bg-primary/90",
  secondary:   "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  outline:     "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
  ghost:       "hover:bg-accent hover:text-accent-foreground",
  link:        "text-primary underline-offset-4 hover:underline",
}
SIZE = { sm: "h-8 px-3", md: "h-9 px-4", lg: "h-10 px-6", icon: "size-9 p-0" }
DEFAULTS = { variant: :primary, size: :md }
```

## Button
- **Variants:** `primary · secondary · destructive · outline · ghost · link`. **Sizes:** `sm/md/lg/icon`.
  **States:** hover (`/90` shift), `focus-visible` ring, `disabled`, `loading` (inline `animate-spin`
  Lucide `loader-2` + keep label; set `aria-busy`). Icon: `left|right|only` (icon-only → `sr-only` label).
- **a11y:** real `<button>`/`<a>`; `min-h-touch`; visible focus ring; `aria-busy` when loading.
- **Responsive:** in toolbars/headers, full-width stacked on mobile → inline at `md`: `w-full md:w-auto`.

## Card
- Slot layout, not a variant enum. `Ui::Card` slots: `media` (a `frame`), `header`, `body`, `footer/actions`.
  Recipe: `box` primitive → `bg-card text-card-foreground rounded-lg border border-border` + inner `stack`.
  **No shadow by default** (1px border does the separation); elevate only genuine overlays.
- **Recipes:** stat/KPI (icon chip `size-10 rounded-md bg-primary/10 text-primary` + `text-step-2 font-bold` value),
  detail (**render the Description list component at `inline`** — do not re-implement `<dl>` rows here),
  selectable option (radio tile: selected =
  `border-primary bg-primary/5`), section/panel (`<fieldset>`). Host in `grid-auto` (`--min: 16rem`).

## Heading blocks (page / section / card)
- **The region `page-anatomies.md` calls a "heading block".** Three scales, same anatomy, so a screen
  never re-derives it: `page` (the one `<h1>`, `text-step-3`), `section` (`<h2>`, `text-step-2`),
  `card` (`<h3>`, `text-step-1`). Scale is the *only* difference — same slots, same behaviour.
- Anatomy: `cluster justify-between items-start` of **[eyebrow? → title → description?]** (a `stack
  gap-1`) and **actions** (a `cluster`). Optional `meta` row under the title for status badge +
  timestamps at `text-step--2 text-muted-foreground`. Description is prose, so `text-step-0
  text-muted-foreground prose-measure` — the one place a heading block carries `step-0`.
- **a11y:** exactly one `page` block per screen; never skip a level to get a size (a card heading in
  a section is `<h3>`, not an `<h2>` styled smaller). If a section has no visible title it still needs
  `aria-labelledby` pointing at an `sr-only` heading.
- **Responsive:** none needed — `cluster` wraps, so actions drop below the title on a narrow screen.
  Keep the **primary** action visible and move the rest into an overflow menu rather than letting
  four buttons wrap into a stack.

## Badge / Tag / Chip
- **Variants:** `primary · secondary · success · warning · destructive · outline · muted`. **Sizes:** `sm/md`.
  Shape `rounded-full`, `inline-flex items-center gap-1 px-2.5 py-0.5 text-step--1 font-medium`.
  Recipe (soft fill): `bg-primary/10 text-primary` (swap role per variant). Features: leading dot, dismissible
  (`×` with `sr-only` "Remove"), count/notification (absolutely positioned).
- **One badge mechanism** — this replaces auctioneer's two (partial + helper) and their divergent palettes.

## Alert / Banner
- **Intents:** `info · success · warning · error` (+ neutral `default`). Recipe: `box` +
  `border-l-4` accent + `[&_svg]:text-{intent}` icon + `stack` body; dismissible via the `dismiss` mixin.
  `role="alert"` (assertive) or `role="status"` (polite). Colored by role token, text stays `foreground`.

## Modal / Dialog
- `Ui::Modal` rendered into the layout's `<turbo-frame id="modal">` (open via `data: { turbo_frame: "modal" }`).
  **Imposter** positioning + `bg-popover text-popover-foreground rounded-lg shadow-lg` (card-class
  surface → the `rounded-lg` token = 12px, not an arbitrary value); backdrop
  `bg-fm-navy/50 backdrop-blur-sm`. **Sizes:** `sm max-w-md · md max-w-lg · lg max-w-2xl · xl max-w-4xl · full`.
  Body `max-h-[70vh] overflow-y-auto`. Slots: `title`, `body`, `actions` (a `cluster`).
- **Behavior:** the `modal` Stimulus controller = focus-trap + focus-restore + Esc + backdrop-close +
  body-scroll-lock; `role="dialog" aria-modal="true" aria-labelledby`. Delete-confirmation = Modal(`sm`) recipe.
- **Responsive:** wrapper `p-4 sm:p-0`; `full` → `max-w-full mx-4`.

## Dropdown / Menu
- `Ui::Dropdown` (trigger slot + items). `role="menu"`/`menuitem`; trigger `aria-haspopup="menu" aria-expanded
  aria-controls`. Panel `bg-popover text-popover-foreground rounded-md border border-border shadow-md
  divide-y divide-border`. Item types: link, button, checkbox, radio, header, divider.
- **Behavior:** `dropdown` controller built on the **list-navigation** + **dismissable-layer** + **anchored-position**
  mixins (roving tabindex, Esc/outside-click, placement). Style open state via `data-[state=open]`.

## Disclosure / Accordion
- `Ui::Disclosure` (trigger slot + panel slot) and `Ui::Accordion` (renders many `Ui::Disclosure`,
  `group:` set). Trigger is a real `<button aria-expanded>` + `aria-controls`; the panel carries
  **`hidden` when collapsed** — `aria-expanded="false"` alone leaves the content in the accessibility
  tree and in the tab order, so both are required, not either.
- **Accordion adds a heading wrapper:** the trigger button sits inside `h2`–`h6` (or
  `role="heading" aria-level`), and that heading contains **only** the button — a badge or overflow
  menu beside the header goes *outside* it. Panel gets `role="region"` + `aria-labelledby` **only up
  to ~6 simultaneously-expandable panels**; past that the landmark noise is worse than the structure.
- **Two modes:** independent collapse, and single-open collapsible (`group:`). We do **not** ship
  APG's always-one-expanded variant — see `interaction-stimulus.md` for why.
- Panel `border-t border-border`; trigger `flex w-full items-center justify-between py-4 text-left
  font-medium`, chevron rotates via `data-[state=open]:rotate-180`. State styled off
  `aria-expanded` / `data-[state=open]`, never a JS-toggled class.
- **Behavior:** `disclosure` controller. `Enter` **and** `Space` activate; `Tab`/`Shift+Tab` move
  between headers. Height transition respects `prefers-reduced-motion`, and the state change never
  depends on an animation event firing. Full contract, and what is APG-required versus ours, in
  [interaction-stimulus.md](interaction-stimulus.md#disclosure--the-full-contract-142).
- **`<details>`/`<summary>`** is the cheaper option for simple, unanimated cases — but it cannot
  animate open/close at all, so it is not a drop-in swap for the controller.

## Navigation (header + sidebar + tabs)
- **App shell** = `Layout::Sidebar` (desktop rail `lg:w-72`, collapsible to `4rem`) + a sticky `header`
  (`h-14 border-b border-border`). Mobile: sidebar becomes an off-canvas **drawer** (`fixed inset-0
  -translate-x-full` + backdrop, `lg:hidden`), toggled by the hamburger. Nav links: active = `bg-accent
  text-primary`, `aria-current="page"`. **Standardize active color on `--primary`** (resolves the
  auctioneer `cerulean` vs fmworkflows `electric` drift — dark mode already lifts primary→electric).
- **Tabs** (`Ui::Tabs`): `role="tablist"/tab/tabpanel`, `aria-selected`, roving tabindex; styles `underline |
  pill | full-width`; active = `data-[state=active]:border-primary`.

## Breadcrumbs
- `<nav aria-label="Breadcrumb">` → `<ol class="cluster">` of items at `text-step--1
  text-muted-foreground`; the **current page is the last item, `aria-current="page"`, not a link**,
  and takes `text-foreground`. Separators are decorative (Lucide `chevron-right`, `aria-hidden="true"`)
  and live in the markup, never as a CSS `::after` — a screen reader should hear "Invoices, INV-042",
  not "Invoices chevron INV-042".
- **Truncation, not scroll:** past ~3 levels show **first → ellipsis → last two**, with the collapsed
  middle in a `Ui::Dropdown` so it stays reachable. A breadcrumb that scrolls horizontally on a phone
  has failed at its one job (telling you where you are at a glance).
- **a11y:** links get `min-h-touch`; the ellipsis trigger is a real `<button>` with an `sr-only`
  label ("Show 2 more levels").
- **Not navigation state.** Breadcrumbs show *hierarchy*, so they never reflect history. If the parent
  is ambiguous the page needs a different shell, not a smarter breadcrumb.

## Table (CRUD)
- **CRUD is modal-driven and in-page** — new/edit/delete open in the shared `turbo-frame` modal; success
  updates the list via Turbo Stream (`prepend`/`replace dom_id`/`remove dom_id`) + a toast; rows are
  `dom_id`-addressable so streams can target them. No full-page new/edit forms. Full flow:
  [crud-modal-pattern.md](crud-modal-pattern.md).
- Keep the proven `shared/_crud_table`, `_crud_header`, `_crud_row_actions` partials, refactored to role
  tokens + components. `<table class="w-full text-step-0 text-left">`, header `text-step--1 uppercase
  bg-muted text-muted-foreground`, sortable headers (link + Lucide chevron), optional select-all.
- **Responsive:** wrap in `overflow-x-auto` (horizontal scroll). For dense data on small screens prefer a
  **card-stack** fallback (`hidden md:table` + a `md:hidden` list of `box`/`stack` rows) — pick per table and
  state it; don't leave scroll as the only mobile story.

## Description list
- **The one mechanism for label/value pairs** — record details, summaries, review steps. `<dl>` with
  `<dt>` at `text-step--1 text-muted-foreground` and `<dd>` at `text-step-0 text-foreground`; money
  and identifiers in `font-mono` so columns align.
- **Layouts:** `stacked` (`<dt>` above `<dd>`, one column — the mobile default and fine everywhere),
  `inline` (label left, value right: `cluster justify-between` per row, `divide-y divide-border` on
  the list), `grid` (multi-column via `grid-auto`, `--min: 16rem`, for wide summaries). Choose by
  content length, not viewport: a long value wraps badly in `inline`, so it belongs in `stacked`.
- **Empty values are explicit** — render an em dash with `sr-only` "not set", never a blank `<dd>`,
  which reads as a rendering bug.
- **a11y:** keep `<dt>`/`<dd>` pairing intact; a row wrapper must not sit between them (invalid and it
  breaks pairing for assistive tech). Multiple values for one label = repeated `<dd>`, no list inside.
- Card's **detail** recipe is this component at `inline`, not a second mechanism — compose it, don't
  re-implement the rows.

## Divider
- **A recipe, not a component.** Plain rule: `<hr class="border-border">` (an `<hr>` is already
  `role="separator"`, so add nothing). Inside a `stack` prefer the parent's `gap` and no rule at all —
  reach for a divider only when a boundary must be *seen*, not merely spaced.
- **Labelled divider** ("or", "3 more"): `cluster` of rule → label → rule with the rules as
  `<span aria-hidden="true" class="h-px flex-1 bg-border">` and the label at `text-step--2
  text-muted-foreground`. The rules are decorative, so the accessible output is just the label.
- **In lists and tables use `divide-y divide-border` on the container**, never an `<hr>` between rows —
  one declaration instead of n elements, and no stray separator after the last row.
- Vertical (in a `cluster`): `<span aria-hidden="true" class="w-px self-stretch bg-border">`.

## Button group
- A set of related actions sharing edges: `cluster gap-0` of `Ui::ButtonComponent(variant: :outline)`
  with `isolate` on the wrapper, `-ms-px` on all but the first (so borders collapse to 1px), and the
  outer corners rounded while inner ones square off.
- **Two kinds, and they are different elements.** *Actions* → `role="group"` + `aria-label`, each child
  a real `<button>`. *Single-select* (a view switcher, a date range) → **`role="radiogroup"`** with
  `aria-checked` per option and roving tabindex from the **list-navigation** mixin; the selected option
  is `bg-accent text-primary`, matching nav-active so "selected" reads the same everywhere.
- **a11y:** `min-h-touch` on every child; the focus ring must not be clipped by the overlap — put
  `focus-visible:z-10` on children so the ring paints above its neighbours.
- **Responsive:** ~3 items is the ceiling on a phone. Beyond that use a `Ui::Dropdown` (actions) or
  `Ui::Tabs` (single-select) rather than letting the group wrap — a wrapped button group loses the
  shared-edge affordance that made it a group.

## Media object
- Fixed-size media beside flowing content — the building block of stacked lists, feeds, comments and
  notifications. `cluster items-start` of a `frame` (avatar, icon chip, thumbnail) and a `stack gap-1`
  body; the media gets `flex-none`, the body `min-w-0` so long words truncate instead of pushing the
  media off-screen.
- **Sizes** follow the media: `sm size-8 · md size-10 · lg size-12` (icon chips use the Card stat
  recipe's `rounded-md bg-primary/10 text-primary`).
- **a11y:** decorative media takes `alt=""`; meaningful media carries a real `alt`. If the whole object
  is a link, wrap once and keep the media inside that link rather than nesting two links to the same place.
- **Responsive:** never stacks — the side-by-side relationship *is* the pattern. If the body needs full
  width on a phone, it was a Card, not a media object.

## Toast / Notification
- Container `fixed top-4 right-4 z-[100] stack max-w-sm pointer-events-none`. Each toast = `box` +
  `border-l-4` intent + `shadow-md`, `role="status" aria-live="polite"` (errors `assertive`), auto-dismiss +
  close (the `toast`/`dismiss` mixin). **Emit via Turbo Streams** to prepend into the container. One mechanism
  (replaces the duplicate `_flash`/`_flash_messages` pair).

## Tooltip / Popover
- `role="tooltip"` + `aria-describedby`; shows on **focus and hover** (keyboard parity), Esc dismiss.
  Built on **anchored-position** + **dismissable-layer** mixins. Popover adds focus move-in + `aria-expanded`.

## Avatar
- `Ui::Avatar` (extract it — auctioneer inlines): `rounded-full` image or initials chip
  `bg-primary/10 text-primary`, sizes `sm size-8 / md size-10 / lg size-12`, optional status dot, group/stacked.

## Logo / Brand mark
- `Ui::Logo` — the ONLY way to render the Prism mark; never hand-roll a text eyebrow (a plain
  `<p>Fidara</p>` in place of the mark is a defect). **Variants:** `mark` (prism only) ·
  `lockup` (prism + wordmark). **Sizes:** `sm 20px / md 28px / lg 40px` prism height —
  **20px is the floor** (brand.md min sizes; lockup min 140px wide).
- Facet hues are **fixed brand colors** (cyan top / cerulean left / electric right) — the one
  documented place raw brand hex beats role tokens, because facets must never be recolored.
  Wordmark = Bricolage Black `uppercase tracking-tight` on `text-foreground` (dark-mode automatic).
- `brand_variant:` picks the pack variant; the endorsement is a **string the variant carries**,
  not a brand name in code — so a product variant shows it ("fmworkflows" + "by Fidara") and a
  parent or standalone brand sets `endorsement: null` and shows none. A parent does not endorse
  itself. Omit the argument to use the pack's `default_variant`. Clear space 1.5× prism height.
  Never stretch/rotate/recolor/shadow the mark.
- **Required on** marketing, auth, and other full-page single-focus surfaces — paired with the
  `cover > center > stack` recipe (see layout-primitives.md). Worked code in
  [component-implementations.md](component-implementations.md).

## Pagination
- Keep the Pagy-based `shared/_pagination`: per-page `<select>`, "Showing X–Y of Z", windowed links + prev/next
  Lucide chevrons, active = `bg-primary/10 text-primary`. Optional `turbo_frame` target. Responsive `flex-col
  md:flex-row`.

## Empty state
- `cover > center > stack`: icon chip `size-16 rounded-full bg-muted`, title, `max-w-md` `text-muted-foreground`
  description, optional primary action (opens in the `modal` frame). One `Ui::EmptyState` component.

## Forms
See [forms.md](forms.md).

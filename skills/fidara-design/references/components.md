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
  detail (`<dl>` rows `flex justify-between`, money in `font-mono`), selectable option (radio tile: selected =
  `border-primary bg-primary/5`), section/panel (`<fieldset>`). Host in `grid-auto` (`--min: 16rem`).

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
  **Imposter** positioning + `bg-popover text-popover-foreground rounded-[12px] shadow-lg`; backdrop
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

## Navigation (header + sidebar + tabs)
- **App shell** = `Layout::Sidebar` (desktop rail `lg:w-72`, collapsible to `4rem`) + a sticky `header`
  (`h-14 border-b border-border`). Mobile: sidebar becomes an off-canvas **drawer** (`fixed inset-0
  -translate-x-full` + backdrop, `lg:hidden`), toggled by the hamburger. Nav links: active = `bg-accent
  text-primary`, `aria-current="page"`. **Standardize active color on `--primary`** (resolves the
  auctioneer `cerulean` vs fmworkflows `electric` drift — dark mode already lifts primary→electric).
- **Tabs** (`Ui::Tabs`): `role="tablist"/tab/tabpanel`, `aria-selected`, roving tabindex; styles `underline |
  pill | full-width`; active = `data-[state=active]:border-primary`.

## Table (CRUD)
- Keep the proven `shared/_crud_table`, `_crud_header`, `_crud_row_actions` partials, refactored to role
  tokens + components. `<table class="w-full text-step-0 text-left">`, header `text-step--1 uppercase
  bg-muted text-muted-foreground`, sortable headers (link + Lucide chevron), optional select-all.
- **Responsive:** wrap in `overflow-x-auto` (horizontal scroll). For dense data on small screens prefer a
  **card-stack** fallback (`hidden md:table` + a `md:hidden` list of `box`/`stack` rows) — pick per table and
  state it; don't leave scroll as the only mobile story.

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

## Pagination
- Keep the Pagy-based `shared/_pagination`: per-page `<select>`, "Showing X–Y of Z", windowed links + prev/next
  Lucide chevrons, active = `bg-primary/10 text-primary`. Optional `turbo_frame` target. Responsive `flex-col
  md:flex-row`.

## Empty state
- `cover > center > stack`: icon chip `size-16 rounded-full bg-muted`, title, `max-w-md` `text-muted-foreground`
  description, optional primary action (opens in the `modal` frame). One `Ui::EmptyState` component.

## Forms
See [forms.md](forms.md).

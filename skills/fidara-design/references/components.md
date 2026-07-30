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
  Body `max-h-[70vh] overflow-y-auto`. **Slots: `title` and `actions` (a `cluster`) — there is NO
  `body` slot;** the body is the block content, same as Alert. This line advertised one for three
  releases, and `m.with_body` raises `NoMethodError` — the #168/#182 class, in prose the call-site
  linter cannot reach.
- **`placement:`** picks centre or an edge: `:center` (default) · `:left` · `:right` · `:bottom`. An
  **overlay drawer is this component with `placement: :right`** — one dialog implementation, one focus
  trap, one `Esc`. A *persistent* sidebar is not a dialog and must not come through here.
- **Behavior:** the `modal` Stimulus controller = focus-trap + focus-restore + Esc + backdrop-close +
  body-scroll-lock; `role="dialog" aria-modal="true" aria-labelledby`. Delete-confirmation = Modal(`sm`) recipe.
- **Responsive:** wrapper `p-4 sm:p-0`; `full` → `max-w-full mx-4`.

## Drawer / off-canvas
- **No APG pattern of its own** (the index lists 30; Drawer and Off-canvas are not among them), so it
  borrows the Dialog contract — and *which* contract depends on the shape, which is the whole point:
- **Overlay drawer** = the documented `Ui::Modal` positioned to an edge. Full dialog contract:
  `role="dialog" aria-modal="true"` + a name, initial focus inside, focus **restored to the trigger**,
  `Esc` closes, background `inert`. Behavior: the `modal` controller (focus-trap + dismissable).
- **Persistent / push drawer** — the ordinary app sidebar — is **not a dialog and must not trap focus**.
  `<nav>` semantics, no `aria-modal`, no initial-focus steal, `sidebar` controller for collapse only.
  Trapping is what *modality* requires, not a property of being a drawer.
- **Responsive: render both, do not morph one.** Modal drawer below `lg`, persistent `<nav>` at `lg` and
  up. Toggling `aria-modal` and a focus trap by media query means the role changes under the user.
- Panel `bg-popover text-popover-foreground shadow-lg` at `max-w-sm`, full-height, `inset-y-0`;
  backdrop as Modal's. Slots as Modal: `title`, `body`, `actions`.

## Carousel
- **An APG pattern** — cite it, and note that most of its machinery is *conditional*. Best default:
  **do not auto-rotate.**
- Container `role="region"` **or** `role="group"` (APG sanctions both; pick by the page's information
  architecture) + **`aria-roledescription="carousel"`** and an accessible name.
- Slides `role="group"` + `aria-roledescription="slide"` — **except the Tabbed variant**, where a slide is
  `role="tabpanel"` with **no** `aria-roledescription`.
- **Three variants:** *Basic* (prev/next only) · *Tabbed* (one tab stop, the Tabs pattern) · *Grouped*
  (individually-tabbable pickers — APG calls it the least keyboard-friendly, so prefer Tabbed).
- **Prev/Next always; play/pause, stop-on-hover and stop-on-focus only if it auto-rotates.**
  Auto-rotation is governed by **WCAG 2.2.2** (not 2.3.3).
- **Inactive slides leave the accessibility tree via `display:none`/`hidden`/`inert`** — `aria-hidden` is
  not the technique APG names, and translating a slide off-screen while leaving it in the tree is the
  failure the pattern warns about.
- `Tab` is **not scripted** — it follows the page tab sequence. Behavior: the `carousel` controller.

## Image gallery / Lightbox
- **No APG pattern** — a *composition*, the same shape as the Command palette: the documented **Modal**
  containing the documented **Carousel**. Both contracts apply unchanged; the thumbnail grid behind it
  becomes `inert`, and closing returns focus to **the thumbnail that was clicked**.
- Thumbnails are a `grid-auto` of buttons (not links) with `alt` text; the viewer is Modal `xl`/`full`
  with prev/next and a counter.
- **No auto-rotation, so no play/pause** — that follows from the Carousel conditional, not from a
  lightbox rule.
- **Two things here are ours, not the spec's:** using a dialog rather than a full-page route (decided,
  because it keeps the grid's scroll position), and the dialog's name string — use the image's caption or
  alt text so it names the picture rather than repeating "Image viewer".

## Dropdown / Menu
- `Ui::Dropdown` (trigger slot + items). `role="menu"`/`menuitem`; trigger `aria-haspopup="menu" aria-expanded
  aria-controls`. Panel `bg-popover text-popover-foreground rounded-md border border-border shadow-md
  divide-y divide-border`. Item types: link, button, checkbox, radio, header, divider.
- **Behavior:** `dropdown` controller built on the **list-navigation** + **dismissable-layer** + **anchored-position**
  mixins (roving tabindex, Esc/outside-click, placement). Style open state via `data-[state=open]`.

## Combobox / Autocomplete
- **Reach for it only for one of APG's two scenarios**, not by option count: the value must come from
  a **closed set** and the list is too long to scan, or the value is **arbitrary** and suggestions
  help. Neither → native `<select>` (see [forms.md](forms.md)).
- `Ui::Combobox` (input slot + option list). The **input itself** carries
  `role="combobox" aria-expanded aria-controls` — `aria-controls` is required, not decorative, and
  the role goes on the input, never a wrapping div (that is the superseded ARIA 1.1 model).
- **Popup**: `role="listbox"` is the implicit default and needs no `aria-haspopup`. A `grid`, `tree`
  or `dialog` popup **must** declare `aria-haspopup` matching that role — and uses
  `gridcell`/`row`/`treeitem` rather than `option`.
- **Options**: `role="option"`, and `aria-selected="true"` on the **active** option — selection
  follows focus in a combobox, so it moves as the user arrows. It is not "the previously chosen
  value"; that is the common mistake.
- **`aria-autocomplete`** is required *if* you autocomplete: `list` (filter the popup), `both` (filter
  plus inline completion), or omit for `none`. A **select-only** combobox has no text to complete, so
  it carries no `aria-autocomplete` at all and may put the role on a non-`<input>` element.
- **Collapsed panel**: the popup is `hidden`; `aria-expanded="false"` alone leaves options in the
  accessibility tree and the tab order.
- Panel `bg-popover text-popover-foreground rounded-md border border-border shadow-md max-h-64
  overflow-auto`; active option `data-[active=true]:bg-accent`. An optional **Open button** beside the
  input is `tabindex="-1"` and outside the tab order — the input already reaches the popup.
- Error affordances reuse the field contract: `aria-invalid`, `aria-describedby` → the same
  `aria-errormessage` wiring as every other input. Do not reinvent them.
- **Behavior:** `combobox` controller on the **list-navigation** + **anchored-position** mixins.
  `↓` into the popup and `↑`/`↓` within it are required; `Enter` accepts; `Esc` dismisses. **`→`/`←`
  move the text cursor**, not the selection. `Space` types a space — it is *not* an activation key
  here. Full required-vs-optional breakdown in
  [interaction-stimulus.md](interaction-stimulus.md#combobox--the-two-corrections-that-matter-and-a-version-trap-229).
- **Announcing "5 results available" via a live region is our convention, not APG's** — the pattern
  never prescribes it. Worth doing; do not cite it as required.

## Command palette
- **Not an APG pattern** — the APG Patterns index lists **30**, none for a command palette (an
  earlier note here said 33; it was wrong). It is a *composition*, and
  the sanctioned one is a **Modal dialog containing an editable Combobox with a listbox popup**: the
  documented `Modal` for the shell, the documented `Combobox` above for the filter and results.
- **`aria-activedescendant` is effectively mandatory here**, even though both focus models are
  generally allowed: the input must keep focus for typing to filter, so moving DOM focus into the
  results list would break typing. The "dialog popups move DOM focus" rule applies to *opening the
  modal*, not to the filtered list inside it.
- Trigger is a global shortcut (`⌘K` / `Ctrl+K`), so there is no persistently visible field to hang
  `aria-haspopup="dialog"` on — that shape belongs to a Date-Picker-style field that expands, not to
  a palette.
- Result rows wanting icon + label + shortcut hint need a `grid` popup (`gridcell`/`row`), with
  `aria-haspopup="grid"` on the input.

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
  `border-l-4` intent + `shadow-md`, auto-dismiss + close (the `toast`/`dismiss` mixin).
- **`role="status"`, and nothing beside it.** The role already implies `aria-live="polite"` *and*
  `aria-atomic="true"`; writing `aria-live` next to it is redundant, and writing bare `aria-live`
  *instead* of it silently drops the atomic half — an announcement then carries only the changed
  node. **Severity picks the role, not a second attribute:** a confirmation is `status`, a
  time-critical failure is `role="alert"` (implicitly assertive, interrupts). Do not put
  `aria-live="assertive"` on a `status`. Full rule in
  [interaction-stimulus.md](interaction-stimulus.md#loading-progress-and-busy-state-95). **Emit via Turbo Streams** to prepend into the container. One mechanism
  (replaces the duplicate `_flash`/`_flash_messages` pair).

## Progress bar
- **`role="progressbar"` is an ARIA role, not an APG pattern** — there is no pattern page for it, so
  the role definition is the authority. Prefer native `<progress>` where the styling allows it.
- **Every value attribute is optional.** `aria-valuemin` defaults to `0`, `aria-valuemax` to `100`,
  so a 0–100 bar needs only `aria-valuenow`. **Indeterminate = OMIT `aria-valuenow`** — never `0`
  (that reads as "no progress made") and never `-1`.
- **The accessible name is required and comes from the author** — `aria-label` or `aria-labelledby`
  only. The role is *Children Presentational*, so the inner fill `<div>` is not exposed: text inside
  it is not read. Use `aria-valuetext` for "Step 2 of 5", or a visible sibling label referenced by
  `aria-labelledby`.
- **Not focusable, no keyboard.** It reports; it does not accept input.
- **Never `role="meter"` for progress.** `meter` is a static measurement (disk usage, score) and it
  *requires* `aria-valuenow`; ARIA says authors SHOULD NOT use it to indicate progress.
- `h-2 rounded-full bg-muted` track + `bg-primary` fill, `transition-[width]`. Announce
  intermittently via the surrounding `role="status"`, not on every increment — the cadence is our
  convention, not a spec figure.

## Skeleton / loading placeholder
- **No role, no APG pattern, no W3C source at all** — this is convention, and doctrine says so
  rather than dressing it as spec. Prefer it over a spinner **whenever the content's size is known**:
  it reserves the space, so nothing shifts when content arrives (CLS).
- **Hide the shapes, announce once.** `aria-hidden="true"` on every placeholder block plus **one**
  `role="status"` message ("Loading invoices…"). Announcing forty placeholder rectangles is worse
  than announcing nothing.
- `aria-busy="true"` on the region until content arrives — correct to set, but **never the only
  mechanism**: it is advisory (assistive tech *MAY* wait) and poorly supported. `aria-hidden` does
  the actual work.
- `animate-pulse rounded-md bg-muted` at the content's size. Suppress the animation under
  `prefers-reduced-motion` — worth doing, but the SC is **2.2.2 Pause/Stop/Hide**, conditional on
  five-plus seconds *and* parallel content, not 2.3.3 (which covers interaction-triggered motion).
- The natural pairing is a **Turbo frame** with `loading="lazy"`, the skeleton as the frame's
  placeholder content.

## Spinner / busy indicator
- **A spinner is not a progress bar.** If the proportion is unknown, `role="progressbar"` promises a
  value it cannot supply — use `role="status"` with a text message and reserve `progressbar` for when
  you genuinely know the fraction.
- Use it only when the content's size is **unknown**; if it is known, use the Skeleton above.
- A Lucide `loader-circle` with `animate-spin`, `aria-hidden="true"` (the icon is decoration), and
  the announcement in a sibling `role="status"` — never `aria-label` on the spinning icon.
- Same `aria-busy` + reduced-motion notes as Skeleton.

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

# Component coverage — what to build, and where to use it

**Generated — do not hand-edit.** `python3 scripts/build_coverage.py` rebuilds this from a
mechanical enumeration of the reference corpora; `--check` fails if it is stale.

Components are built **just-in-time, in the project**, when a screen needs one — they are
never batch-built here. So this file is not a build queue and not an availability list.
Nothing is withheld: **every row below is buildable on demand.** What differs is how much
the doctrine already tells you, and that is the only axis here.

## How to read a row

| Guidance | Means | What you get |
|---|---|---|
| `documented` | a reference doc defines its anatomy | build it straight from that entry |
| `derivable` | no dedicated entry needed | the **Build from** column names the documented parts it composes from |
| `needs doctrine #N` | an agent would have to invent an a11y or interaction contract | **Build from** still gives the nearest safe approach; `#N` tracks writing the real entry |

`needs doctrine` is the only one that marks a genuine gap, and it is a gap in *writing*, not
in *capability* — you can still build the thing today, you just carry more risk of getting
the keyboard or ARIA contract wrong, which is exactly why it is tracked.

Every row also carries **Where / when to use it**. Knowing how to build a component without
knowing which surface it belongs on is how screens get assembled from the wrong parts, so the
builder refuses to emit a row that lacks it.

## Totals

| | count |
|---|---|
| Tailwind UI leaf components enumerated | 93 |
| Flowbite catalogue entries enumerated | 63 |
| fidara rows | 113 |
| — `documented` | 40 |
| — `derivable` from documented parts | 43 |
| — `needs doctrine` (tracked writing gap) | 30 |

`Kind` is `primitive` · `component` · `composition` · `page archetype`. `In TW` / `In FB`
show which corpus carries the pattern — useful because the two are good at different things:
Tailwind UI wins on visual polish, Flowbite on interaction breadth.

## Documented — build straight from the reference entry

| Component | Kind | In TW | In FB | Where / when to use it | Watch out for |
|---|---|---|---|---|---|
| Alert / Banner | component | ✓ | ✓ | in-page state (Alert) vs page-wide announcement (Banner) | — |
| Avatar | component | ✓ | ✓ | wherever a person is named; pair with the name, never alone as identification | — |
| Badge / Tag / Chip | component | ✓ | ✓ | status and category labels inside table rows, list items and headings | — |
| Breadcrumbs | component | ✓ | ✓ | detail screens more than one level deep, inside the page heading block | separators are aria-hidden markup, never ::after; truncates first → … → last two |
| Button | component | ✓ | ✓ | any action; `primary` once per view, `destructive` only behind a confirm | — |
| Button group | component | ✓ | ✓ | 2–5 related actions, or a single-select filter — `role=group` vs `radiogroup` | actions = role=group; single-select = role=radiogroup — different elements, not variants |
| Card | component | ✓ | ✓ | a bounded surface in a dashboard grid, or a detail panel; also the stat-tile base | — |
| Checkbox | component | ✓ | ✓ | independent booleans; multiples need a fieldset with a legend | — |
| Description list | component | ✓ | — | read-only attribute/value pairs on a detail or settings screen | blank values render an em dash + sr-only 'not set', never an empty <dd> |
| Dropdown / Menu | component | ✓ | ✓ | overflow actions and scope pickers; not for navigation between pages | — |
| Empty state | component | ✓ | — | the zero-row branch of every index — required, not optional | — |
| Form layout | component | ✓ | — | every form — simple_form owns the field anatomy app-wide | simple_form owns every form; the wrapper anatomy is defined once in an initializer |
| Heading blocks (page / section / card) | component | ✓ | ✓ | the top of every page, section and card — the scale prop picks the level, so never style a heading down | one anatomy; scale is the only axis, so a card heading can never be an h2 styled small |
| Logo / Brand mark | component | — | — | shell headers, auth screens and marketing surfaces | ours, not from either corpus: clear-space 1.5×, min 20px / lockup 140px (brand.md) |
| Media object | component | ✓ | — | any avatar/icon + text row: list items, feeds, comments, notifications | never stacks — the side-by-side relationship IS the pattern |
| Modal / Dialog | component | ✓ | ✓ | a focused create/edit/confirm step; never for content a page can hold | — |
| Navigation — header / navbar | component | ✓ | ✓ | the app's top bar in the stacked shell | — |
| Navigation — sidebar / vertical | component | ✓ | ✓ | the app's primary rail in the sidebar/multi-column shells | — |
| Pagination | component | ✓ | ✓ | any index over ~25 rows; pair with the Table | — |
| Radio group | component | ✓ | ✓ | one choice from 2–5 visible options, in a fieldset | — |
| Select | component | ✓ | ✓ | a closed set of ~2–10 options; above that reach for the combobox | — |
| Table (CRUD) | component | ✓ | ✓ | the index of a resource — sortable headers, row actions, select-all | — |
| Tabs | component | ✓ | ✓ | switching views of the SAME resource; never as page navigation | — |
| Text input | component | ✓ | ✓ | single-line entry; the shipped wrapper supplies label, hint and error | floating label is a variant, not a component |
| Textarea | component | ✓ | ✓ | multi-line entry; set rows, never a fixed pixel height | — |
| Toast / Notification | component | ✓ | ✓ | transient confirmation of a completed action; never for errors requiring a decision | — |
| Toggle / Switch | component | ✓ | ✓ | a setting that applies immediately; if it needs Save, use a Checkbox | — |
| Tooltip / Popover | component | — | ✓ | a supplementary label (Tooltip) or a small rich panel (Popover); never the only place information appears | — |
| Stat tile | composition | ✓ | — | the metric row at the top of a dashboard, one metric per Card | page-anatomies composes these from Card, one metric each — deliberately not a new component |
| Detail anatomy | page archetype | ✓ | — | a single record with attributes and actions | — |
| Home / dashboard anatomy | page archetype | ✓ | — | the landing screen after sign-in | — |
| Multi-column shell | page archetype | ✓ | — | screens needing a contextual aside beside the main region | — |
| Settings anatomy | page archetype | ✓ | — | grouped preference forms | — |
| Sidebar shell | page archetype | ✓ | — | authenticated app screens with a persistent rail | — |
| Stacked shell | page archetype | ✓ | — | authenticated screens with few top-level areas, or marketing-adjacent app pages | — |
| Center / container | primitive | ✓ | — | the outer wrapper of page content, capping it at the measure | — |
| Divider | primitive | ✓ | ✓ | between unrelated blocks; inside a list use `divide-y` on the container instead | an <hr> is already role=separator; in lists the answer is divide-y on the container |
| Frame (aspect-ratio media) | primitive | — | ✓ | every image or video, so layout never shifts on load | — |
| List container (divide-y) | primitive | ✓ | — | any stacked list of rows — the container owns the separators | — |
| Prose / long-form type | primitive | — | ✓ | any body copy; the measure cap is what keeps it readable | fluid --text-step-* scale + measure in foundations-tokens.md |

## Derivable — compose it from documented parts

No dedicated catalogue entry, and none needed: these are compositions. Build from what the
**Build from** column names rather than inventing markup — that is what keeps a JIT-built
screen consistent with everything already in the app.

| Component | Kind | In TW | In FB | Build from | Where / when to use it |
|---|---|---|---|---|---|
| Action panel | component | ✓ | — | Card + Heading (card scale) + Button group | an authenticated app screen, inside one of the three shells |
| Activity feed / Timeline | component | ✓ | ✓ | Media object rows in a `divide-y` container; the rail is a border on the container, not a pseudo-element per row | an authenticated app screen, inside one of the three shells |
| Bottom navigation | component | — | ✓ | the native tab bar on Hotwire Native; the shipped sidebar/stacked shells on web | native mobile shells (Hotwire Native); never as a web nav |
| Category filters | component | ✓ | — | `<details>`/`<summary>` groups inside a `stack`, until #142 lands | a commerce surface (catalog, product, cart, checkout) |
| Chat bubble | component | — | ✓ | Media object rows in a `divide-y` container — the same shape, without inventing message semantics | a messaging, comment or activity thread — not general app screens |
| Device mockup | component | — | ✓ | a `frame` at the screenshot's own ratio | marketing surfaces only, to frame a product screenshot |
| Number input | component | — | ✓ | the documented Text input with `inputmode=numeric` | an authenticated app screen, inside one of the three shells |
| Phone input | component | — | ✓ | a text input with `inputmode=tel` and app-side normalisation, using the shipped field anatomy | any form collecting a telephone number |
| Product list / grid | component | ✓ | — | Card + Badge + Button group; prices on the fluid type scale | a commerce surface (catalog, product, cart, checkout) |
| Product quickview | component | ✓ | — | the documented Modal with the product overview blocks inside | a commerce surface (catalog, product, cart, checkout) |
| QR code | component | — | ✓ | generate in the app and render an `<img>` inside a `frame` | wherever a code must be scanned — checkout, tickets, device pairing |
| Search input | component | — | ✓ | the documented Text input, `type=search`, with a leading Lucide icon | an authenticated app screen, inside one of the three shells |
| Speed dial / FAB cluster | component | — | ✓ | the page-header actions slot (Heading + Button group), or a Dropdown for overflow | a mobile-first surface where the primary action must stay reachable while scrolling |
| Stacked list | component | ✓ | ✓ | Media object rows inside a `divide-y` container | an authenticated app screen, inside one of the three shells |
| Status indicator / dot | component | — | ✓ | Badge, or a `size-2 rounded-full` span plus `sr-only` text — never colour alone | an authenticated app screen, inside one of the three shells |
| Store navigation | component | ✓ | — | the documented navbar / sidebar navigation | a commerce surface (catalog, product, cart, checkout) |
| Bento grid section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Blog / article list section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| CTA section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Category preview | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Checkout form | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Contact section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Content / prose section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| FAQ section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Feature section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Footer | composition | ✓ | ✓ | `center` > `cluster` of link lists + Logo | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Grid list | composition | ✓ | — | `grid-auto` of Cards | a region of an app screen, inside one of the three shells |
| Hero section | composition | ✓ | ✓ | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Incentives block | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Logo cloud | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Marketing header | composition | ✓ | — | the documented navbar + Logo; mobile reuses the shell's disclosure | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Newsletter section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Order history | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Order summary | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Pricing section / table | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Product features block | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Product overview | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Promo section | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Shopping cart | composition | ✓ | — | Card + Heading + Description list / Table inside `grid-auto` or `Switcher` | a block within a storefront, product, cart or checkout page |
| Stats section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Team section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Testimonial section | composition | ✓ | — | `center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, Buttons for CTAs — no bespoke section CSS | a section of a marketing page, stacked inside the landing / pricing / about anatomy |
| Keyboard key (KBD) | primitive | — | ✓ | `<kbd>` with muted role tokens at `--text-step--1` | docs and shortcut hints; the command palette needs it |

## Needs doctrine — buildable today, but you are carrying the risk

These need an a11y or interaction contract the docs do not yet state (a keyboard model, an
ARIA pattern, a reduced-motion rule). **Build them when a project needs them** — the
**Nearest guidance** column is the safest current approach — and expect the tracked issue to
replace that approach with a proper entry.

| Component | Kind | In TW | In FB | Tracked | Nearest guidance | Where / when to use it |
|---|---|---|---|---|---|---|
| Accordion / Disclosure | component | — | ✓ | #142 | `<details>`/`<summary>` until #142 lands — native, keyboard-correct, no JS | an authenticated app screen, inside one of the three shells |
| Calendar / Date picker / Time picker | component | ✓ | ✓ | #95 | `input[type=date|time]` via simple_form, plus Rails date helpers — styled with the shipped field anatomy so it matches everything else | an authenticated app screen, inside one of the three shells |
| Carousel / Slider | component | — | ✓ | #95 | `grid-auto`, or a horizontal scroller with visible affordances and real focus order | prefer not to — if a client insists, a marketing surface only |
| Combobox / Autocomplete | component | ✓ | — | #95 | the documented Select until the entry lands — do not hand-roll the ARIA combobox pattern | an authenticated app screen, inside one of the three shells |
| Command palette | component | ✓ | — | #95 | Modal + the list-navigation mixin over a filtered list | an authenticated app screen, inside one of the three shells |
| Copy to clipboard | component | — | ✓ | #95 | a Button plus a Toast confirmation; the clipboard call is a small controller | next to an API key, invite link or ID |
| Drawer / off-canvas | component | ✓ | ✓ | #95 | the documented Modal, positioned to an edge — keep its focus trap | an authenticated app screen, inside one of the three shells |
| File upload / Dropzone | component | — | ✓ | #95 | the documented file field; add drag-and-drop as an enhancement, never as the only path | an authenticated app screen, inside one of the three shells |
| Image gallery / Lightbox | component | — | ✓ | #95 | `grid-auto` of `frame` thumbnails linking to the full image | media-heavy surfaces: portfolio, product media, docs |
| Mega menu / Flyout | component | ✓ | ✓ | #90 | the documented Dropdown for now; hover-intent is what #90 must specify | a marketing surface (landing, pricing, about) — not app screens, which use the shell navigation |
| Progress bar | component | ✓ | ✓ | #95 | `<progress>`, or a div with `role=progressbar` + `aria-valuenow/min/max` and a visible label | an authenticated app screen, inside one of the three shells |
| Range input | component | — | ✓ | #95 | `<input type=range>` in the documented field wrapper; leave the native track | an authenticated app screen, inside one of the three shells |
| Reviews + Rating | component | ✓ | ✓ | #91 | Media object rows; the rating needs an accessible name ("4 out of 5"), not stars alone | a commerce surface (catalog, product, cart, checkout) |
| Skeleton / loading placeholder | component | — | ✓ | #95 | a muted `box` at the content's size, suppressed under `prefers-reduced-motion` | a Turbo frame whose content size IS known — preferred over a spinner because it does not shift layout |
| Spinner / busy indicator | component | — | ✓ | #95 | a Lucide spinner with `aria-busy` on the region it replaces; honour reduced-motion | a region whose content is loading and has no known size |
| Stepper / wizard | component | — | ✓ | #95 | a `cluster` of Badges with `aria-current=step` | a multi-step flow: checkout, onboarding, long forms |
| Video player | component | — | ✓ | #95 | native `<video controls>` inside a `frame` for ratio | marketing and docs surfaces; inside a `frame` so layout never shifts |
| About page archetype | page archetype | ✓ | — | #90 | the marketing header + stacked sections inside `center`; `cover > center > stack` for a single-focus page | a whole marketing or auth page; compose sections inside it |
| Auth page archetype (sign-in / sign-up / reset) | page archetype | ✓ | — | #90 | one of the three shells plus the documented anatomy regions | a whole app screen |
| Cart page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Category page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Checkout page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Error page archetype (404/500) | page archetype | ✓ | — | #90 | the marketing header + stacked sections inside `center`; `cover > center > stack` for a single-focus page | a whole marketing or auth page; compose sections inside it |
| Landing page archetype | page archetype | ✓ | — | #90 | the marketing header + stacked sections inside `center`; `cover > center > stack` for a single-focus page | a whole marketing or auth page; compose sections inside it |
| Order detail page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Order history page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Pricing page archetype | page archetype | ✓ | — | #90 | the marketing header + stacked sections inside `center`; `cover > center > stack` for a single-focus page | a whole marketing or auth page; compose sections inside it |
| Product page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Storefront page archetype | page archetype | ✓ | — | #91 | a stacked-shell page: Heading block, then the commerce blocks in `grid-auto` | a whole commerce page; compose the blocks inside it |
| Inline link | primitive | — | ✓ | #95 | the Button `link` variant's classes on an `<a>`, until a token exists | body copy and prose; for actions use the Button `link` variant |

## Interaction patterns

Enumerated separately because they do not map one-to-one onto a corpus directory —
Flowbite's `data-*` trigger attributes are the better source, and they cut across components.

| Pattern | Status | Note |
|---|---|---|
| disclosure (collapse / accordion) | planned #142 | the single largest gap found: 732 `data-collapse-toggle` instances across the Flowbite corpus and we shipped no controller at all |
| dialog (modal / drawer) | shipped | focus trap, Escape, restore focus on close |
| menu (dropdown) | shipped | roving tabindex, Escape, click-outside |
| list-navigation (tabs / single-select groups) | shipped | arrow keys + Home/End |
| dismissible (alert / toast) | shipped | removes the node, announces politely |
| theme toggle (light / dark) | shipped | 13 corpus pages carry one; ours is a role-token flip |
| filter / typeahead | planned #95 | needed by both command palette and combobox |
| drag and drop (upload) | planned #95 | needed by the file dropzone; keyboard path is mandatory |
| carousel / slide | declined | see Carousel — a doctrine position, not a backlog item |

## Layout primitives

| Primitive | Status |
|---|---|
| `stack` | shipped |
| `cluster` | shipped |
| `center` | shipped |
| `box` | shipped |
| `grid-auto` | shipped |
| `frame` | shipped |
| `cover` | shipped |
| `Layout::Sidebar` | shipped |
| `Layout::Switcher` | shipped |
| `cover > center > stack (single-focus recipe)` | shipped |

## How to re-run this

```bash
python3 scripts/build_coverage.py           # regenerate
python3 scripts/build_coverage.py --check   # CI-style staleness check
python3 scripts/build_coverage.py --audit   # what is unclassified right now
```

The corpora are **licensed references** (#89): gitignored, studied locally, never
redistributed. Only names, statuses and our own prose reach this file — no markup, class
list or asset is copied. Without the local corpora the builder **refuses to run** rather
than emitting a file that looks complete.

When a corpus is updated, re-run it. A new upstream directory that nobody has classified
**fails the build** and names itself, so coverage cannot silently rot. That failure is the
feature: it is the only reason this file can be trusted as a completeness claim.

Sources: Tailwind UI corpus directories; Flowbite catalogue read from
<https://flowbite.com/docs/> (Components, Forms, Typography) on 2026-07-29. Two names often
attributed to Flowbite are **not** in its catalogue and are deliberately absent here:
`Separator` (theirs is `HR`) and a cookie-consent component (none exists).

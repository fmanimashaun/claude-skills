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
| — `documented` | 69 |
| — `derivable` from documented parts | 44 |
| — `needs doctrine` (tracked writing gap) | 0 |

`Kind` is `primitive` · `component` · `composition` · `page archetype`. `In TW` / `In FB`
show which corpus carries the pattern — useful because the two are good at different things:
Tailwind UI wins on visual polish, Flowbite on interaction breadth.

## Documented — build straight from the reference entry

| Component | Kind | In TW | In FB | Where / when to use it | Watch out for |
|---|---|---|---|---|---|
| Accordion / Disclosure | component | — | ✓ | an authenticated app screen, inside one of the three shells | 732 instances in the audit corpus — the second most common interactive pattern after links. APG-verified contract (#142): what is required, and what is ours, is stated separately |
| Alert / Banner | component | ✓ | ✓ | in-page state (Alert) vs page-wide announcement (Banner) | — |
| Avatar | component | ✓ | ✓ | wherever a person is named; pair with the name, never alone as identification | — |
| Badge / Tag / Chip | component | ✓ | ✓ | status and category labels inside table rows, list items and headings | — |
| Breadcrumbs | component | ✓ | ✓ | detail screens more than one level deep, inside the page heading block | separators are aria-hidden markup, never ::after; truncates first → … → last two |
| Button | component | ✓ | ✓ | any action; `primary` once per view, `destructive` only behind a confirm | — |
| Button group | component | ✓ | ✓ | 2–5 related actions, or a single-select filter — `role=group` vs `radiogroup` | actions = role=group; single-select = role=radiogroup — different elements, not variants |
| Calendar / Date picker / Time picker | component | ✓ | ✓ | an authenticated app screen, inside one of the three shells | native first: the `type` fallback to a TEXT input is a spec guarantee, and there is NO APG date-picker pattern — two examples, two valid architectures |
| Card | component | ✓ | ✓ | a bounded surface in a dashboard grid, or a detail panel; also the stat-tile base | — |
| Carousel / Slider | component | — | ✓ | prefer not to — if a client insists, a marketing surface only | content behind a timed or manual slide is content most users never see, and the pattern is a persistent a11y liability. This is a doctrine position, not a backlog item — if a client insists, build it in the app against the a11y contract rather than blessing it as a kit primitive |
| Checkbox | component | ✓ | ✓ | independent booleans; multiples need a fieldset with a legend | — |
| Combobox / Autocomplete | component | ✓ | — | an authenticated app screen, inside one of the three shells | — |
| Copy to clipboard | component | — | ✓ | next to an API key, invite link or ID | the announcement IS the feature; a repeat needs the region cleared or it stays silent |
| Description list | component | ✓ | — | read-only attribute/value pairs on a detail or settings screen | blank values render an em dash + sr-only 'not set', never an empty <dd> |
| Drawer / off-canvas | component | ✓ | ✓ | an authenticated app screen, inside one of the three shells | ONE ROW, TWO CONTRACTS: the overlay drawer is a modal dialog and traps focus; the persistent push drawer is not a dialog and must not |
| Dropdown / Menu | component | ✓ | ✓ | overflow actions and scope pickers; not for navigation between pages | — |
| Empty state | component | ✓ | — | the zero-row branch of every index — required, not optional | — |
| File upload / Dropzone | component | — | ✓ | an authenticated app screen, inside one of the three shells | the native input stays VISIBLE — hiding it behind the dropzone fails WCAG 2.5.7 |
| Form layout | component | ✓ | — | every form — simple_form owns the field anatomy app-wide | simple_form owns every form; the wrapper anatomy is defined once in an initializer |
| Heading blocks (page / section / card) | component | ✓ | ✓ | the top of every page, section and card — the scale prop picks the level, so never style a heading down | one anatomy; scale is the only axis, so a card heading can never be an h2 styled small |
| Image gallery / Lightbox | component | — | ✓ | media-heavy surfaces: portfolio, product media, docs | focus trapping, keyboard paging and zoom are a large surface, and no current family has a media-heavy surface |
| Logo / Brand mark | component | — | — | shell headers, auth screens and marketing surfaces | ours, not from either corpus: clear-space 1.5×, min 20px / lockup 140px (brand.md) |
| Media object | component | ✓ | — | any avatar/icon + text row: list items, feeds, comments, notifications | never stacks — the side-by-side relationship IS the pattern |
| Mega menu / Flyout | component | ✓ | ✓ | a marketing surface (landing, pricing, about) — not app screens, which use the shell navigation | a DISCLOSURE, not a menu — APG advises against role=menu for site nav, so it shares no ARIA with the Dropdown row |
| Modal / Dialog | component | ✓ | ✓ | a focused create/edit/confirm step; never for content a page can hold | — |
| Navigation — header / navbar | component | ✓ | ✓ | the app's top bar in the stacked shell | — |
| Navigation — sidebar / vertical | component | ✓ | ✓ | the app's primary rail in the sidebar/multi-column shells | — |
| Pagination | component | ✓ | ✓ | any index over ~25 rows; pair with the Table | — |
| Progress bar | component | ✓ | ✓ | an authenticated app screen, inside one of the three shells | the Flowbite audit surfaced LABELLED progress bars specifically |
| Radio group | component | ✓ | ✓ | one choice from 2–5 visible options, in a fieldset | — |
| Range input | component | — | ✓ | an authenticated app screen, inside one of the three shells | native `input type=range` already IS role=slider; custom only for two thumbs |
| Reviews + Rating | component | ✓ | ✓ | a commerce surface (catalog, product, cart, checkout) | the governing criterion is 1.1.1 (A), NOT 1.4.1 — filled-vs-empty stars differ in shape, so 1.4.1 bites only where hue alone carries the distinction; read-only average and interactive picker are different contracts |
| Select | component | ✓ | ✓ | a closed set of ~2–10 options; above that reach for the combobox | — |
| Skeleton / loading placeholder | component | — | ✓ | a Turbo frame whose content size IS known — preferred over a spinner because it does not shift layout | Turbo frame loading states need this; without it agents invent spinners |
| Spinner / busy indicator | component | — | ✓ | a region whose content is loading and has no known size | — |
| Stepper / wizard | component | — | ✓ | a multi-step flow: checkout, onboarding, long forms | a display, not a widget: no tablist, no progressbar, no arrow keys. Move focus on advance and then do NOT add a live region — 4.1.3 excludes what a change of context already announced. Also feeds #91's checkout flow, which is inside 3.3.4 (AA) |
| Table (CRUD) | component | ✓ | ✓ | the index of a resource — sortable headers, row actions, select-all | — |
| Tabs | component | ✓ | ✓ | switching views of the SAME resource; never as page navigation | — |
| Text input | component | ✓ | ✓ | single-line entry; the shipped wrapper supplies label, hint and error | floating label is a variant, not a component |
| Textarea | component | ✓ | ✓ | multi-line entry; set rows, never a fixed pixel height | — |
| Toast / Notification | component | ✓ | ✓ | transient confirmation of a completed action; never for errors requiring a decision | — |
| Toggle / Switch | component | ✓ | ✓ | a setting that applies immediately; if it needs Save, use a Checkbox | — |
| Tooltip / Popover | component | — | ✓ | a supplementary label (Tooltip) or a small rich panel (Popover); never the only place information appears | — |
| Video player | component | — | ✓ | marketing and docs surfaces; inside a `frame` so layout never shifts | no APG pattern, so the keyboard model is the UA's and not ours; `kind=captions` is not `kind=subtitles`; and an autoplaying video is governed by WCAG 2.2.2 (A), not by reduced-motion |
| Stat tile | composition | ✓ | — | the metric row at the top of a dashboard, one metric per Card | page-anatomies composes these from Card, one metric each — deliberately not a new component |
| About page archetype | page archetype | ✓ | — | a whole marketing or auth page; compose sections inside it | — |
| Auth page archetype (sign-in / sign-up / reset) | page archetype | ✓ | — | a whole app screen | uses the cover > center > stack recipe for true vertical centering, not bare center |
| Cart page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Category page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Checkout page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Detail anatomy | page archetype | ✓ | — | a single record with attributes and actions | — |
| Error page archetype (404/500) | page archetype | ✓ | — | a whole marketing or auth page; compose sections inside it | an intentional error-page DESIGN — it returns 200 and is a legitimate page under test (qa-flow #106) |
| Home / dashboard anatomy | page archetype | ✓ | — | the landing screen after sign-in | — |
| Landing page archetype | page archetype | ✓ | — | a whole marketing or auth page; compose sections inside it | — |
| Multi-column shell | page archetype | ✓ | — | screens needing a contextual aside beside the main region | — |
| Order detail page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Order history page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Pricing page archetype | page archetype | ✓ | — | a whole marketing or auth page; compose sections inside it | — |
| Product page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Settings anatomy | page archetype | ✓ | — | grouped preference forms | — |
| Sidebar shell | page archetype | ✓ | — | authenticated app screens with a persistent rail | — |
| Stacked shell | page archetype | ✓ | — | authenticated screens with few top-level areas, or marketing-adjacent app pages | — |
| Storefront page archetype | page archetype | ✓ | — | a whole commerce page; compose the blocks inside it | — |
| Center / container | primitive | ✓ | — | the outer wrapper of page content, capping it at the measure | — |
| Divider | primitive | ✓ | ✓ | between unrelated blocks; inside a list use `divide-y` on the container instead | an <hr> is already role=separator; in lists the answer is divide-y on the container |
| Frame (aspect-ratio media) | primitive | — | ✓ | every image or video, so layout never shifts on load | — |
| Inline link | primitive | — | ✓ | body copy and prose; for actions use the Button `link` variant | the Button `link` variant is NOT this — it has no underline at rest, and dark-mode `--primary` is 2.59:1 against body text, under G183's 3:1, so colour cannot carry it. The 3:1 figure is technique G183, not SC 1.4.1 itself; 2.5.8 exempts links inside a sentence |
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
| Command palette | component | ✓ | — | the documented Modal containing the documented Combobox with a listbox popup; keep `aria-activedescendant` so typing keeps filtering | an authenticated app screen, inside one of the three shells |
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

**None — every row above is `documented` or `derivable`.** No component in either corpus
now requires an agent to invent an a11y or interaction contract.

This section is not deleted, because the status still exists and the next unclassified
upstream component may well land here. An empty table would have been worse than this
sentence: it would print guidance for rows that are not there.

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

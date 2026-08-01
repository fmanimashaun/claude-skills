# Component Catalog

Each component is a **ViewComponent** composing layout primitives + **semantic role tokens**,
with a fixed **variant × size × state** vocabulary. Reuse the SAME axes everywhere: sizes
`sm | md | lg` (+ `icon` for buttons); state via attributes (`disabled`, `aria-invalid`,
`data-state`, `aria-expanded`), never bespoke classes. Every component carries the a11y +
responsive rules listed. Class strings below use role tokens only — copy the recipe, don't
substitute raw colors.

## The focus ring: `outline-hidden`, never `outline-none` (Tailwind v4)

**Every focus recipe in this kit is `focus-visible:outline-hidden focus-visible:ring-2 …`, and the
first half is not interchangeable with `outline-none`.** Writing `outline-none` in a v4 project
removes the focus indicator entirely for forced-colors users. The reason is a rename that changed
behaviour under a stable name:

- Tailwind **v3**'s `outline-none` *"didn't actually set `outline-style: none`, and instead set an
  invisible outline that would still show up in forced colors mode **for accessibility
  reasons**"* ([v4 upgrade guide][tw4]). It was the safe utility.
- Tailwind **v4** renamed that to **`outline-hidden`** and introduced a *new* `outline-none` that
  *"actually sets `outline-style: none`"* ([v4 upgrade guide][tw4]). Same string, opposite meaning.

The ring cannot cover for it. Tailwind's rings are **box-shadow**, and in forced-colors mode
*"`box-shadow` and `text-shadow` compute to `none`"* ([CSS Color Adjust 1][cca]) — while
`outline-color` is force-adjusted to a system color rather than removed. So the outline is the part
that survives, which is precisely why v3's utility kept an invisible one. `outline-none` + `ring-2`
in v4 leaves a forced-colors user with **no visible focus indicator at all** — a WCAG **2.4.7**
failure that is invisible in normal rendering and therefore never caught by eye.

This shipped wrong in nine recipes across four files: the strings were correct under v3 and were
carried through the v4 migration unchanged. When a framework renames a utility, grep the old name —
a rename that keeps the old spelling alive with new semantics is the dangerous kind.

[tw4]: https://tailwindcss.com/docs/upgrade-guide
[cca]: https://www.w3.org/TR/css-color-adjust-1/

Express variants server-side as a Ruby map (base + variants + sizes + defaults), the cva
pattern without the JS dep:

```ruby
# app/components/ui/button_component.rb (shape for every catalog component)
BASE = "inline-flex items-center justify-center gap-2 rounded-md text-step--1 font-medium " \
       "transition-colors duration-[180ms] ease-out " \
       "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2 " \
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
- **The `link` variant is a BUTTON that looks like a link** — an action in a toolbar, not a link in a
  sentence. For prose see [Inline link](#inline-link) below, which explains why its
  `hover:underline` is the wrong contract inside running text.

## Inline link
- **This row has a real APG pattern** — unusually, for this file. Purpose: *"A link widget provides an
  interactive reference to a resource. The target resource can be either external or local."* And it is
  emphatic about the element: *"Authors are strongly encouraged to use a native host language link
  element, such as an HTML `<A>` element with an `href` attribute … applying the `link` role to an
  element will not cause browsers to enhance the element with standard link behaviors … providing these
  features of the element is the author's responsibility."* **So: a real `<a href>`.** `role="link"` is
  for when you genuinely cannot have one, and it hands you the entire job.
- **Its keyboard table is two rows, and that is all of it**: *"Enter: Executes the link and moves focus
  to the link target"* and *"Shift + F10 (Optional): Opens a context menu for the link."* **APG says
  nothing about `Space`, and nothing about an `<a>` without `href`** — we looked. "Enter activates, Space
  does not" is real browser behaviour but it is **not in this pattern**, so never cite APG for it.
- **The 3:1 figure is a technique, not the criterion.** SC 1.4.1 Use of Color (**Level A**) reads only
  *"Color is not used as the only visual means of conveying information…"* — **no ratio, and no mention
  of links.** The 3:1 comes from **G183, a *Sufficient Technique***: *"a relative luminance (lightness)
  difference of 3:1 or greater with the text around can be used"*, plus *"visual highlights when the user
  hovers over each link."* Write "G183 recommends", **never** "WCAG requires 3:1" — a technique is one
  way to pass, not the bar.
  - **G183's own test names hover only** — *"Check that hovering over the link causes a visual
    enhancement."* Focus is a **separate** obligation (2.4.7), referenced by G183 only as an analogy. And
    G183 is explicit that the cue is not a substitute: *"Hover or focus style changes alone are not
    sufficient to meet the criterion."*
  - **A carve-out worth knowing and not using:** 1.4.1's Understanding says *"a hyperlink which has been
    styled to appear no different than neighboring static text would not fail this success criterion, as
    there would be no color differentiation."* An invisible link is outside 1.4.1 **entirely**. That is a
    gap in the criterion, not a licence — it still leaves 2.4.4 in play and is plainly bad. Never offer it
    as a defence.
- **Underline is a convention upstream, and a requirement here.** G183 offers *"such as an underline, a
  change in font style such as bold or italics, or an increase in font size"*, and G14/G182 are
  underline-free sufficient alternatives. So **no upstream mandates underline** — but **we do, at rest, in
  prose.** That is our decision, and the measurements below are why it is not merely taste.
- **Measured against our own tokens** (re-derivable from `foundations-tokens.md`; ratios are WCAG relative
  luminance):

  | mode | link | vs body text | vs `--background` | vs `--card` |
  |---|---|---|---|---|
  | light | `--primary` `#0072C4` | **3.66:1** ✓ clears G183's 3:1 | **4.74:1** ✓ clears 1.4.3 | 5.00:1 ✓ |
  | dark | `--primary` `#00A3FF` | **2.59:1** ✗ under G183's 3:1 | 6.30:1 ✓ | 5.21:1 ✓ |

  Light `--primary` was `#0077CC` and measured **4.42:1** against `--background` — under 1.4.3 (#304).
  It now points at `--color-fm-cerulean-700`, an accessible step; the brand mark keeps `#0077CC`,
  because a logo is not text. Re-derive any figure here with
  `python3 scripts/check_token_contrast.py`, which gates all ten role-token text pairs.

  Two consequences, and they are the practical content of this entry:
  1. **In dark mode the colour route is unavailable.** 2.59:1 against body text is below G183's 3:1, so
     colour cannot be the distinguisher and a **non-colour cue at rest is mandatory** — not stylistic.
     Since the cue must be there in dark mode anyway, it is there in both; one link recipe, not two.
  2. **In light mode an inline link on `--background` is 4.42:1 — below 1.4.3 Contrast (Minimum) (AA),
     which wants 4.5:1 for normal-size text.** It clears on `--card` (4.66:1). Body copy is never *large
     scale* (*"at least 18 point or 14 point bold"*, ≈24 px / ≈18.5 px at 1 pt = 1.333 px), so the 3:1
     large-text allowance never applies to it. **This is a token defect, not a usage rule** — tracked
     separately; do not work around it per-component.
- **So: prose links get `underline underline-offset-4`, not the Button `link` variant.** That variant is
  `text-primary underline-offset-4 hover:underline` — **no underline at rest**, i.e. exactly the
  colour-only-plus-hover shape G183 permits *only* at 3:1 against surrounding text, which dark mode misses.
  The variant stays right for a button styled as a link; it was never right inside a sentence, and this
  row's previous guidance ("the Button `link` variant's classes on an `<a>`") was pointing at it.
- **2.5.8 Target Size (Minimum) (AA) does NOT apply to a link in a sentence.** Its **Inline** exception:
  *"The target is in a sentence or its size is otherwise constrained by the line-height of non-target
  text"*, and the Understanding doc's worked example is literally this case — *"Links within paragraphs of
  text do not need to meet the 24 by 24 CSS pixels requirements, so the success criterion passes."*
  **Do not pad an inline link to 24 px**: it wrecks the line rhythm to satisfy a criterion that exempts it.
- **Link text: 2.4.4 is A, 2.4.9 is AAA — do not swap them.** 2.4.4 Link Purpose (In Context) (**A**):
  purpose determinable *"from the link text alone or from the link text together with its programmatically
  determined link context."* 2.4.9 Link Purpose (Link Only) is **AAA**, and the well-known *"click here"*
  failure (**F84**) is filed under **2.4.9**. So generic link text is a **named failure at AAA** and an
  ambiguity risk at A — it is wrong to claim it "fails AA".
- **Focus, at the right levels.** 2.4.7 Focus Visible **AA**. 2.4.11 Focus Not Obscured (Minimum) **AA**
  (new in 2.2) — *"the component is not entirely hidden due to author-created content"*, which sticky
  headers break. 1.4.11 **AA** carries the indicator's own contrast at 3:1: *"the visual focus indicator
  for a component must have sufficient contrast against the adjacent background."* **2.4.13 Focus
  Appearance is AAA**, not AA — its 2 px-perimeter / 3:1 rule is a target we aim at, never an obligation
  we claim to enforce.
- **a11y:** external links get a visible cue plus `sr-only` text, not `title`. Never `target="_blank"`
  without saying so in the accessible name.

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

## Video player
- **No APG pattern, and therefore no upstream keyboard model.** The index lists 30 patterns and none
  is a media player; the source repo's `content/patterns` directory has no media entry either. So
  anything presented as "the video player pattern" is somebody's convention, not a citation. Ours:
  **ship the native control set and inherit the UA's keyboard model rather than authoring one.**
- **`<video controls>` inside a `frame`** — and be honest about what `controls` buys. The HTML
  Standard is deliberately loose: the UA *"**should** expose a user interface"* including *"features
  to begin playback, pause playback, seek to an arbitrary position … change the volume, change the
  display of closed captions"*. A **should**, and the section specifies **no key bindings at all**.
  Space-to-play and arrows-to-seek are browser convention; never write them down as a contract.
- **Custom controls are the expensive path, and two AA criteria switch on the moment you take it.**
  Both exempt native chrome *by name*: **1.4.11 Non-text Contrast (AA)** carves out *"where the
  appearance of the component is determined by the user agent and not modified by the author"*, and
  **2.5.8 Target Size (Minimum) (AA)** carves out *"User Agent Control — the size of the target is
  determined by the user agent and is not modified by the author"*. Replace the chrome and you own
  **3:1** on every control and state and **24 × 24 CSS px** on every target — plus the whole keyboard
  model you just declined to inherit. Do it only when a requirement forces it.
- **Captions are Level A, and `captions` is not `subtitles`.** **1.2.2 Captions (Prerecorded)** is
  **Level A**: *"Captions are provided for all prerecorded audio content in synchronized media."* The
  element is `<track kind="captions">`, which the spec defines as covering *"sound effects, relevant
  musical cues, and other relevant audio information, suitable for when sound is unavailable or not
  clearly audible"*. `kind="subtitles"` is a **different track** — *"suitable for when the sound is
  available but not understood"* — so shipping subtitles where captions are owed fails 1.2.2.
- **Audio description is two criteria at two levels. Do not merge them.** **1.2.3 (Level A)** accepts
  *"an alternative for time-based media **or** audio description"* — a transcript passes. **1.2.5
  (Level AA)** removes that escape hatch: *"Audio description is provided for all prerecorded video
  content in synchronized media."* At AA a transcript is not enough, and the track is
  `<track kind="descriptions">` (*"Textual descriptions of the video component … Synthesized as
  audio"*). A **silent** clip is neither: that is **1.2.1 (A)**, wanting a text alternative or an
  audio track.
- **Autoplay is governed by 2.2.2 at Level A — that, not reduced-motion, is the rule.** A hero video
  starting on load is *"moving … information that (1) starts automatically, (2) lasts more than five
  seconds, and (3) is presented in parallel with other content"*, so it needs *"a mechanism for the
  user to pause, stop, or hide it"*. Understanding 2.2.2 names the case — *"Common examples include
  motion pictures, synchronized media presentations, animations"* — and scopes the trigger: *"'starts
  automatically' broadly refers to animations/updates that are not the direct result of a user's
  intentional activation"*. **A player the visitor presses play on is out of scope; a background loop
  is not.** If sound can play automatically past 3 s, **1.4.2 Audio Control (A)** applies on top and
  wants a pause/stop mechanism or volume control independent of the system's.
- **Three things here are ours, and each says so because none has an upstream.** (1) **Muted-by-default
  is our rule, not an exemption** — "autoplay is blocked unless muted" is UA policy, and the HTML
  Standard offers it only as an example of a policy a UA *could* adopt: *"an exception could be made
  to allow playback while muted."* Never state it as a guarantee. (2) **Reduced motion suppresses
  autoplay.** `prefers-reduced-motion` in Media Queries 5 says nothing about video, media or autoplay,
  and the nearest normative criterion — 2.3.3 — is **AAA and about interaction-triggered animation**,
  not this. We do it anyway: gate the autoplay inside `@media (prefers-reduced-motion: no-preference)`,
  the construction `motion.md` already prescribes. The 2.2.2 pause control stays visible either way —
  it is a Level A obligation, not a fallback for the reduce branch. (3) **The player carries an
  accessible name** (`aria-label`, or `aria-labelledby` pointing at its caption/heading); "Video" is
  not a name.
- **`frame` crops — set `--ratio`.** `layout-primitives.md` gives `frame > *` `object-fit: cover`, so
  a 4/3 source in the default 16/9 frame silently loses its edges. Also set `poster` so the frame is
  never blank, and `preload="metadata"` so a marketing page does not fetch the whole file.

## Dropdown / Menu
> **Scope: an application/action menu, NOT site navigation.** `role="menu"` is correct here — a "…"
> button opening Edit / Duplicate / Delete is exactly what the role is for. It is **wrong for a nav
> bar**, and APG says so in a callout on its own Menubar example: *"A pattern more suited for typical
> site navigation with expandable groups of links is the Disclosure Pattern… few sites need the
> additional keyboard functionality required to support the ARIA `menubar` and `menu` roles."* For
> navigation, use [Mega menu / Flyout](#mega-menu--flyout) below, which is a **disclosure** and shares
> none of this row's ARIA. The two look similar and are structurally opposite; that is why this note
> exists.

- `Ui::Dropdown` (trigger slot + items). `role="menu"`/`menuitem`; trigger `aria-haspopup="menu" aria-expanded
  aria-controls`. Panel `bg-popover text-popover-foreground rounded-md border border-border shadow-md
  divide-y divide-border`. Item types: link, button, checkbox, radio, header, divider.
- **Behavior:** `dropdown` controller built on the **list-navigation** + **dismissable-layer** + **anchored-position**
  mixins (roving tabindex, Esc/outside-click, placement). Style open state via `data-[state=open]`.

## Mega menu / Flyout
- **No APG pattern, and the governing material tells you NOT to reuse Dropdown.** The index lists 30
  patterns and none is a mega menu. What governs is the **Disclosure** pattern — specifically its
  *Disclosure Navigation Menu* and *Disclosure Navigation Menu with Top-Level Links* examples.
- **It is a disclosure, not a menu. No `role="menu"`, no `menuitem`, no `aria-haspopup`.** APG's own
  words: *"it does not use the WAI-ARIA `menu` role… Typical site navigation does not need all the
  keyboard interactions specified by the menu and menubar pattern."* Plain `<ul>`/`<li>`/`<a>` inside a
  panel a button expands. (APG also carries a *Navigation Menubar* example, and there is an open
  upstream proposal to **delete** it for this reason — do not take it as the endorsed route.)
- **A top-level item that must both navigate and expand is TWO elements, not one.** APG's hybrid
  example: *"each item contains a top-level link and an associated disclosure button."* The link
  navigates; the adjacent button carries `aria-expanded` + `aria-controls`. Do not make one element
  both — a link with `aria-expanded` is neither thing properly.
- **Keyboard: `Tab` and `Esc` are required; arrow keys are explicitly optional.** The example's own
  table marks arrows, `Home` and `End` **"(Optional)"** — Tab through the links is sufficient. `Esc`
  closes and **returns focus to the button**, and APG ties that to a WCAG obligation rather than taste:
  *"Implementing this Esc behavior is necessary to meet the WCAG 2.1 1.4.13: Content on Hover or Focus
  criterion."*
- **If it opens on hover, WCAG 1.4.13 Content on Hover or Focus (AA) applies in full** — all three:
  **dismissible** without moving pointer or focus, **hoverable** (the pointer can travel into the panel
  without it vanishing — so no gap between trigger and panel), and **persistent** until dismissed or no
  longer valid. A hover menu that closes when the pointer crosses a 4px gap fails *hoverable*, and it
  is the most common way this is got wrong.
- Panel `bg-popover text-popover-foreground rounded-md border border-border shadow-md`, laid out with
  `grid-auto`; columns are a `<ul>` each with a heading. Behavior: the **disclosure** mixin
  (`aria-expanded` + dismissable-layer), **not** the `dropdown` controller.

**Three things here are ours, and are labelled as ours rather than cited:**

- **Hover-intent delay.** Neither APG nor WCAG mentions one. Open on hover after ~120ms of intent and
  close after ~240ms, so a pointer crossing the nav does not flash every panel — a convention, not a
  requirement. Hover is an *enhancement*: the button must work on click and on `Enter`/`Space` first.
- **Column grouping.** APG's examples are single-column and say nothing about columns, `role="group"`,
  or headings. A heading element per column followed by a plain `<ul>` is enough; do not invent
  `aria-labelledby` group semantics and attribute them to APG. And **do not announce column or item
  counts** — no guidance exists for it, and it is noise.
- **What it becomes on a small viewport.** No upstream at all. Ours: the mega menu collapses into the
  mobile drawer's nested disclosure list — the same `aria-expanded` button per section, stacked, with no
  hover path. That reuses the drawer contract rather than inventing a second mobile nav.

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
- **a11y:** a real `<table>` with `<caption>` (`sr-only` if the heading above already names it) and
  `<th scope="col">` / `<th scope="row">` — without `scope` a screen reader cannot associate a cell
  with its header, and a `<div>` grid loses the table semantics entirely. Sortable headers carry
  `aria-sort` on the sorted column **only**. Row actions need names: an icon-only edit button is
  `aria-label`-ed with the row's subject, not "Edit".
- Keep the proven `shared/_crud_table`, `_crud_header`, `_crud_row_actions` partials, refactored to role
  tokens + components. `<table class="w-full text-step--1 text-left">`, header `text-step--1 uppercase
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
- **a11y:** the media is **decorative by default** — `alt=""` on a thumbnail whose meaning is already
  in the adjacent text, because "Photo of Ada Lovelace" beside the words "Ada Lovelace" is announced
  twice. Give it real `alt` only when it carries information the body does not. Responsive: the
  cluster wraps rather than shrinking the media below its fixed size.
- **Sizes** follow the media: `sm size-8 · md size-10 · lg size-12` (icon chips use the Card stat
  recipe's `rounded-md bg-primary/10 text-primary`).
- **a11y:** decorative media takes `alt=""`; meaningful media carries a real `alt`. If the whole object
  is a link, wrap once and keep the media inside that link rather than nesting two links to the same place.
- **Responsive:** never stacks — the side-by-side relationship *is* the pattern. If the body needs full
  width on a phone, it was a Card, not a media object.

## Reviews + Rating
- **Two different things in one row, and they have different contracts.** The **review list** is
  documented **Media object** rows in a `divide-y` container — avatar, author, date, body — and adds
  nothing new. The **rating** is the part with an a11y contract, and it splits again into a
  **read-only average** and an **interactive picker**. Do not give them the same markup.
- **No APG rating pattern.** The index lists 30 and none is a rating; `w3c/aria-practices`
  `content/patterns` has no `rating` directory. So nothing here is "per the APG".
- **The governing criterion is 1.1.1 Non-text Content (Level A), not 1.4.1.** This is worth being
  exact about, because the intuitive citation is the wrong one. 1.1.1: *"All non-text content that is
  presented to the user has a text alternative that serves the equivalent purpose."* A star row that
  encodes a value is **informational** non-text content, so it cannot claim the *"pure decoration"*
  exception — *"if non-text content is pure decoration … then it is implemented in a way that it can
  be ignored by assistive technology."* **A star row with no text alternative fails 1.1.1.**
- **1.4.1 Use of Color (A) applies only in a narrower case** — *"Color is not used as the only visual
  means of conveying information."* Filled-vs-empty stars differ in **shape**, and the Understanding
  document names shape as the *remedy* for 1.4.1 (*"Use information in addition to color, such as
  shape or text"*), not as something it regulates. So 1.4.1 bites **only when the filled/empty
  distinction is carried by hue alone** — gold vs grey stars of identical shape, a `1`–`5` scale
  coloured red-to-green. Then it applies in full. Cite 1.1.1 first and 1.4.1 conditionally; the
  reverse overstates one and misses the other.
- **Read-only average: `role="img"` plus an accessible name.** The ARIA spec makes this exact: an
  `img` is *"a container for a collection of elements that form an image"*, its characteristics are
  **`Children Presentational: True`** and **`Accessible Name Required: True`**, and *"authors **MUST**
  provide the element with an accessible name … using the `aria-label` or `aria-labelledby`
  attribute."* That is precisely the job — collapse five glyphs into one unit and name it once. Five
  separately-announced stars is the failure this prevents.
- **`<meter>` is also spec-conformant for a numeric average** — *"The `meter` element represents a
  scalar measurement within a known range, or a fractional value"* — and a 4.2-out-of-5 is exactly
  that. Two spec-honest routes; **we default to `role="img"`** so the average and the per-review value
  share one mechanism. Note the spec's own exclusions if you reach for it: *"The `meter` element should
  not be used to indicate progress (as in a progress bar)"*, and it *"does not represent a scalar value
  of arbitrary range … unless there is a known maximum value."*
- **Interactive picker: a radio group, and that is OUR decision.** There is **no upstream** naming a
  widget for a 1–5 star picker — neither Radio Group nor Slider mentions ratings, and no APG pattern
  covers it. We choose **Radio Group** because a rating is a discrete choice of one value from five
  named ones, which is Radio Group's stated purpose (*"a set of checkable buttons … where no more than
  one of the buttons can be checked at a time"*), and not Slider's continuous single-thumb range. Build
  it as a real `<fieldset>` of radios styled as stars, so it inherits that pattern's keyboard model
  (Tab into the group, arrows move **and** select, Space checks) for free. **Do not** attribute the
  choice to APG.
- **The accessible name string is ours too.** Nothing upstream prescribes wording — 1.1.1 requires *a*
  text alternative "that serves the equivalent purpose" and is silent on phrasing. Ours: **"4 out of 5
  stars"** for the average and **"Rate 4 out of 5 stars"** for each picker radio. Spelled out, because
  "4/5" and "★★★★☆" are read aloud badly, and because a consistent string is what makes a rating
  comparable across screens.
- **Half stars are a rounding of the label, never a new mechanism.** Render 4.2 however you like; the
  name says the real value. And the visible count **must** appear as text next to the stars — that is
  the review-list convention and it satisfies 1.1.1 without relying on the label at all.
- **Responsive:** the rating is a `cluster` and never wraps mid-row — set `flex-none` on it so a long
  author name cannot break the stars across two lines.

## Payment / card entry
- **The card fields are not yours to build.** Card number, expiry and security code are rendered by
  the payment provider — a hosted page you redirect to, or provider-owned iframe(s) you embed. What
  this entry specifies is the **container**: the label, the error region, the `md` field height
  (`h-9`, matching the input recipe) so a provider iframe lines up with the fields above and below it,
  and the ring tokens you hand the provider's stylesheet so a focused iframe field does not look
  foreign. There is no `Ui::CardNumberComponent`, and writing one is the defect.
- **Which integration you choose has a compliance consequence, and the intuitive answer is out of
  date.** PCI DSS v4.0.1's SAQ A — the January 2025 revision, in effect since **31 March 2025** —
  **removed** Requirements 6.4.3 and 11.6.1 (and 12.3.1) as SAQ A line items and replaced them with an
  eligibility criterion: *"The merchant has confirmed that their site is not susceptible to attacks
  from scripts that could affect the merchant's e-commerce system(s)."* Per PCI SSC **FAQ 1588** that
  criterion applies **only** to *"e-commerce merchants with a webpage that includes a TPSP's/payment
  processor's embedded payment page/form (for example, one or more inline frame(s) (iframes))"* and
  *"does not apply to e-commerce merchants with a webpage that redirects customers from the merchant's
  webpage to a TPSP/payment processor … or e-commerce merchants that fully outsource payment
  functions."* So **embed vs redirect is a UI decision that moves an obligation**, and an embedding
  merchant discharges it either by deploying the 6.4.3/11.6.1 techniques or by written confirmation
  from the provider. Quoting the current wording is the point: citing 6.4.3/11.6.1 *as SAQ A line
  items* has been wrong since 2025-03-31. **This is framing, not a compliance determination** — which
  SAQ you validate to is your acquirer's and QSA's call, not a design skill's.
- **Nothing card-shaped may touch your DOM, your params or your logs.** That is the whole reason the
  fields are the provider's. A "just for validation" mirror input, a Stimulus value holding the PAN,
  or an analytics listener on the payment container each undo the integration you chose.
- **`type="number"` is wrong for a card number, and the spec says why.** *"The type=number state is
  not appropriate for input that happens to only consist of numbers but isn't strictly speaking a
  number. For example, it would be inappropriate for credit card numbers or US postal codes."* Its
  test is whether a spinbox would make sense: *"Getting a credit card number wrong by 1 in the last
  digit isn't a minor mistake, it's as wrong as getting every digit incorrect."* `type="text"`, with
  `inputmode="numeric"` where the value really is all digits. The note names **postal codes** too, so
  it binds the address block you *do* own — but a postcode is alphanumeric in much of the world, so
  that one gets `type="text"` and **no** numeric `inputmode`.
- **The fields that ARE yours take autofill tokens.** Cardholder name is `cc-name`; your own billing
  block is `billing`-prefixed (`autocomplete="billing postal-code"`). The order is fixed by the HTML
  Standard and is not free-form: optionally a `section-*` token, then optionally `shipping` or
  `billing`, then optionally `home`/`work`/`mobile`/`fax`/`pager`, then the field name — in that
  order. `billing postal-code` is valid; `postal-code billing` is not.
- **1.3.5 Identify Input Purpose (AA) covers these, with two boundaries worth knowing.** The `cc-*`
  tokens (`cc-name`, `cc-number`, `cc-exp`, `cc-csc`, `cc-type`, …) *are* in WCAG's *Input Purposes
  for User Interface Components* list, so a cardholder-name field is in scope. But the SC is *"scoped
  to inputs collecting information about the user"* — H98 states it directly, and Understanding 1.3.5
  adds that *"an input field for information that is not about the user does not need to
  programmatically expose its purpose, even if that purpose is included in the Input Purposes
  list"*, naming `transaction-amount`. And **`one-time-code` is a valid HTML autofill token but is
  absent from WCAG's list** — put it on a 3-D Secure step because it makes the OS offer the SMS code,
  not because 1.3.5 asks for it.
- **The disable-on-submit half is already done, which is exactly why it is not the protection.** Turbo
  *"will set the 'submitter' element's disabled attribute when the submission begins, then remove the
  attribute after the submission ends"*; `data-turbo-submits-with` *"specifies text to display when
  submitting a form"* and is the labelled in-flight state, never a bare spinner. Both are client-side
  and both lose to a reloaded tab. **Only a server-side idempotency key makes a double-submit safe**,
  and that is the rule — the button state is feedback, not a guard.
- **A form that posts to the provider's hosted page must opt out of Turbo.** `data-turbo="false"`
  *"disables Turbo Drive on links and forms including descendants"*. Otherwise Turbo fetches the
  cross-origin payment page and cannot render it, and the user sees nothing happen.
- **a11y — you cannot label the provider's field from your page, and this is the part everyone gets
  wrong.** `<label for>` requires *"the ID of a labelable element **in the same tree** as the label
  element"*: a mount-point `<div>` is not labelable, and a control inside an `<iframe>` is a different
  tree, so neither `for` nor `aria-labelledby` reaches it. **The accessible name must be set inside
  the frame, through the provider's own label/placeholder option**; the visible caption in your page
  is then for sighted users and the `<iframe>` carries a `title`. A `<label for="card-element">`
  pointing at the mount div looks right, validates as nothing, and names no control. Errors from the
  provider go into **your** error region for the field, in text (3.3.1), never a colour change on the
  border alone.
- **Responsive:** one column, always — see the Checkout anatomy in
  [page-anatomies.md](page-anatomies.md#checkout--the-purchase-flow). A two-column payment block
  produces an ambiguous tab order across a boundary you do not control.

## Promo / discount code
- **No upstream at all.** APG has no coupon, promo or "apply code" pattern, so everything here is
  **ours** except the two HTML-spec lines, which say so.
- **It is a second submission next to one you already have, and that is the whole difficulty.** Two
  rules from the HTML Standard settle the shape. A nested `<form>` is invalid — the `form` element's
  content model is *"Flow content, but with no `form` element descendants"* — so the code field cannot
  simply get its own form inside the checkout form. And *"a form element's default button is the first
  submit button in tree order whose form owner is that form element"*, so an "Apply" button dropped
  into the checkout form **becomes its default button**: Enter in the email field then applies an
  empty code. Both failure modes are silent. **Ours: the code entry is its own `<form>`, a sibling of
  the checkout form, never a descendant** — the order summary is a separate region, so this costs
  nothing in layout and gives each form its own default button. Better still, put it on the **cart**,
  before a checkout form exists at all. What you must not do is make it a `type="button"` driven by
  Stimulus: that removes it as the default button and leaves Enter in the code field *placing the
  order*, which is the worst of the three.
- **The result must be announced, and the amount is the announcement.** A code that applies changes a
  total elsewhere on the page. Put `role="status"` on the summary total, not on the code field — the
  role carries polite **and** atomic, so the user hears "Total £42.00" rather than "42.00". Same
  mechanism as the cart total; do not add a second live region for the code field.
- **A rejected code is an input error, not a toast.** 3.3.1 Error Identification (A): *"If an input
  error is automatically detected, the item that is in error is identified and the error is described
  to the user in text."* The message belongs beside the field via the simple_form error slot. A toast
  is dismissible and unassociated, so it satisfies neither half.
- **Never clear the field on failure**, and never make the user retype a code that worked — 3.3.7
  Redundant Entry (A) is about the same information *"required to be entered again in the same
  process"*, and a code silently dropped between steps is exactly that.
- **Ours: no auto-apply on blur or on keystroke.** Applying a discount changes a financial total, so
  it is an explicit press. This is the same reasoning the Stepper entry gives for not auto-advancing,
  and it avoids 3.2.2 On Input rather than papering over it with an advisory.
- `cluster` of a labelled `text` input (`uppercase` styling only — never `text-transform` on the
  value you send) and a `secondary` Button. The label is visible; "Promo code" as a placeholder is the
  usual failure and disappears the moment anyone types.
- **Responsive:** the cluster wraps to two rows on a narrow viewport rather than shrinking the input
  below its `min-h-touch` height.

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
- **Scope vs the Stepper below.** A continuous bar showing overall wizard completion *is* this
  component, and `aria-valuetext="Step 2 of 5"` is the right way to label it. The **enumerated list of
  named steps** ("Cart → Shipping → Payment") is not — see [Stepper / wizard](#stepper--wizard).

## Stepper / wizard
- **No APG pattern, and unusually little upstream of any kind.** The index lists 30; "stepper",
  "wizard" and "multi-step" appear nowhere on it. Most of this entry is therefore **our decision,
  recorded on [#95](https://github.com/fmanimashaun/claude-skills/issues/95#issuecomment-5147018825)**,
  and every such line below says so. Only the cited lines are citable.
- **`aria-current="step"` on exactly one step.** This part *is* spec: ARIA's values table gives
  *"step — Represents the current step within a process"*, and *"Authors **SHOULD** only mark one
  element in a set of elements as current with `aria-current`."*
- **It is not a tablist, and ARIA is the reason.** *"Authors **SHOULD NOT** use the `aria-current`
  attribute as a substitute for `aria-selected` in widgets where `aria-selected` has the same meaning.
  For example, in a `tablist`, `aria-selected` is used on a `tab`."* Be straight about the limit of
  that: **APG contains no warning against reusing Tabs for wizard flows** — we looked, there is none.
  The position that a gated, ordered sequence is not *"layered sections of content"* you may select
  freely is **ours**.
- **It is not a `progressbar` either, and that is ours too.** ARIA scopes `progressbar` to *"tasks that
  take a long time"* and says *"it is always read-only"*; HTML says *"the `progress` element is the
  wrong element to use for something that is just a gauge, as opposed to task progress."* **Neither
  names steppers**, so neither settles it — but a step list whose completed entries are clickable is
  not read-only, so we decline both.
- **Markup: an `<ol>` always; `<nav aria-label="Progress">` only when the steps are really links.**
  Ours. An ordered sequence is an ordered list. The landmark is conditional because a stepper's future
  steps are usually not navigable, and a landmark whose contents lead nowhere is noise. (Breadcrumb's
  *"contained within a navigation landmark region"* is real but **not transferable** — a breadcrumb is
  a trail of links to ancestors.)
- **No widget keyboard model. Ours, and deliberately nothing.** There is no upstream keyboard table
  because there is no pattern. The indicator is a **display**: no roving tabindex, no arrow keys.
  Navigable completed steps are ordinary links in the page tab order; future steps are not focusable.
  WCAG asks only that the model be operable (2.1.1) and order-preserving (2.4.3) — an invented
  arrow-key contract satisfies neither better and surprises everyone.
- **Announce by moving focus, and then do NOT add a live region.** This is the part an implementer gets
  wrong twice. 4.1.3 Status Messages (**AA**) has a two-part test: the message must concern *"the
  progress of a process"* — a step change does — **and** must *"not [be] delivered via a change in
  context."* Moving focus **is** a change of context, and the Understanding document excludes it by
  name: *"Changes of context, by their nature, interrupt the user by taking focus … and so have already
  met the goal to alert the user."* **So: on advancing, move focus to the new step's heading** (ours,
  and it satisfies 2.4.3) — 4.1.3 then does not apply, and a live region on top would double-announce.
  A `role="status"` region is correct only in the other design, where the step changes without moving
  focus. **Pick one branch; never both.**
- **Never auto-advance on input.** 3.2.2 On Input (**Level A**): *"Changing the setting of any user
  interface component does not automatically cause a change of context unless the user has been advised
  of the behavior before using the component."* Advancing on a field change is exactly that. Ours: we
  do not auto-advance at all — advancing is an explicit button press, which avoids the class rather
  than papering over it with an advisory.
- **A checkout wizard is inside 3.3.4's scope, at Level AA.** 3.3.4 Error Prevention (Legal, Financial,
  Data) covers *"web pages that cause legal commitments or financial transactions for the user to occur,
  that modify or delete user-controllable data … or that submit user test responses"*, and requires at
  least one of **Reversible**, **Checked**, or **Confirmed**. A final review step before submit is the
  usual answer. Note the levels: **3.3.4 is AA; 3.3.6 Error Prevention (All) is AAA** and applies to any
  information submission — do not quote one at the other's level.
- Visually a `cluster` of numbered `Badge`s with connectors, or a `stack` on narrow viewports. Each step
  carries its number **and** its name as text; the state (done / current / upcoming) is never colour
  alone — a check glyph for done, `aria-current="step"` plus visible weight for current.

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
- **a11y:** the image is decorative (`alt=""`) wherever the name is adjacent; the initials chip is
  `aria-hidden` for the same reason. **The status dot must not be colour-alone** — it is state, and
  the catalog's own rule forbids colour-only state, so pair it with `sr-only` text ("Online") or
  `title`. A stacked group is a list: `<ul>` with `sr-only` names, and a `+3` overflow chip that
  says what it counts.

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
- **a11y:** wrap it in `<nav aria-label="Pagination">` — there is usually more than one landmark of
  that type on a list screen. **The active page must not be colour-alone**: `aria-current="page"`
  carries it, and `bg-primary/10 text-primary` is then the visual half rather than the whole signal.
  Prev/next chevrons are icon-only, so each needs an `sr-only` label, and a disabled edge is
  `aria-disabled` rather than removed, so the control does not move between pages.

## Empty state
- `cover > center > stack`: icon chip `size-16 rounded-full bg-muted`, title, `max-w-md` `text-muted-foreground`
  description, optional primary action (opens in the `modal` frame). One `Ui::EmptyState` component.
- **a11y:** the icon chip is decoration — `aria-hidden="true"`, never an `alt` describing it. The
  title is a real heading at the level the surrounding page implies, not a styled `<p>`; an empty
  state replaces content, so the outline must not lose a level. If it appears after a filter or
  search, announce it — the region gets `aria-live="polite"`, or the user filters into silence.

## Forms
See [forms.md](forms.md).

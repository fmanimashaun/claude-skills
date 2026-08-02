# Interaction (Hotwire / Stimulus)

Behavior is Hotwire, not a JS component framework. Interactive components style themselves
off attributes their Stimulus controller toggles (`data-[state=…]`, `aria-*`); Tailwind v4's
`data-*`/`aria-*` variants make this declarative. Build behavior once as **four reusable
mixins**, then compose them — don't re-solve accessibility per component.

## The four reusable mixins (build once, reuse everywhere)

1. **list-navigation** (roving tabindex) — one focusable item at a time; ↑/↓ (or ←/→) move,
   Home/End jump, Enter activates. Shared by menu, tabs, listbox, radio-group, and the
   **select-only** combobox. Keeps `aria-activedescendant` when focus must stay in an input.
   - **`Space` and typeahead are NOT editable-combobox behaviours.** Neither appears in APG's
     normative Keyboard Interaction section for a combobox; both come from the *select-only*
     variant, where there is no text field for `Space` to type into. In an **editable** combobox
     `Space` types a space, and typed characters drive *filtering* rather than a
     typeahead-jump — a different mechanism. Applying the mixin wholesale to an editable
     combobox produces a control that swallows the space bar.
2. **focus-trap + restore** — on open, move focus in and cycle first/last on Tab; on close,
   **restore focus to the trigger**; mark the background **`inert`** and lock body scroll. Used by
   modal + drawer only (never trap outside a true modal).
   - **`inert` is the load-bearing part, not the Tab handler**, and it shipped missing from
     `focus_trap.js` for as long as `aria-modal="true"` shipped on the Modal. Tab-cycling confines
     *the tab sequence*; a virtual cursor, a rotor, a swipe, or a click still reach the background.
     ARIA 1.2 requires the interface be controllable using only the modal's descendants and warns
     that *"users of those technologies will experience severe negative ramifications if a dialog is
     marked modal but does not behave as a modal for other users."*
   - **`inert` alone — do not add `aria-hidden` beside it.** `inert` removes the subtree from the tab
     order, hit-testing **and** the accessibility tree in one attribute; adding `aria-hidden` is how a
     background ends up hidden from AT while still clickable.
   - **Restore only what you set.** The dismissable-layer is a stack, so overlays nest: an inner
     overlay closing must not un-inert what the outer one still needs, nor unlock body scroll under
     it.
3. **dismissable-layer** — Esc + outside-click close, maintained as a **stack** so nested
   overlays close top-first. Used by dropdown, popover, tooltip, drawer, modal.
4. **anchored-position** — place a floating element relative to a trigger with collision
   flipping; prefer CSS anchor positioning where available, else a small JS positioner. Used by
   dropdown, popover, tooltip, combobox.

**None of the four is a *gesture* mixin, and when one is built it inherits a contract these do not
have.** A press or drag does not only end in a clean `pointerup` — there are **eight** ways it can be
abandoned (`pointercancel`, `lostpointercapture`, `pointerleave`, window `blur`, `visibilitychange`,
Escape, blur, move tolerance), and *"if a component can be mid-gesture, it registers a window `blur`
listener"* or it stays stuck in its pressed state the moment a user alt-tabs. Full contract, plus
`touch-action` by owned axis and the capture-versus-drop distinction, in
[motion.md](motion.md#6-every-gesture-can-be-abandoned-eight-ways).

## Per-component behavior contract

**Not every row here has an APG pattern**, and the heading used to imply otherwise. APG's index is 30
patterns: **Toast, Progress bar, Spinner, Skeleton, any date picker and any mega menu are not among them** — a date
picker is two *examples*, under Dialog and under Combobox. Rows without a pattern are
sourced to an ARIA *role* definition or composed from primitives, and each says which — an entire row
implying an authority that does not exist is the same defect class as citing a keybinding a spec never
mandated (#142).

| Component | Roles / ARIA | Keyboard | Mixins |
|---|---|---|---|
| Dropdown/Menu | trigger `aria-haspopup aria-expanded aria-controls`; `role=menu/menuitem` | Enter/Space/↓ open · ↑↓ · Home/End · type-ahead · Esc | list-nav + dismissable + anchored |
| Dialog/Modal | `role=dialog aria-modal aria-labelledby` | Esc close · Tab trapped | focus-trap + dismissable |
| Drawer (overlay) | as Dialog — no APG pattern of its own | Esc · Tab trapped | focus-trap + dismissable |
| Drawer (persistent / push) | **not a dialog** — see the contract below | none | none |
| Carousel | `role=region` **or** `group` + `aria-roledescription=carousel` | prev/next buttons | carousel |
| Mega menu / Flyout | **disclosure, NOT a menu** — `aria-expanded` + `aria-controls` on a button; no `role=menu`, no `aria-haspopup` | Tab · **Esc required** (WCAG 1.4.13) · arrows **optional** | disclosure + dismissable |
| Range / Slider | **native `input type=range` already IS `role=slider`** — adding the role or `aria-valuemin/max` is NOT RECOMMENDED | native: arrows · Home/End (**PgUp/PgDn optional**) | none |
| Slider, custom (multi-thumb only) | one `role=slider` **per thumb**, each with its own name + `aria-valuenow` | as above, per thumb | none — test on touch AT first |
| Date / Time input | native `input[type=date\|time]` — **"No corresponding role"** in ARIA in HTML | the platform picker's own | none |
| Date picker, custom | **no APG pattern**: Dialog **or** Combobox + `role=grid`; `aria-selected` = chosen, `aria-current="date"` = today | grid navigation; month/year heading is a live region | focus-trap + dismissable |
| Lightbox / gallery viewer | Dialog **containing** a Carousel | Esc · Tab trapped · prev/next | focus-trap + dismissable + carousel |
| Tabs | `role=tablist/tab/tabpanel` `aria-selected aria-controls`; the **panel** carries `aria-labelledby` back to its tab, and the tablist is named; see the contract below | ←→ · ↑↓ **only** when `aria-orientation=vertical` · Space/Enter when activation is manual · **Home/End are `(Optional)`** | list-nav |
| Tooltip | `role=tooltip` `aria-describedby` | show on focus+hover · Esc | anchored + dismissable |
| Popover | trigger `aria-expanded aria-controls` | Esc · focus moves in | anchored + dismissable + focus-trap(soft) |
| Combobox | input `role=combobox aria-expanded aria-controls` (**both** required); listbox popup `aria-activedescendant` | ↓ into list · ↑↓ in list · Enter · Esc | list-nav + anchored |
| Disclosure (collapse) | trigger `<button aria-expanded>` + `aria-controls`; panel `hidden` | Enter **and** Space toggle | disclosure |
| Accordion | as Disclosure, **plus** header button wrapped in a heading with `aria-level` | Enter/Space · Tab/Shift+Tab between headers | disclosure(group:) |
| Toast | `role=status` **or** `alert` — severity decides (below); no APG pattern, nearest is *Alert* | focusable dismiss | dismiss |
| Progress bar | `role=progressbar` — an ARIA role, not an APG pattern; see the contract below | none (not focusable) | — |
| Spinner / Skeleton | no role, no pattern — composed from `aria-busy` + a `status` region | none | — |

Non-negotiables: visible `focus-visible` ring meeting contrast; keyboard reaches everything
the mouse can; restore focus to the trigger on close; announce async changes via a live region.

### Drawer, Carousel and Lightbox — one dialog, one rotator, one composition of both (#95)

**APG has a pattern for the middle one only.** The index lists 30; **Carousel** and **Dialog (Modal)**
are both on it, **Drawer**, **Off-canvas**, **Lightbox** and **Gallery** are not. So the drawer borrows
the Dialog contract, the lightbox is the composition already precedented by the Command palette
(*documented Modal containing a documented X*), and neither may be cited as a pattern of its own.

#### The drawer's real fault line: modal or persistent — and it is not one contract

`coverage.md` used to say "the documented Modal, positioned to an edge — keep its focus trap" with no
qualifier, and applied to the wrong shape that is actively harmful.

- **Overlay drawer** (slides in over content, backdrop, dismissible) → **is** a modal dialog. Full
  Dialog contract: `role="dialog"`, `aria-modal="true"`, an accessible name via `aria-labelledby` or
  `aria-label`, **initial focus inside** (generally the first focusable element), **focus returns to the
  invoking element** on close, and **`Esc` closes** — APG lists Escape unconditionally.
- **Persistent / push drawer** (the ordinary Rails app sidebar: always visible at `lg`, pushes content,
  never dismisses) → **not a dialog at all, and it must NOT trap focus.** It is never overlaid and the
  background is never inert, so it fails APG's own definition of a dialog (*"a window overlaid on either
  the primary window or another dialog window"*). Give it `<nav>`/`role="navigation"` and no dialog
  semantics.
- **"A drawer must trap focus" is false as stated.** Trapping is what **modality** requires, not a
  property of being a drawer: ARIA 1.2 scopes *"authors SHOULD manage focus of modal dialogs"* to modal
  dialogs, with no equivalent for non-modal ones. Trap the overlay; never trap the persistent panel.
- **`aria-modal="true"` is conditional on behaviour, not decoration.** APG: mark a dialog modal only
  when code prevents all users interacting with outside content **and** styling obscures it. That is
  what the `inert` line in the focus-trap mixin above exists to make true.
- **The responsive case is two components, not one that changes role.** A panel that is a modal overlay
  at `sm` and permanent chrome at `lg` changes *which contract applies* at the breakpoint. Render the
  persistent `<nav>` at `lg` and the modal drawer below it; do not toggle `aria-modal` and a focus trap
  by media query.

#### Carousel — three variants, and most of the machinery is conditional

- **Container: `role="region"` OR `role="group"`** — APG sanctions both and says the choice *"depends on
  the information architecture of the page"*. Either way it carries
  **`aria-roledescription="carousel"`**. Writing "`role=group` is required" overclaims.
- **Slides: `role="group"` + `aria-roledescription="slide"`** — except in the **Tabbed** variant, where
  each slide takes **`role="tabpanel"` and NO `aria-roledescription`**: *"Each slide container has role
  tabpanel in lieu of group, and it does not have the aria-roledescription property."*
- **Three variants, not two.** **Basic** (prev/next, no picker) · **Tabbed** (adds a single tab stop
  implementing the Tabs pattern) · **Grouped** (adds individually-tabbable picker buttons — APG calls it
  *"the least friendly for keyboard users"*, so prefer Tabbed when you want a picker).
- **Prev/Next buttons are needed always. Everything else is conditional on auto-rotation.** *Only* if it
  auto-rotates does it need a **play/pause button**, **stop on keyboard focus entering**, and **stop on
  mouse hover**. A manually-advanced carousel needs none of the three — requiring them anyway is
  inventing work.
- **`Tab` is not scripted.** APG: *"Tab and Shift+Tab: Move focus through the interactive elements of the
  carousel as specified by the page tab sequence — scripting for Tab is not necessary."* Arrow keys
  belong to the Tabs pattern in the Tabbed variant, not to the slides.
- **Inactive slides must leave the accessibility tree — but `aria-hidden` is not the named technique.**
  APG's Roles/States/Properties names no `aria-hidden` requirement; its reference implementation uses
  **`display: none`**. What the pattern actually warns against is a slide *"incorrectly hidden, e.g.,
  displayed off-screen"* — moved out of the viewport while still in the tree. So: remove it with
  `display:none`, `hidden`, or `inert`. Do not claim the spec mandates `aria-hidden`, and never
  "hide" a slide by translating it off-screen.
- **Auto-rotation is governed by WCAG 2.2.2 Pause, Stop, Hide (A)** — moving content that starts
  automatically, lasts over five seconds, and is presented in parallel with other content; technique
  **G186**, failure **F16**. **Not 2.3.3**, which is scoped to *"motion animation triggered by
  interaction"* (the same distinction the skeleton contract draws). Best default: **do not auto-rotate.**

#### Lightbox / image gallery — the composition, and where we decided rather than cited

A **Dialog (Modal)** containing a **Carousel**. Both contracts above apply unchanged, and the thumbnail
grid behind it becomes genuinely `inert`. Closing returns focus **to the thumbnail that was clicked**,
not to the grid — the Dialog rule is the *invoking element*.

- **The two patterns do not conflict, but that is inference, not a citation.** Carousel defers `Tab` to
  the page tab sequence and Dialog only changes where that sequence *wraps*, so reading both normative
  sections together they compose. No document states this about the combination, because no Lightbox
  pattern exists to state it — so it is recorded as reasoning, not quoted as a rule.
- **"A lightbox must be a dialog rather than a full-page navigation" has no upstream either way.** We use
  a dialog **by decision**, because it preserves the grid's scroll position and the user's place in it.
  Do not attribute that to a spec.
- **No auto-rotation, therefore no play/pause control** — which follows from the Carousel conditional
  above rather than from a lightbox rule.
- **The dialog's name string is ours too.** The pattern requires *a* name (`aria-labelledby` or
  `aria-label`); what it says is undocumented upstream. Use the image's own caption or alt text, so the
  name identifies the picture rather than announcing "Image viewer" over and over.

### Loading, progress and busy state (#95)

**None of these three has an APG pattern.** Progress bar has a normative ARIA *role*; Spinner and
Skeleton have neither role nor pattern and are compositions. Saying so is part of the contract.

**`progressbar` — every value attribute is optional, which surprises people.** There is no "Required
States and Properties" row for the role: `aria-valuemin` defaults to `0`, `aria-valuemax` to `100`.

- **Indeterminate means OMIT `aria-valuenow`** — not `0`, not `-1`: *"the author SHOULD omit the
  `aria-valuenow` attribute."*
- **An accessible name IS required**, and *Name From: author* — so `aria-label` or `aria-labelledby`
  only. It cannot come from the element's text.
- **It is a leaf.** *"Children Presentational: True"* — the inner fill `<div>` is not exposed, so never
  put the percentage text inside it and expect it read; use `aria-valuetext` or a sibling.
- **Never use `meter` for progress.** The difference is not stylistic: `meter` **requires**
  `aria-valuenow` where `progressbar` treats it as optional, and both ARIA and APG say *"authors SHOULD
  NOT use the `meter` role to indicate progress."* `meter` is a static measurement (disk usage); a
  progressbar is a task advancing.
- **Do not announce every increment.** WCAG's own example describes *"intermittent announcements"*, and
  `aria-busy` on the region is the spec's batching tool. The specific cadence — every 10%, every two
  seconds — is **our** convention, not a spec figure, so do not cite one for it.

**Announcing the state — `role="status"`, not bare `aria-live`.** `role="status"` carries an implicit
`aria-live="polite"` **and** an implicit `aria-atomic="true"`. Bare `aria-live="polite"` leaves
`aria-atomic` at **false**, and then *"assistive technologies will only present the changed node"* — so
"Total £52.00" announces as "52.00". Use the role.

**The one exception: a persistent, empty *container* that receives insertions.** The toast container
(`<div id="toasts" aria-live="polite">`) is correct as bare `aria-live`, because `aria-atomic="false"`
is exactly what you want there — atomic would re-announce every toast already on screen. The rule above
is about a region whose **own text changes**; this is a region whose **children are inserted**.

**Where the sources stop, and we do not fill the gap.** MDN describes the pattern as `aria-live` on an
**empty** element that is then updated — which is why the container is persistent and in the layout. What
no source we could find states either way is whether inserting an element that *itself* carries
`role="status"` is announced on its own. So doctrine does not rely on it: the container is always
present, and the toast's role is there to express **severity**, not to be the live region. Do not
"simplify" this by deleting the container's `aria-live` on the strength of the toast having a role — that
would be an unverified negative doing load-bearing work.

**`role="alert"` is for severity, not for loading.** It is implicitly *assertive* and interrupts. A
confirmation ("Copied", "Item added") is `status`; a time-critical failure ("Payment failed", "Session
expiring") is `alert`. That is the whole decision rule, and offering both without it — as this file did
— leaves the choice to guesswork.

**WCAG 4.1.3 Status Messages (AA) covers this explicitly**, and unusually the citation is safe: the SC's
own definition names *"the waiting state of an application"* and *"the progress of a process"*. Cite it.

**Skeleton: hide the shimmer, announce once.** `aria-hidden="true"` on the placeholder shapes plus a
single `role="status"` message ("Loading invoices…"), and `aria-busy="true"` on the region until content
arrives. Announcing forty placeholder rectangles is worse than announcing nothing.

- **`aria-busy` must never be the only mechanism.** It is optional and advisory — *"assistive
  technologies **MAY** want to wait"* — and support is poor in practice. `aria-hidden` on the shapes is
  what actually does the work; `aria-busy` is the correct signal layered on top.
- **No W3C source covers skeletons at all.** This shape is sound practitioner convention, not spec — and
  doctrine says so rather than implying otherwise.
- **Shimmer and reduced motion: the SC is 2.2.2 Pause/Stop/Hide (A), not 2.3.3.** 2.3.3 covers animation
  from *interaction*; a skeleton starts on load. And 2.2.2 is **conditional** — more than five seconds
  *and* presented in parallel with other content — so a fast skeleton, or one that is the only thing on
  the page, may not trigger it at all. Respect `prefers-reduced-motion` anyway, but know it is not among
  WCAG's named techniques for that SC.

**Spinner: a spinner is not a progress bar.** If nothing is known about duration it is an indeterminate
busy state, so `role="status"` with a text message beats `role="progressbar"` with no value — the role
promises a value it cannot supply. Reserve `progressbar` for when you genuinely know the proportion.

### Combobox — the two corrections that matter, and a version trap (#229)

**`aria-controls` is required, not decorative.** ARIA 1.2 lists exactly **two** required states for
the `combobox` role and this is one of them: *"Authors **MUST** set `aria-controls` on a combobox
element to a value that refers to the combobox popup element."* Our behaviour table shipped with only
`aria-expanded` while `forms.md` had both — two files contradicting each other on load-bearing wiring.

**Both focus models are sanctioned.** ARIA 1.2 presents moving real DOM focus into the popup as the
base case and `aria-activedescendant` as an alternative *"in lieu of"* it. We default to
`aria-activedescendant` for a listbox popup — focus stays in the input so typing keeps filtering — but
it is not the only conformant way, and for a **dialog** popup it is *disallowed*: APG, *"Unlike other
combobox popups, dialogs do not support `aria-activedescendant` so DOM focus moves into the dialog."*

**Keyboard: required and optional are mixed, so do not present them as one list.** `↓` from the input
into the popup, `↑`/`↓` within a listbox popup, `Enter`, and `Esc`-dismisses are **required**. `↑` from
the input jumping to the last item, `Alt+↓`/`Alt+↑`, `Home`/`End` in a listbox or grid popup, and
`PageUp`/`PageDown` (grid only) are **optional** — `PageUp`/`PageDown` are not in the listbox-popup
section at all. `Home`/`End` are required only for a **tree** popup.

**`→`/`←` inside an editable combobox move the text cursor**, they do not navigate options: *"Right
Arrow: If the combobox is editable, returns focus to the combobox without closing the popup and moves
the input cursor one character to the right."* Treating all four arrows as list navigation is
non-conformant for an editable combobox.

**Version trap — three models, not two.** ARIA 1.0 referenced the popup with `aria-owns`; ARIA 1.1
required a **non-focusable wrapper** owning a textbox plus popup; **ARIA 1.2 (current)** puts
`role="combobox"` on the input itself with `aria-controls`. ARIA 1.2 says plainly that *"a combobox
following the ARIA 1.1 combobox specification will no longer conform with the ARIA specification."*
Our doctrine is on the current model — a wrapper `<div role="combobox">` with `aria-owns` is the
superseded one, so do not "correct" it back from an older tutorial.

### Disclosure — the full contract (#142)

Disclosure is the **second most common interactive pattern after plain links** — 732 instances
across a 72-page professional corpus, outnumbering dropdowns 73:1 and tabs 81:1. It had one word
in this table (`(toggle)`) while rarer patterns had full treatments, so it is specified here.

**Two modes, and deliberately not a third.** Independent collapse (several panels may be open)
and **single-open collapsible** (opening one closes its siblings; all may be closed). APG
sanctions a third — *always one expanded* — which we **do not ship**: it prevents the user
collapsing everything, which is hostile in the FAQ and settings contexts this pattern serves,
and it is the only variant needing `aria-disabled` on the open header. Excluding it removes an
API branch and a failure mode. That is our decision, not a spec constraint.

**Required, per APG — stated plainly because these carry no qualifier:**

| Requirement | Where it applies |
|---|---|
| trigger has `role=button` and `aria-expanded` reflecting state | both modes |
| **`Enter` and `Space`** both activate | both modes |
| `Tab` / `Shift+Tab` reach each header in normal order | accordion |
| header button **wrapped in a heading element** with an appropriate `aria-level` | accordion |
| the heading contains **only** the button — a badge or menu-button beside it sits *outside* the heading | accordion |

`aria-level` is required whenever a non-native heading is used (`div role="heading"`); a native
`h2`–`h6` supplies it implicitly.

**`aria-controls` is recommended, not required.** APG marks it "Optionally", but ARIA 1.2 says the
author **SHOULD** use it when the panel is not *owned* by the trigger — which is exactly our
markup, since trigger and panel are siblings. So we emit it by default and cite ARIA, not APG.

**State and hiding are two separate obligations.** `aria-expanded="false"` does **not** remove the
panel from the accessibility tree — ARIA 1.2's MUST-exclude list covers `display:none`,
`visibility:hidden` and the HTML `hidden` attribute, and `aria-expanded` is not on it. So a
collapsed panel carries `hidden` (the technique APG's own reference implementation uses) *as well
as* the trigger's `aria-expanded="false"`. Setting only the ARIA state leaves collapsed content
readable by a screen reader and reachable by Tab.

**`role="region"` on the panel is optional, with a real threshold.** APG: *"Avoid using the
`region` role in circumstances that create landmark region proliferation, e.g., in an accordion
that contains more than approximately **6 panels** that can be expanded at the same time."* So
emit `role="region"` + `aria-labelledby` for small accordions, and **not** past ~6
simultaneously-expandable panels. A template that always emits it is wrong for large accordions.

**Arrow keys are ours, not APG's.** `ArrowUp`/`ArrowDown`/`Home`/`End` between headers are **not
in the current APG Accordion pattern** — they appeared in a 2017 APG 1.1 *example* and were
removed. Offer them if you like, as a documented enhancement borrowed loosely from Tabs; never
describe them as required by APG, and never let focus movement be the *only* way to operate the
control.

**Reduced motion — an implementation-correctness rule, not a WCAG citation.** Height transitions
respect `prefers-reduced-motion`, and **the state change must never depend on an animation event
firing**: gating `hidden`/`aria-expanded` on `animationend` breaks the control outright when the
animation is suppressed, because the event never arrives. That is a functional failure (4.1.2 /
2.1.1), not a motion issue — SC 2.3.3 only requires that animation *can be disabled* and says
nothing about the end state.

**Deep links.** If the URL fragment targets a collapsed panel, open it on load before scrolling,
or the browser scrolls to a `hidden` element and lands nowhere.

**`<details>`/`<summary>` — a genuine option, with two constraints.** It is *not* an APG-endorsed
implementation of this pattern (APG's Disclosure page never mentions it), and it has **no built-in
way to animate open/close**, so it cannot host the transition above. Use it for simple, static,
unanimated disclosure where the cheapness is worth it; reach for the controller otherwise.
Practitioners also document inconsistent screen-reader state announcement across readers —
enough to know the gaps exist, not enough to pin one.

### Tabs — the optional rows, the forbidden one, and manual activation (#95)

Tabs **is** an APG pattern, which makes it the opposite risk from Disclosure above: the temptation is
not to invent keys but to ship the whole table as required when the pattern marks part of it
`(Optional)`. The catalog entry ([components.md → Tabs](components.md#tabs)) carries the role wiring;
this is the behaviour.

**Required — no qualifier on any of these:**

| Requirement | Verbatim |
|---|---|
| `Tab` into the list lands on the **active** tab, not the first | *"When focus moves into the tab list, places focus on the active tab element."* |
| `Tab` out goes to the panel | *"…moves focus to the next element in the page tab sequence outside the tablist, which is the tabpanel unless the first element containing meaningful content inside the tabpanel is focusable."* |
| ←/→ move between tabs (horizontal) | *"Left Arrow: moves focus to the previous tab"* / *"Right Arrow: Moves focus to the next tab"* |
| ↓/↑ **only** when `aria-orientation="vertical"` | *"When a tab list has its aria-orientation set to vertical: Down Arrow performs as Right Arrow is described above."* |
| `Space` or `Enter` activate under manual activation | *"Space or Enter: Activates the tab if it was not activated automatically on focus."* |

**A horizontal tablist must NOT listen for ↑/↓ — this is the row implementations get wrong**, because
binding all four arrows feels more helpful. APG says the opposite, and gives the reason: *"If the tab
list is horizontal, it does not listen for Down Arrow or Up Arrow so those keys can provide their
normal browser scrolling functions even when focus is inside the tab list."* A tablist that eats ↓
traps a keyboard user who is trying to scroll the page.

**Optional — ship them if you like, never write them down as required.** `Home` and `End` are each
marked `(Optional)` in the pattern's own table, as is `Delete` (*"If deletion is allowed, deletes
(closes) the current tab element…"*, with a context-menu alternative). **There is no `Ctrl+Delete`**:
it is absent from the current pattern *and* from the 2017 APG 1.1 snapshot — the same vintage that
produced #142's phantom accordion keys, checked for exactly that reason.

**Two rows nobody remembers exist**, both conditional on the tab having a popup menu: `Shift + F10`
*"If the tab has an associated popup menu, opens the menu"*, and correspondingly *"If a tab element
has a popup menu, it has the property aria-haspopup set to either menu or true."* Omit both when
there is no menu — do not emit `aria-haspopup` unconditionally.

**Automatic vs manual activation — and in a Hotwire app the answer is usually manual.** APG
recommends automatic, *conditionally*, and the condition is the whole point: *"It is recommended that
tabs activate automatically when they receive focus as long as their associated tab panels are
displayed without noticeable latency. This typically requires tab panel content to be preloaded."*
**A panel that is a lazy `<turbo-frame>` is by definition not preloaded**, so arrowing across five
tabs would fire five requests and stall focus movement on each. Ours, inferred from APG's own
precondition rather than stated by it: **panels rendered inline → automatic; panels behind a lazy
frame → manual**, and the controller reads which from the markup rather than guessing.

**Roving tabindex, not `aria-activedescendant`.** Both are generic composite-widget strategies in
APG's keyboard practice, but the Tabs pattern and both of its reference examples implement only the
first, and note that a `<button>` tab needs no explicit `tabindex="0"`: *"Since an HTML button element
is used for the tab, it is not necessary to set tabindex="0" on the selected (active) tab element."*
Writing it anyway is harmless; citing `aria-activedescendant` as this pattern's recommendation is not.

## Controller conventions (mirror the markup ergonomics)

Expose `data-controller` / `data-action` / `data-<name>-target` so markup reads close to a
declarative component and porting HTML examples is easy. Style state off attributes:

```erb
<button data-controller="dropdown" data-action="click->dropdown#toggle"
        aria-haspopup="menu" aria-expanded="false" aria-controls="menu-1"
        class="… aria-expanded:bg-accent">Actions</button>
<div id="menu-1" role="menu" data-dropdown-target="menu"
     class="hidden data-[state=open]:block bg-popover border border-border rounded-md shadow-md">…</div>
```

Reuse the proven controllers already in the apps: `modal`, `dropdown`, `tabs`, `sidebar`,
`theme` (dark toggle + localStorage), `toast`, `search` (debounced), `multistep`,
`form_validation`, `countdown`. Refactor them onto the four mixins so behavior is consistent.

**Everything else the reference docs prescribe by name, you will have to write** — and this list is
the whole of it, so a component that needs a controller not below is a component whose behavior
nobody has specified yet:

| controller | drives | composes |
|---|---|---|
| `dismiss` | Alert, Toast | dismissable-layer |
| `disclosure` | Accordion, mobile nav, filter groups | — (the contract is in this file, #142) |
| `combobox` | Combobox / Autocomplete, and the Command palette inside `modal` | list-navigation + anchored-position |
| `tooltip` | Tooltip / Popover | dismissable-layer + anchored-position |
| `switch` | Toggle / Switch | — |
| `dropzone` | File upload | — (gesture; see the abandonment contract above) |
| `clipboard` | Copy to clipboard | — |
| `feed` | Activity feed, `role="feed"` shape only | — |
| `carousel` | Carousel, and the Lightbox inside `modal` | list-navigation |
| `payment-element` | Payment / card entry (the PSP's own element) | — |
| `native-bridge`, `bridge--button` | Hotwire Native surfaces (mobile.md) | — |

- **`sidebar` is collapse only — the overlay drawer is `modal`.** This entry used to read "`sidebar`
  (drawer + collapse)", conflating the two shapes the drawer contract above separates: the persistent
  panel is *not a dialog* and must not trap focus, while the overlay drawer is a modal dialog and must.
  One controller doing both is how a persistent sidebar acquires `aria-modal` and a focus trap it should
  never have. `sidebar` collapses and expands; `modal` (focus-trap + dismissable) drives the overlay,
  positioned to an edge.
- **`carousel`** — prev/next plus, *only if it auto-rotates*, play/pause and stop-on-hover/focus. The
  lightbox composes it inside `modal` rather than adding a controller of its own.
- **This bullet used to say `carousel` was "the only new controller the #95 rows need", and the docs
  around it already said otherwise (#95).** The shipped snippets prescribe `dropzone` and `clipboard`
  in forms.md, and `combobox`, `disclosure` and `feed` in component-implementations.md — five more
  controllers for #95 rows alone, every one of them named in markup a reader is told to copy. Anyone
  who believed the sentence would have gone hunting for a mixin that covers drag-and-drop and found
  none, because **none of the four is a gesture mixin** (see the contract above). The table is now
  reconciled against every `data-controller=` the reference docs contain by
  `scripts/lint_self_consistency.py` (`controller-inventory-gap`), so the inventory cannot silently
  fall behind the markup again.

## Real-time & data (standardize)

- Prefer **Turbo Frames** for lazy-loading fragments (tables, sections, combobox results) and
  **Turbo Streams** for server-pushed updates (toasts, live lists). This is the default.
- Raw ActionCable in a Stimulus controller is the **justified exception**, and there is now a
  testable line rather than a judgement call: **Action Cable when the payload is a *fact*, not a
  *fragment*.** If the server knows what the DOM should become, it is a Turbo Stream; if the server
  has a fact and the *client* decides what it means, it is raw Action Cable JSON. Campfire's six
  channels are all on the second side — unread ids, read receipts, typing, presence, heartbeat —
  and none carries HTML. Full derivation, and the measurement behind it, in
  [hotwire's production.md](../../hotwire/references/production.md).
  - This entry used to read "allowed only for genuinely bespoke real-time… document why Streams
    didn't fit", which is the same rule at a vaguer precision. Superseded rather than duplicated:
    two statements of one rule at different sharpness is how a reader ends up citing the weaker.
    (Auctioneer uses raw ActionCable; fmworkflows uses a Turbo Stream responder.)
- `prefers-reduced-motion`: gate all transitions/animations; provide a no-motion path.

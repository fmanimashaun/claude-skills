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
   **restore focus to the trigger**; mark the background inert (`inert`/`aria-hidden`) and lock
   body scroll. Used by modal + drawer only (never trap outside a true modal).
3. **dismissable-layer** — Esc + outside-click close, maintained as a **stack** so nested
   overlays close top-first. Used by dropdown, popover, tooltip, drawer, modal.
4. **anchored-position** — place a floating element relative to a trigger with collision
   flipping; prefer CSS anchor positioning where available, else a small JS positioner. Used by
   dropdown, popover, tooltip, combobox.

## Per-component behavior contract

**Not every row here has an APG pattern**, and the heading used to imply otherwise. APG's index is 30
patterns: **Toast, Progress bar, Spinner and Skeleton are not among them.** Rows without a pattern are
sourced to an ARIA *role* definition or composed from primitives, and each says which — an entire row
implying an authority that does not exist is the same defect class as citing a keybinding a spec never
mandated (#142).

| Component | Roles / ARIA | Keyboard | Mixins |
|---|---|---|---|
| Dropdown/Menu | trigger `aria-haspopup aria-expanded aria-controls`; `role=menu/menuitem` | Enter/Space/↓ open · ↑↓ · Home/End · type-ahead · Esc | list-nav + dismissable + anchored |
| Dialog/Modal | `role=dialog aria-modal aria-labelledby` | Esc close · Tab trapped | focus-trap + dismissable |
| Drawer | as Dialog | Esc · Tab trapped | focus-trap + dismissable |
| Tabs | `role=tablist/tab/tabpanel` `aria-selected aria-controls` | ←→ (Home/End) | list-nav |
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

Reuse the proven controllers already in the apps: `modal`, `dropdown`, `tabs`, `sidebar`
(drawer + collapse), `theme` (dark toggle + localStorage), `toast`, `search` (debounced),
`multistep`, `form_validation`, `countdown`. Refactor them onto the four mixins so behavior is
consistent.

## Real-time & data (standardize)

- Prefer **Turbo Frames** for lazy-loading fragments (tables, sections, combobox results) and
  **Turbo Streams** for server-pushed updates (toasts, live lists). This is the default.
- Raw ActionCable in a Stimulus controller is allowed only for genuinely bespoke real-time
  (e.g. high-frequency bid/counter updates) — document why Streams didn't fit. (Auctioneer uses
  raw ActionCable; fmworkflows uses a Turbo Stream responder — the Stream path is the standard,
  ActionCable the justified exception.)
- `prefers-reduced-motion`: gate all transitions/animations; provide a no-motion path.

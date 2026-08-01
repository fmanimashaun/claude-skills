# Motion — named patterns, tokenised timing, reduced-motion by construction

Our motion doctrine was **one line**: *150–200ms `ease-out`, transition `colors/opacity/transform`
(never `all`), gated on `prefers-reduced-motion`*. That governs component state transitions and
nothing else — so scroll reveals, staggered entrances, drag feedback and marketing motion were
unspecified, and unspecified means invented per screen. Ad-hoc motion is worse than none:
inconsistent easing across sections reads as amateurish, and unguarded motion is an accessibility
failure.

**Source and attribution.** The principles below are adapted from **[interior][interior]**'s
[`DESIGN.md`][design] (MIT, © ddoemonn) — a micro-interaction design language written against React
and the `motion` library. **Attribute it** where a rule is lifted.

[interior]: https://github.com/ddoemonn/interior
[design]: https://github.com/ddoemonn/interior/blob/main/DESIGN.md

**What we take and what we cannot, stated up front.** Its *principles* are stack-independent and
mostly better than ours. Its *implementation* is not portable: the five named springs
(`CELL 520·34·0.45`, `SURFACE 420·36·0.9`, …) are constants for `motion`'s spring solver, and CSS has
no spring primitive. Anywhere below that a number is ours rather than theirs, it says so — an
adapted constant presented as a citation would be the worst of both.

---

## 1. Two curves, and a departure is always shorter than an arrival

This is the single highest-value rule here, and we had **no** version of it: our doctrine used one
easing and one duration range in both directions.

> *"A departure is always shorter than an arrival."*

Without it, a thing leaving and a thing arriving overlap — *"replacements either lag or smear
together"*. Concretely, from the source: enter **0.22s**, exit **0.18s**.

**Two curves, one for each direction.** We keep our shipped arrival curve rather than adopting
theirs — `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)` is already calibrated against our corpora and
theirs (`0.23, 1, 0.32, 1`) is the same family. What we lacked is the **departure** curve, which
mirrors it: fast out of frame rather than soft into place.

```css
@theme {
  /* arrival — decelerates into place. Already shipped; unchanged. */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  /* departure — accelerates away. NEW. Adapted from interior's LEAVE [0.4, 0, 1, 1]. */
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
}
```

**Never use one curve for both.** An element that leaves on the arrival curve hangs about; an element
that arrives on the departure curve snaps and reads as a jump.

**How these reach markup differs between the two, and getting it wrong means the class silently does
nothing.** `--ease-*` **is** a Tailwind v4 theme namespace: defining `--ease-in` generates an
`ease-in` utility, and because Tailwind ships its own `--ease-in`/`--ease-out` defaults, our
definitions **override** them — which is deliberate, and already true of the `--ease-out` we ship.
There is **no `--duration-*` namespace**: `duration-*` utilities take numbers or arbitrary values, so
our duration tokens are consumed either as `var(--duration-fast)` in CSS or with Tailwind's
custom-property syntax **`duration-(--duration-fast)`** in a class. Do not expect a `duration-fast`
class to exist.

## 2. Distance chooses the duration

> *"Over 200 pixels → DISCLOSE, 20–200 → CELL, under 20 → SMALL."*

Their mechanism is spring selection; ours is duration, because CSS has no springs. **The rule that
transfers is that travel distance, not component type, picks the timing** — a chip settling 8px and a
drawer crossing the screen must not share a duration.

| Travel | Duration token | Use |
|---|---|---|
| under 20px | `--duration-fast` **120ms** | chips, labels floating, icon nudges, focus rings |
| 20–200px | `--duration` **180ms** | rows, cells, thumbs, menu items — the default |
| over 200px | `--duration-slow` **280ms** | drawers, modals, anything crossing the viewport |

**The three durations are ours** — derived by holding our shipped 180ms as the mid tier and applying
their ratios. Their millisecond figures come from spring settling times and do not carry over.

**Exits take the tier below.** A 20–200px element leaves in **120ms**, not 180ms. That is rule 1
expressed in the table rather than left to judgement.

## 3. Scale never starts at zero

> *"Scale never starts at 0. It starts at 0.9 or 0.97."*
> *"Below about 0.9 it is visibly soft."*

*"Nothing in the physical world begins as a point."* Entrance from `scale(0)` reads as a cartoon;
entrance from **0.97** reads as arriving.

- **Enter:** `opacity 0 → 1`, `scale 0.97 → 1`, `translateY 10px → 0`
- **Exit:** `opacity → 0`, `scale → 0.98`, `translateY → 6px`

Exit moves **less** than entry — a smaller scale change and a shorter travel — which is what makes it
read as *settling away* rather than *appearing in reverse*.

**Transform origin is pinned to the edge the element came from.** A dropdown under its trigger grows
from `top`, not `center`.

**We drop the blur.** interior enters with `blur(6px)` and exits with `blur(3px)`. Animating `filter`
is expensive and, at our durations, buys little — this is **our** call, not a flaw in theirs.

**An entrance no longer needs JavaScript.** An element appearing from `display: none` — a popover, a
dialog, a Turbo-inserted row — could not be transitioned in CSS, which is why entrance animation used
to mean a controller toggling classes on the next frame. Two features fixed that:

- **`@starting-style`** supplies the values to transition *from* on an element's first style update;
- **`transition-behavior: allow-discrete`** makes discrete properties like `display` transitionable
  at all, which is what lets `display: none → block` participate.

```css
@media (prefers-reduced-motion: no-preference) {
  .popover {
    transition: opacity var(--duration) var(--ease-out),
                scale   var(--duration) var(--ease-out),
                display var(--duration) allow-discrete;
  }
  @starting-style {
    .popover:popover-open { opacity: 0; scale: 0.97; }
  }
}
```

**Version boundary, stated precisely because it is still moving.** This pair reached Baseline
**"Newly available" on 6 August 2024** (Firefox 129 closed the gap). It is *not* yet "widely
available" — that tier is 30 months on, i.e. **February 2027** — so treat a CSS-only entrance as a
progressive enhancement, not a floor. Without support the element simply appears, which is the
correct fallback.

## 4. On disclosure, opacity finishes before height

> *"Height and opacity get separate durations when disclosing."*
> Opacity **0.18s**, height **0.28s** — *"opacity finishing first hides the reflow."*

We ship a Disclosure component with a height transition and never said this. Content that fades out
before the container finishes collapsing hides the reflow; fade and collapse on the same clock and
the text visibly squashes.

```css
@media (prefers-reduced-motion: no-preference) {
  .disclosure-panel {
    transition:
      opacity var(--duration-fast) var(--ease-out),      /* finishes first */
      height  var(--duration-slow) var(--ease-out);
  }
}
```

## 5. Reduced motion: change the behaviour, not just the timing

Our doctrine said "gate transitions on `prefers-reduced-motion`". That is necessary and not
sufficient. The invariant to hold is theirs, and it is sharper:

> *"`prefers-reduced-motion` → the information still arrives, the trip is skipped."*

- **Never remove the element or the state change** — set the duration to zero. *"The element must
  still end up in the right place."* A transition that is skipped must still commit its end state.
- **Change behaviour where timing alone is not the problem:** `scroll-behavior: auto` instead of
  `smooth`; a text reveal **jumps to its final state** rather than typing; a marquee **stops
  looping** rather than looping faster.
- **Do not animate on mount** — the entrance is the trip, and the content is the information.

**We gate on `no-preference`, and that is our decision, not a rule anyone published.** Our CSS wraps
motion in `@media (prefers-reduced-motion: no-preference)` rather than overriding inside
`@media (prefers-reduced-motion: reduce)`. Worth being straight about: **MDN's own canonical example
and WebKit's own article both use the opposite direction**, and the Media Queries Level 5 spec makes
no authoring recommendation either way — it only defines the two values. We choose `no-preference`
because it **fails safe**: a user agent that does not support the media feature at all never matches
`no-preference`, so motion never activates, whereas the `reduce`-override direction leaves motion on
by default in exactly that case. Do not cite a spec for this; it is a reasoned default.

This is already load-bearing elsewhere in our doctrine: the **skeleton** shimmer and the **spinner**
both suppress under reduced motion, and `interaction-stimulus.md` requires that *a state change never
depend on an animation event firing* — because with motion suppressed the event never fires. That
rule and this one are the same rule seen from two directions.

**WCAG boundary, unchanged from the loading contract:** an auto-starting animation is governed by
**2.2.2 Pause, Stop, Hide** (A), conditional on running over five seconds *and* being presented in
parallel with other content. **2.3.3 Animation from Interactions** (AAA) covers motion triggered by
*interaction*. Respect the preference regardless; cite the right one.

## 6. Every gesture can be abandoned eight ways

The most transferable section in the source, and the one our four Stimulus mixins say **nothing**
about. A press or drag does not only end in a clean `pointerup`:

> `onPointerUp` · `onPointerCancel` · `onLostPointerCapture` · `onPointerLeave` (holds only) ·
> window `blur` · document `visibilitychange` · Escape `keydown` · `onBlur`

> **Non-negotiable: *"If a component can be mid-gesture, it registers a window `blur` listener."***

Alt-tab mid-press and the press never ends; the element stays stuck in its active state until
something else disturbs it. That is the bug this rule exists to prevent, and it is invisible in
testing because nobody alt-tabs during a click on purpose.

Three more from the same section:

- **Use `setPointerCapture()` on the element the gesture started on**, and treat
  `lostpointercapture` as a **cancel, not a drop** — the two are different outcomes.
- **`touch-action` is chosen by the axis you own:** `manipulation` for a button, `pan-y` for a
  horizontal drag, `none` for two-dimensional. Getting this wrong is how a drag fights the scroller.
- **Move tolerance before a press becomes a drag:** 8px for long-press, 10px for hold.
- *"Keyboard is not an afterthought; it is a second complete implementation."*

## 7. Cap the stagger

> *"The whole reveal fits maxDuration (1.6s)."*

A per-child delay multiplied by an unbounded list is a wait:

```
per-child delay × child count ≤ 1.6s      →      delay = min(preferred, 1.6s / count)
```

*"A stagger that scales with the data eventually becomes a wait."* Twelve cards at 80ms is pleasant;
sixty rows at 80ms is five seconds of the page assembling itself.

## 8. CSS transitions have exactly three jobs

> *"A CSS `transition-colors` on a cell driven by a gesture will always look flatter than a spring."*

Their split is spring-vs-transition. Ours is **transition-vs-nothing**, but the boundary lands in the
same place — a transition is for a *discrete state change*, never for something the user is currently
moving:

1. **Hover and focus tint** — `transition-colors` at 150ms.
2. **State changes on fields and buttons** — `border-color`, `box-shadow`, `background-color`, 150ms.
3. **Threshold crossings** — e.g. a strength meter changing colour, 200ms.

**Reject transition-based colour changes on anything the user is dragging.** While a pointer is down
the element must track the pointer, and a 150ms colour transition lags visibly behind it.

And the rule we already had, which survives unchanged: **transition named properties, never `all`**.

## 9. Physics runs linear; intention runs eased

> *"A ripple is a wave… travels at constant speed — so it expands **linearly**, not eased."*
> *"A spinner turns at one rate because it is reporting an unknown, a marquee moves at one rate
> because it is a belt."*

Easing communicates *intent* — something decided to move and settled. Constant rate communicates
*physics or ignorance*. Applying an ease to a spinner implies it knows how far along it is, which is
precisely the thing it is admitting it does not know. This matches the loading contract: a spinner is
for **unknown** duration, a progress bar for known.

> *"Research before inventing. A ripple, a spinner, a slider detent are solved, published, and
> measured."*

## 10. Focus: two signals, never three

> *"No focus rings. A 2px border plus the surface lifting is already two signals."*

Three focus shapes, chosen by the element's relationship to its container:

| Shape | When | What |
|---|---|---|
| **Inset** | a row or cell inside a container | `inset 0 0 0 1px` accent + a faint accent wash |
| **Border + lift** | a standalone control with room around it | accent border + a soft shadow |
| **Outside** | an element filling its frame | `0 0 0 1–1.5px` accent, nothing else |

**Never combine a ring, a border change and a shadow.** Two signals is emphasis; three is noise.
Two more from the same section, both easy to get wrong: **draw the focus edge after the fill**, and
where something slides underneath, **draw focus as a sibling above it** so it is not overlapped.

## 11. Reserve the destination — zero layout shift

> *"Zero layout shift. Every reachable state reserves its space up front."*
> *"A button keeps its width when its state changes."*

Motion that reflows the page is not polish, it is a bug with an animation on it. Two techniques worth
naming:

- **Reserve up front.** A button that swaps its label for a spinner keeps its widest width; a list
  that will gain a row reserves the row's height.
- **The invisible twin.** *"An invisible copy of the widest state the box can ever hold, in the same
  grid cell, sizing the column once."* Then animate opacity **inside** a box that never resizes. This
  is the same instinct as the skeleton reserving the content's size.

## 12. Announcements: late, once, and about the outcome

Motion and announcement are the same event to a screen-reader user, so this belongs here rather than
only in the a11y contract:

> *"Announce late."* — wait for the stream to stop before saying anything (their delays: 420–900ms).
> *"Announce once."* — dedupe, or a re-render repeats it.
> *"Announce the outcome, not the mechanism."* — "Invoice sent", not "request completed".

This composes with the live-region rule in
[interaction-stimulus.md](interaction-stimulus.md#loading-progress-and-busy-state-95): use
`role="status"`, which carries polite **and** atomic, rather than a bare `aria-live`.

---

## 13. Cross-page motion — Turbo 8 view transitions

Everything above is motion *within* a page. Turbo 8 (**v8.0.0, February 2024**) added two separate
things that are easy to conflate:

- **page refreshes with morphing** (idiomorph DOM-diffing) — nothing to do with view transitions;
- **View Transitions API support for navigations** — this is the cross-page motion one.

**Opt in with a meta tag on *both* the current and the next page**, or nothing happens:

```erb
<meta name="view-transition" content="same-origin">
```

**One correction worth having, because the assumption is natural and wrong:** the Hotwire handbook
does **not** provide or document `view-transition-name`. That property is **plain CSS from the View
Transitions API** — it works because Turbo turned transitions on for the navigation, not because
Turbo wraps it. Naming an element and styling its transition is standard CSS:

```css
.sidebar { view-transition-name: sidebar; }

@media (prefers-reduced-motion: no-preference) {
  ::view-transition-old(sidebar),
  ::view-transition-new(sidebar) { animation-duration: var(--duration-slow); }
}
```

Turbo does add `data-turbo-visit-direction` (`forward` / `back` / `none`) on `<html>`, which is the
hook for direction-aware transitions.

**The rules above still apply across pages** — a departure is still shorter than an arrival, and a
cross-viewport transition is still `--duration-slow`.

## 14. One entrance pattern per page, at most three regions

§7 caps a single stagger. This caps the **page**, which is the limit that actually gets exceeded —
each section is added by someone who only saw their own section.

- **One entrance pattern per page.** Pick `fade-up` *or* `scale-in` *or* a stagger, and use it
  everywhere on that page. Three different entrances do not read as three ideas; they read as an
  unfinished template.
- **At most three animated regions**, and **never two running at once in the viewport**. Motion is a
  focus signal, and a signal competing with another signal is noise. If two regions would animate
  together, they are one region.
- **Never on content the reader came for.** A hero, a feature grid, a testimonial band may animate
  in. Body copy, tables, form fields and anything below the fold that the reader scrolled to *on
  purpose* must be present on arrival — animating it makes the reader wait for something they
  already asked for.

The arithmetic follows §7: three regions at the 1.6s stagger ceiling is 4.8s of page assembly if
they queue, which is why they may not run together rather than merely being capped in number.

This is **ours**, not an upstream rule — no spec bounds animation count. It is recorded here so it
is a decision rather than each author's taste, and it is the number `design-auditor` counts.

## What we did not take

- **The five springs** (`CELL`, `CROSSFADE`, `SMALL`, `DISCLOSE`, `SURFACE`). They are `motion`
  solver constants, and **CSS has no spring or physics-based easing** — verified against MDN's
  easing-function reference, which lists exactly three families: linear (`linear`, `linear()`),
  cubic-bézier (`ease*`, `cubic-bezier()`) and step (`steps()`, `step-start`, `step-end`). §2 keeps
  the *distance-chooses-timing* principle and expresses it in durations instead.
  - **The approximation route, and why we are not taking it yet.** `linear()` takes a list of sampled
    progress points, so a spring curve *can* be pre-sampled into one — and that is an **established
    technique**, documented by Chrome's own developer site, not something we would be inventing.
    `linear()` is [CSS Easing Functions Level 2](https://drafts.csswg.org/css-easing/#the-linear-easing-function)
    and Baseline **since December 2023**. The reason to hold off is not support, it is **cost**: a
    convincing spring needs 40-plus sampled points, and a hand-pasted point list is unreadable and
    unmaintainable at every call site. Reach for it when a specific component genuinely needs spring
    feel and generate the points; do not scatter them through the codebase before then.
- **Velocity handoff** (*"every release passes `info.velocity` into the spring that takes over"*).
  Correct, and it needs a spring to hand off *to*. Revisit if we ever adopt a JS animation library.
- **Entry/exit blur.** Dropped as our call — cost over benefit at our durations.
- **The React-specific machinery** — quantized step state to avoid 60fps re-renders, `layoutId`,
  `useReducedMotion()`. The *underlying* discipline does transfer to Stimulus: when a value changes
  every frame, write it to a CSS custom property or `style.transform` on rAF rather than toggling
  classes, and report the committed value to ARIA rather than every intermediate one.
- **Their colour, radius, typography and material sections.** We have our own, calibrated against our
  own corpora. Only the motion and interaction sections are adapted here.

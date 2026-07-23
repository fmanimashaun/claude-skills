# Layout Primitives

Compose UI from a small set of single-purpose layout primitives; never write per-page
layout CSS. Each primitive owns exactly **one** concern (spacing *or* centering *or*
wrapping *or* ratio) and delegates the rest to a child primitive. They respond to available
space **intrinsically** (flex-wrap, `flex-basis` thresholds, grid `auto-fit`, `clamp()`) —
so most responsiveness needs **no** `@media` query. Tune every knob via a `--custom`
property; never fork a primitive to change a value.

**Spacing lives on the parent** (Stack/Cluster/Grid `gap`), never as a child's outer margin
— so any child slots in cleanly.

## Stateless primitives → Tailwind v4 `@utility` recipes

Define once in `application.css`; apply in ERB like `class="stack"` and tune with inline
`style="--space: var(--space-l)"`.

```css
/* Stack — vertical rhythm BETWEEN siblings only (not edges) */
@utility stack {
  display: flex; flex-direction: column;
  gap: var(--space, var(--space-s));
}
/* Cluster — wrap a group of variable-width items with even gaps (tags, button rows, meta) */
@utility cluster {
  display: flex; flex-wrap: wrap;
  gap: var(--space, var(--space-xs));
  align-items: var(--align, center); justify-content: var(--justify, flex-start);
}
/* Center — center a column and cap it at the measure; gutters so text never hits the edge */
@utility center {
  box-sizing: content-box; margin-inline: auto;
  max-inline-size: var(--measure); padding-inline: var(--gutter, var(--space-s));
}
/* Box — a padded surface (the atomic "thing with padding + border") */
@utility box {
  padding: var(--padding, var(--space-s));
  border: 1px solid var(--color-border); border-radius: var(--radius);
  /* invert variant: set --bg/--fg to flip colors; keep contrast via -foreground tokens */
}
/* Grid — responsive grid that adds/removes columns to fit; no breakpoints */
@utility grid-auto {
  display: grid; gap: var(--space, var(--space-s));
  grid-template-columns: repeat(auto-fit, minmax(min(var(--min, 16rem), 100%), 1fr));
}
/* Frame — lock media to an aspect ratio and crop */
@utility frame {
  aspect-ratio: var(--ratio, 16 / 9); overflow: hidden;
}
@utility frame { & > * { inline-size: 100%; block-size: 100%; object-fit: cover; } }
/* Cover — min-height region that centers a principal child, header/footer pinned to edges */
@utility cover {
  display: flex; flex-direction: column; min-block-size: var(--min-height, 100svh);
  padding: var(--space, var(--space-m)); gap: var(--space, var(--space-m));
  & > .cover-centered { margin-block: auto; }
}
/* Reel — horizontal scroll strip (space-saving alternative to Grid) */
@utility reel {
  display: flex; gap: var(--space, var(--space-s));
  overflow-x: auto; scroll-snap-type: x proximity;
  & > * { flex: 0 0 var(--item-width, 16rem); scroll-snap-align: start; }
}
/* Icon — size an inline SVG to the adjacent text and align it */
@utility with-icon {
  display: inline-flex; align-items: center; gap: var(--space, 0.5em);
  & svg { inline-size: 1em; block-size: 1em; fill: currentColor; }
}
```

## Parameterized / behavioral primitives → ViewComponents

Their `flex-basis`/`calc()` thresholds (or JS) make them awkward as ad-hoc utilities; wrap
as components with slots + args that emit the custom properties.

- **Sidebar** (`Layout::Sidebar`, args `side_width`, `content_min`, `space`, `side: :left|:right`).
  A two-pane layout that wraps to stacked with **no media query**: flex container with
  `flex-wrap: wrap`; the sidebar child `flex-basis: var(--side-width); flex-grow: 1`; the main
  child `flex-basis: 0; flex-grow: 999` with `min-inline-size: var(--content-min, 50%)` — when
  main can't hold that width, the pair wraps. Slots: `sidebar`, `main`.
- **Switcher** (`Layout::Switcher`, args `threshold`, `space`, `limit`). Flips a set of
  equal-width items between one row and a full stack **all at once** at a container-width
  threshold: children `flex-grow: 1; flex-basis: calc((var(--threshold) - 100%) * 999)`; add a
  quantity cap so more than `limit` items always stack. Use for feature columns / pricing tiers.
- **Imposter** (`Layout::Imposter` / used by Modal/Tooltip) — center an element out of flow:
  `position: absolute` (or `fixed`), `inset: 50%`, `translate: -50% -50%`, `max-block/inline-size:
  100%`, `overflow: auto`. Pair with the dismissable-layer + focus-trap Stimulus mixins.
- **Container** (`Layout::Container`, args `name`) — sets `container-type: inline-size`
  (+ optional `container-name`) so nested primitives can respond to their **local** width via
  `@container`. Ideal around Turbo-Frame fragments that render into varying slots. It does NOT
  replace Sidebar/Switcher/Grid (those need zero queries) — use it only when a component needs
  an explicit, component-scoped breakpoint.

## Canonical compositions (nest primitives; don't invent monoliths)

- **Page:** `center > stack`
- **Card:** `box > stack` (media on top via `frame`)
- **Gallery/dashboard:** `grid-auto > (box > stack)`
- **Hero / empty-state:** `cover > center > stack`
- **App shell:** `Layout::Sidebar[ sidebar: nav, main: (stack) ]`
- **Toolbar / tag list / button row:** `cluster`
- **Icon + label (button/link/list):** `with-icon`

## The rules

1. Nest primitives; never write a bespoke `.dialog`-style layout monolith.
2. One concern per primitive; delegate the rest downward.
3. Spacing on the parent's `gap`, never child margins.
4. Tune with `--custom` properties (pulled from the fluid `--space-*` / `--text-step-*` scale).
5. Keep the **measure** intact — Sidebar/Switcher must not let text children exceed `--measure`
   after redistributing width.
6. Intrinsic first; a `@media`/`@container` breakpoint is an exception that must be justified
   (see [responsive.md](responsive.md)).

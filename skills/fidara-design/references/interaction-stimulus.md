# Interaction (Hotwire / Stimulus)

Behavior is Hotwire, not a JS component framework. Interactive components style themselves
off attributes their Stimulus controller toggles (`data-[state=…]`, `aria-*`); Tailwind v4's
`data-*`/`aria-*` variants make this declarative. Build behavior once as **four reusable
mixins**, then compose them — don't re-solve accessibility per component.

## The four reusable mixins (build once, reuse everywhere)

1. **list-navigation** (roving tabindex) — one focusable item at a time; ↑/↓ (or ←/→) move,
   Home/End jump, typeahead, Enter/Space activate. Shared by menu, tabs, listbox/combobox,
   radio-group. Keeps `aria-activedescendant` when focus must stay in an input (combobox).
2. **focus-trap + restore** — on open, move focus in and cycle first/last on Tab; on close,
   **restore focus to the trigger**; mark the background inert (`inert`/`aria-hidden`) and lock
   body scroll. Used by modal + drawer only (never trap outside a true modal).
3. **dismissable-layer** — Esc + outside-click close, maintained as a **stack** so nested
   overlays close top-first. Used by dropdown, popover, tooltip, drawer, modal.
4. **anchored-position** — place a floating element relative to a trigger with collision
   flipping; prefer CSS anchor positioning where available, else a small JS positioner. Used by
   dropdown, popover, tooltip, combobox.

## Per-component behavior contract (WAI-ARIA APG)

| Component | Roles / ARIA | Keyboard | Mixins |
|---|---|---|---|
| Dropdown/Menu | trigger `aria-haspopup aria-expanded aria-controls`; `role=menu/menuitem` | Enter/Space/↓ open · ↑↓ · Home/End · type-ahead · Esc | list-nav + dismissable + anchored |
| Dialog/Modal | `role=dialog aria-modal aria-labelledby` | Esc close · Tab trapped | focus-trap + dismissable |
| Drawer | as Dialog | Esc · Tab trapped | focus-trap + dismissable |
| Tabs | `role=tablist/tab/tabpanel` `aria-selected aria-controls` | ←→ (Home/End) | list-nav |
| Tooltip | `role=tooltip` `aria-describedby` | show on focus+hover · Esc | anchored + dismissable |
| Popover | trigger `aria-expanded aria-controls` | Esc · focus moves in | anchored + dismissable + focus-trap(soft) |
| Combobox | `role=combobox aria-expanded` + listbox `aria-activedescendant` | ↓ into list · ↑↓ · Enter · Esc | list-nav + anchored |
| Accordion | header `<button aria-expanded aria-controls>` | Enter/Space toggle | (toggle) |
| Toast | `role=status`/`alert` `aria-live` | focusable dismiss | dismiss |

Non-negotiables: visible `focus-visible` ring meeting contrast; keyboard reaches everything
the mouse can; restore focus to the trigger on close; announce async changes via a live region.

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

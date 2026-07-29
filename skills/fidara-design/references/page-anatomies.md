# Page anatomies — shells and screen archetypes

The catalog says what a **component** looks like. This says what a **screen** looks like:
which shell holds it, what regions it has, how those regions behave on a phone, and
which catalog entries fill them.

Without this an agent asked for "the invoices screen" has to invent page structure,
and invented structure is where breakpoint chains, nested cards and inconsistent
heading ramps come from. **A screen is composed, not designed.** Pick a shell, pick an
anatomy, fill the regions from the catalog.

Everything here is built from primitives that already exist
(`references/layout-primitives.md`) and roles from `references/foundations-tokens.md`.
Nothing on this page introduces a new `@utility`.

## The contract every shell keeps

The base layout owns two things. A shell may not drop them:

```erb
<%# app/views/layouts/application.html.erb %>
<turbo-frame id="modal"></turbo-frame>   <%# CRUD is modal-driven — crud-modal-pattern.md %>
<div id="toasts" aria-live="polite" class="…"></div>
```

`<turbo-frame id="modal">` is what makes every create/edit path work without a full
page load, and `#toasts` is the only place flash output belongs. A shell that omits
either breaks flows that live outside its own template — the failure shows up in an
unrelated screen, which is the worst kind.

## Type, once, so no screen re-derives it

From `foundations-tokens.md` — interface chrome is **smaller** than prose:

| Region | Step |
|---|---|
| Page title (the one `h1`) | `text-step-3` |
| Section heading | `text-step-2` |
| Card / panel heading | `text-step-1` |
| Prose, ledes, descriptions | `text-step-0` |
| **Everything else in a shell** — nav, buttons, labels, inputs, table cells, badges, breadcrumbs | **`text-step--1`** |
| Meta, timestamps, table headers, helper text | `text-step--2` |

A dense app screen may have **no** `text-step-0` at all. Reaching for it in chrome is
the most common calibration error.

---

# Shell archetypes

Three, and they are exhaustive for app UI. If a screen seems to need a fourth, it is
usually a **page anatomy** problem, not a shell problem.

## 1. Sidebar shell — persistent rail, mobile drawer

**Use when** the product has more than ~5 top-level destinations, or navigation must
stay visible while working. This is the default for authenticated app UI.

```erb
<div class="min-h-dvh bg-card text-foreground">
  <%= render(Layout::SidebarComponent.new) do |sidebar| %>
    <% sidebar.with_sidebar do %>
      <div class="stack h-full pt-safe pb-safe">
        <%= render(Ui::LogoComponent.new(brand_variant: :fmworkflows)) %>
        <nav class="stack" aria-label="Main">…</nav>
        <div class="mt-auto"><%# account / user menu %></div>
      </div>
    <% end %>

    <% sidebar.with_main do %>
      <main id="main" class="min-h-0 overflow-y-auto">…</main>
    <% end %>
  <% end %>
</div>
```

- **Rail** — brand mark top, primary nav, account menu pinned bottom via `mt-auto`.
  Nav items are `text-step--1` with `min-h-touch`.
- **Mobile** — the rail becomes a drawer. `Layout::SidebarComponent` owns the
  disclosure; do not hand-roll a second one. The trigger lives in the mobile top bar,
  is icon-only, and therefore needs `sr-only` text (`components.md` → Navigation).
- **Brand mark** — rail top on desktop, mobile top bar centre or left. Never both at once.
- **Scroll containment** — the rail and `<main>` scroll independently. Both need
  `min-h-0` alongside `overflow-y-auto`; a flex/grid child will not scroll without it
  and the whole page scrolls instead, taking the rail with it.
- **Safe areas** — `pt-safe` / `pb-safe` on the rail, so a notch or home indicator
  never covers the first nav item or the account menu. Matters in Hotwire Native.

## 2. Stacked shell — top bar, no rail

**Use when** navigation is shallow (≤5 destinations), or the content wants full width:
marketing-adjacent app pages, onboarding, single-purpose tools, reading views.

```erb
<div class="min-h-dvh bg-card text-foreground">
  <header class="border-b border-border pt-safe">
    <div class="shell">
      <div class="cluster justify-between min-h-touch">
        <%= render(Ui::LogoComponent.new(brand_variant: :fmworkflows)) %>
        <nav class="cluster" aria-label="Main">…</nav>
      </div>
    </div>
  </header>

  <main id="main" class="shell section-y-compact">…</main>
</div>
```

- **Mobile** — the nav collapses behind a disclosure in the same bar. The bar itself
  never wraps to two rows; that is the signal you needed the sidebar shell.
- **`shell`** gives the page gutters and max measure. Do not re-declare `max-w-*` inside it.
- **Separation** is `border-b border-border`, not a shadow. Elevate only genuine
  overlays (`foundations-tokens.md`).
- Use `section-y-compact` for app pages; plain `section-y` is the marketing rhythm.

## 3. Multi-column shell — rail, main, aside

**Use when** a secondary region must stay visible while working in the primary one:
inbox + reading pane, record + activity feed, editor + inspector.

```erb
<%= render(Layout::SidebarComponent.new) do |sidebar| %>
  <% sidebar.with_sidebar do %>…<% end %>
  <% sidebar.with_main do %>
    <div class="grid-auto items-start" style="--min: 28rem">
      <main id="main" class="min-h-0 overflow-y-auto">…</main>
      <aside class="min-h-0 overflow-y-auto" aria-label="Details">…</aside>
    </div>
  <% end %>
<% end %>
```

- **Intrinsic, not breakpointed.** `grid-auto` collapses to one column when the
  container cannot fit two of `--min` — no `lg:grid-cols-2`. The columns reflow
  because the *container* is narrow, which is also correct inside a drawer or a split view.
- **Mobile** — one column, `<aside>` after `<main>` in DOM order so it reads second.
  When the aside is a *detail of a selection* rather than a companion, it becomes a
  separate screen on mobile, not a stacked region.
- **Three independent scroll regions** — rail, main, aside. Each needs `min-h-0` with
  its `overflow-y-auto`.
- `items-start` stops a short aside stretching to the tallest column.

---

# Page anatomies

Same four regions every time, so screens stay recognisable:

**heading block → toolbar → content region → aside (optional)**

## Home / dashboard

Answers "what needs my attention?" — not "here is everything."

```erb
<div class="stack">
  <header class="stack">
    <h1 class="text-step-3"><%= t(".title") %></h1>
    <p class="text-step-0 text-muted-foreground prose-measure"><%= t(".lede") %></p>
  </header>

  <div class="grid-auto" style="--min: 16rem">
    <%# stat cards — Card, one metric each %>
  </div>

  <div class="grid-auto items-start" style="--min: 24rem">
    <%# charts on chart tokens (data-viz.md); recent-activity list %>
  </div>
</div>
```

- **Composes** — Card, Badge, Table (CRUD) for recent rows, Empty state, charts per
  `data-viz.md`. Never raw hex in a chart; the palette is validated per brand pack.
- **Mobile** — every `grid-auto` band collapses to one column with no breakpoints.
  Order bands by urgency, because on a phone the third band is below the fold.
- **Empty state is not optional.** A dashboard on day one has no data, and that is the
  first screen a new user sees.

## Detail

One record. The screen answers "what is this, and what can I do to it?"

```erb
<div class="stack">
  <nav aria-label="Breadcrumb" class="text-step--1">…</nav>

  <header class="cluster justify-between items-start">
    <div class="stack gap-1">
      <h1 class="text-step-3"><%= @invoice.reference %></h1>
      <div class="cluster text-step--2 text-muted-foreground"><%# status badge, meta %></div>
    </div>
    <div class="cluster"><%# primary action + overflow menu %></div>
  </header>

  <div class="grid-auto items-start" style="--min: 26rem">
    <div class="stack"><%# the record: description list, related table %></div>
    <aside class="stack" aria-label="Activity">…</aside>
  </div>
</div>
```

- **Composes** — Badge (status), Button (one primary action), Dropdown (overflow),
  Table, Modal for every edit, Avatar in activity, Breadcrumb.
- **Mobile** — the header `cluster` wraps naturally; actions drop below the title
  rather than being cramped beside it. Keep the primary action visible without
  scrolling; move the rest into the overflow menu.
- **Edits are modal** (`crud-modal-pattern.md`) targeting `<turbo-frame id="modal">`.
  A detail screen that navigates away to edit loses the user's place.

## Settings

Many small forms, grouped. The risk here is a wall of inputs.

```erb
<div class="stack">
  <header class="stack">
    <h1 class="text-step-3"><%= t(".title") %></h1>
  </header>

  <%= render(Layout::Switcher.new(threshold: "48rem")) do %>
    <nav class="stack" aria-label="Settings sections">…</nav>

    <div class="stack">
      <section class="box stack" aria-labelledby="profile-heading">
        <h2 id="profile-heading" class="text-step-1"><%= t(".profile") %></h2>
        <%= simple_form_for @user do |f| %>
          <div class="stack">
            <%= f.input :name %>
            <%# every field is `f.input` — the anatomy comes from the simple_form
                wrapper (forms.md); a page anatomy owns only the arrangement %>
          </div>
          <div class="cluster justify-end">
            <%= render(Ui::ButtonComponent.new(variant: :primary)) { t(".save") } %>
          </div>
        <% end %>
      </section>
    </div>
  <% end %>
</div>
```

- **Composes** — Field/Forms (`forms.md`), Switch for booleans, Button, Alert for
  destructive confirmation, Tabs *only* if sections are few and mutually exclusive.
- **Section per `box`**, heading at `text-step-1`. **Never nest a card in a card** —
  the section *is* the surface.
- **Mobile** — `Layout::Switcher` puts the section nav above the panels below its
  threshold. Do not convert the nav to tabs on mobile; that hides which section you are in.
- **Save per section**, not one page-wide save. A single save button over eight
  sections makes every edit feel risky.

---

# No breakpoint where a primitive says it better

The kit's structure is breakpoint-driven; ours is intrinsic. Substitute:

| Instead of | Use | Why |
|---|---|---|
| `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3` | `grid-auto` + `--min` | Reflows on **container** width, so it is correct in a drawer or split view too |
| `flex-col md:flex-row` | `Layout::Switcher` with a threshold | The switch happens at the width the *content* needs, not a device guess |
| `hidden md:block` for a rail | `Layout::SidebarComponent` | Drawer behaviour and the disclosure come with it |
| `space-y-*` on children | `stack` (parent `gap`) | Spacing belongs to the parent; margins fight when children reorder |
| `flex items-center gap-*` | `cluster` | Wraps by default, which is what you wanted on a phone |
| `max-w-7xl mx-auto px-*` | `shell` | One definition of page gutters and measure |
| `overflow-y-auto` alone in a flex/grid child | add `min-h-0` | Without it the child cannot shrink, so the *page* scrolls instead of the region |

A `sm:`/`lg:` prefix is legitimate when the change is genuinely viewport-dependent —
safe-area padding, or a fixed bottom bar that only exists on small screens. It is not
legitimate as a substitute for a primitive that expresses the same intent.

# Choosing, in order

1. **Shell** — >5 destinations or nav must persist → sidebar. Secondary region stays
   visible → multi-column. Otherwise → stacked.
2. **Anatomy** — many records → dashboard. One record → detail. Many small forms →
   settings.
3. **Fill regions from the catalog.** If nothing fits, that is a catalog gap worth
   filing, not a licence to invent a bespoke component in a page template.
4. **Check** — one `h1` at `text-step-3`; chrome at `text-step--1`; no nested cards; no
   breakpoint chain from the table above; `min-h-0` on every scroll region; empty state
   for anything data-driven; `min-h-touch` on every control; safe-area padding on fixed
   chrome.

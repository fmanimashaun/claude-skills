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

The base layout owns three things. A shell may not drop them:

```erb
<%# app/views/layouts/application.html.erb %>
<a href="#main" class="fixed left-2 -top-16 focus-visible:top-2 …">Skip to main content</a>
<turbo-frame id="modal"></turbo-frame>   <%# CRUD is modal-driven — crud-modal-pattern.md %>
<div id="toasts" aria-live="polite" class="…"></div>
```

`<turbo-frame id="modal">` is what makes every create/edit path work without a full
page load, and `#toasts` is the only place flash output belongs. A shell that omits
either breaks flows that live outside its own template — the failure shows up in an
unrelated screen, which is the worst kind.

The skip link is **first in `<body>`, before the header**, and it is a **Level A**
obligation (WCAG 2.4.1 Bypass Blocks), not a nicety. Every `<main>` below therefore
carries `id="main"` **and `tabindex="-1"`** — without the latter the fragment's focusing
steps fall back to the viewport and focus never reaches the region. Full recipe, including
why the usual `sr-only` + `focus-visible:not-sr-only` construction is a coin flip, in
`components.md` → Skip link and `component-implementations.md`.

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
      <main id="main" tabindex="-1" class="min-h-0 overflow-y-auto">…</main>
    <% end %>
  <% end %>
</div>
```

- **Rail** — brand mark top, primary nav, account menu pinned bottom via `mt-auto`.
  Nav items are `text-step--1` with `min-h-touch`.
- **Mobile** — the rail becomes a drawer. `Layout::SidebarComponent` owns the
  disclosure; do not hand-roll a second one. The trigger lives in the mobile top bar,
  is icon-only, and therefore needs `sr-only` text (`components.md` → Navigation — sidebar / vertical).
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

  <main id="main" tabindex="-1" class="shell section-y-compact">…</main>
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
      <main id="main" tabindex="-1" class="min-h-0 overflow-y-auto">…</main>
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

The heading block is the `Heading` component (`page`/`section`/`card` scale); breadcrumbs, description lists, button groups and media objects are catalog entries too — see `components.md` → Heading blocks, Breadcrumbs, Description list, Button group, Media object.

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

- **Composes** — Breadcrumbs, Heading(`page`) with a Button group in its actions slot, Badge
  (status), Dropdown (overflow), Description list for the record, Media object per activity
  entry, Table, Modal for every edit.
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

## How a page is paced

Everything above says what one **band** contains. Nothing said what the **sequence** of bands looks
like — and on a marketing page the sequence *is* the design. This section is that sequence, and it
composes only from rows that already exist: no new token, no new `@utility`, no new archetype.

<!-- page-pacing:begin -->

**The gap is measurable in our own generated data.** In [coverage.md](coverage.md), **14**
marketing-section rows carry a byte-identical `Build from` string — Bento grid, Blog / article list,
CTA, Contact, Content / prose, FAQ, Feature, Hero, Logo cloud, Newsletter, Pricing, Stats, Team and
Testimonial. Every one of those rows is correct on its own. Followed literally they compose
**fourteen identical centred stacks separated by equal whitespace**: a page right in every part and
flat as a whole. `scripts/check_page_pacing.py` re-measures that count against `coverage.md`, so it
is a measurement rather than an assertion.

**6–8 bands** sit between the marketing header and the footer. Fewer says nothing; more is a page
nobody reaches the end of. The default sequence:

| # | Band | Composed from | Tone | Columns | Width |
|---|---|---|---|---|---|
| 1 | Hero — the claim, the lede, the one primary action, a proof strip | Hero section | card | 1 | prose |
| 2 | Capabilities — 3–6 verb-led cards | Feature section | background | n | shell |
| 3 | Deep feature — prose beside a product screenshot | Feature section | card | 2 | shell |
| 4 | Proof — the customer marks, on one line | Logo cloud | background | 1 | shell |
| 5 | How it works — three numbered steps, as an `<ol>` | Content / prose section | card | 1 | prose |
| 6 | Objections — the three questions sales actually hears | FAQ section | background | 2 | shell |
| 7 | Closing CTA — the same action as the hero | CTA section | card | 1 | prose |

<!-- page-pacing:end -->

**Reading the three axis columns.** Each names something already shipped; none is a new knob.

| Column | Values | What they are |
|---|---|---|
| **Tone** | `card` · `background` | the role painted on the full-bleed band — `bg-card` / `bg-background` from `foundations-tokens.md` §2 |
| **Columns** | `1` · `2` · `n` | `stack` · `Layout::Switcher` · `grid-auto`, from `layout-primitives.md` |
| **Width** | `prose` · `shell` | the utility capping the band's *content*: `prose-measure` (`--width-prose`) or `shell` (`--width-shell`) |

`Composed from` names a row of `coverage.md` verbatim, and the same check reads that join: a band
naming something that is not a row fails, which is what keeps this table from quietly growing a
fifteenth section nobody documented.

### The rules

1. **Tone alternates at every boundary.** A marketing page starts on `card` because the stacked
   shell already paints its root `bg-card` — so the hero meets the header with no seam — and every
   other band is `background`.
2. **Consecutive bands never share both Columns and Width.** This is the rule the 14 identical rows
   break: `1` + `prose` fourteen times running is the flat page. Changing *both* is fine; changing
   *neither* is the defect.
   The tempting stronger form — *"exactly one axis moves per boundary"* — **contradicts rule 1
   outright**, and the proof is one line: if tone must change at every boundary and only one axis
   may change at a boundary, then tone is the axis that changes every time, so Columns and Width
   never change at all. "Exactly one axis" plus alternating tone *is* the flat page, arrived at by
   a rule that sounds stricter. That is why the shipped rule is a floor and not an equality.
3. **A band's edge comes from its tone, not from a border.** No `border-b` between marketing bands.
   The 1px edge is chrome — the stacked shell's own header uses it, and `foundations-tokens.md` →
   *Elevation idiom* measured that a 1px edge plus a minimal shadow is the whole vocabulary.
4. **A `card`-tone band carries no `Ui::Card`.** A card on a `card` surface has nothing to sit
   against, and both flatten. This is *Settings*' "never nest a card in a card", lifted from the
   section to the page: card grids go on a `background` band, which is why band 2 is where it is.
5. **One primary action for the page, at most once per band.** This reconciles two things already
   written rather than adding a third: `coverage.md`'s Button row says `primary` **once per view**
   (one primary *action*, not one button), and *Landing* below says that same CTA appears in the
   hero, once mid-page, and in the closing band. Two `primary` fills in one band is the violation.
   Every other action on the page is `secondary` or the Button `link` variant.
6. **Decoration in at most two bands, and never two adjacent.** `visual-assets.md` §8 already owns
   the hard part — decoration never goes behind running text, because contrast is measured against
   what is actually behind the glyphs. The *count* is the new half, and it is the page-level twin of
   `motion.md` §14: each band is added by someone who only saw their own band.
7. **Motion is not restated here.** `motion.md` §14 caps a page at one entrance pattern and three
   animated regions, never two at once. Pacing adds nothing to it.

```erb
<%# A band is full-bleed, so its tone reaches the viewport edge; the width utility caps the CONTENT
    inside it, never the band. Band 1 — hero: `card` tone, one column, prose width. %>
<section class="bg-card section-y">
  <div class="stack text-center prose-measure mx-auto">
    <h1 class="text-step-5"><%= t(".claim") %></h1>
    <p class="text-step-1 text-muted-foreground"><%= t(".lede") %></p>
    <div class="cluster justify-center"><%# the one primary action %></div>
  </div>
</section>

<%# Band 2 — capabilities. Tone flips, and Columns and Width move with it, so the boundary reads
    without a rule drawn between them. Cards sit on a `background` band, never on a `card` one. %>
<section class="bg-background section-y" aria-labelledby="capabilities-heading">
  <div class="shell stack">
    <h2 id="capabilities-heading" class="text-step-2"><%= t(".capabilities") %></h2>
    <div class="grid-auto" style="--min: 18rem"><%# 3–6 Ui::Card, verb-led headings %></div>
  </div>
</section>
```

**Every band still needs an `h2`**, visible or `sr-only` — the heading-outline rule under *Landing*
applies per band, and a page whose bands are distinguished only by colour has no outline at all.

**None of this has an upstream.** There is no specification for how many bands a marketing page has
or in what order, so this is **ours**, recorded here so it is a decision rather than each author's
taste — the same footing as `motion.md` §14's region cap. Where a claim above *does* have a source it
is cited to the file that carries it, and the only number asserted about ourselves (the 14) is
measured. The band **sequence** is a default, not a law: swap band 4 for *Stats section* or *Testimonial
section*, or band 6 for a *Pricing section / table* teaser. The rules above do not move.

## Landing

The one screen that must survive a stranger's first eight seconds. It answers *"why should I care,
and what do I do next?"* — nothing else.

**This is the spine of the paced sequence above, not a second answer.** Its four sections are bands
1, 2, 5 and 7 of *How a page is paced*; the bands between them, the tone alternation and the axis
rules are there, and a real landing page needs all of it.

**Shell: stacked.** No sidebar; there is no app to navigate yet. Marketing pages are the only place
the stacked shell is the *default* rather than a choice.

**One primary action, repeated — never several competing ones.** The same CTA appears in the hero, once
mid-page, and in the closing band. Two different primary CTAs on a landing page is a decision the
visitor has to make instead of the one you want.

```erb
<div class="stack" style="--space: var(--space-xl)">
  <section class="stack text-center" style="--space: var(--space-s)">
    <h1 class="text-step-5 max-w-[45ch] mx-auto"><%# the claim, not the product name %></h1>
    <p class="text-step-1 text-muted-foreground max-w-[60ch] mx-auto"><%# who it is for, concretely %></p>
    <div class="cluster justify-center"><%# primary CTA + one quiet secondary %></div>
    <%# proof immediately under the fold line: logos, a number, or one real quote — not all three %>
  </section>

  <section class="grid-auto" style="--min: 18rem" aria-label="Capabilities">
    <%# 3–6 capability cards. Each: verb-led heading, one sentence, no icon-only labels %>
  </section>

  <section class="stack" aria-label="How it works">
    <%# 3 numbered steps. An <ol>, because the order is the meaning %>
  </section>

  <section class="stack text-center" aria-label="Get started">
    <%# the SAME primary CTA as the hero %>
  </section>
</div>
```

**Heading discipline:** exactly one `h1` (the claim). Every section gets an `h2`, even where the design
shows no visible heading — use `sr-only` rather than skipping the level, or the page has no outline for
anyone navigating by headings.

## Pricing

Answers *"which plan, and what will it cost me?"* — in that order. The comparison is the page; the
prose is scaffolding.

```erb
<div class="stack" style="--space: var(--space-l)">
  <header class="stack text-center" style="--space: var(--space-2xs)">
    <h1 class="text-step-4">Pricing</h1>
    <%# billing-period toggle: a Ui::ButtonGroup with kind: :select — it is a radiogroup, not styling %>
  </header>

  <div class="grid-auto items-start" style="--min: 17rem">
    <%# one Ui::Card per plan. The recommended plan carries a Ui::Badge, NOT colour alone %>
  </div>

  <table class="w-full text-step--1">
    <caption class="sr-only">Plan comparison</caption>
    <thead><tr><th scope="col">Feature</th><%# th scope=col per plan %></tr></thead>
    <tbody><%# th scope=row per feature; ✓/— cells carry an sr-only word, never a bare glyph %></tbody>
  </table>

  <section aria-label="Pricing questions"><%# the 3 objections sales actually hears, as a disclosure %></section>
</div>
```

**The recommended plan needs a non-colour signal.** A ring or tint alone fails for anyone who cannot
see it; the badge is what carries the meaning. Same rule as every status in this system.

**Comparison cells must say what they mean.** A `✓` with no accessible name is announced as nothing.
Pair the glyph with `sr-only` text ("Included" / "Not included") — the identical reasoning to icon-only
controls needing a name.

## About

Answers *"who is behind this, and can I trust them?"* Mostly prose, which is exactly why it goes wrong:
there is no data to structure, so it drifts into a wall.

```erb
<div class="stack" style="--space: var(--space-l)">
  <header class="stack" style="--space: var(--space-2xs)">
    <h1 class="text-step-4"><%# what we do, in one line — not "About us" %></h1>
    <p class="text-step-1 text-muted-foreground max-w-[65ch]"><%# the why %></p>
  </header>

  <section class="stack" aria-label="Story">
    <%# prose: max-w-[70ch]. Longer measures are unreadable regardless of type size %>
  </section>

  <section class="grid-auto" style="--min: 14rem" aria-label="Team">
    <%# Ui::MediaObject per person: avatar + name + role. Avatar never carries the name alone %>
  </section>
</div>
```

**Constrain the measure, not the font size.** A 70-character line is the readability limit; making type
smaller to fit more per line makes it worse, not denser.

## Error (404 / 500)

Answers *"where am I, and how do I get out?"* Two sentences and a way forward — nothing else earns its
place on a page someone reached by accident.

**The status code must match the page.** A 404 design served with HTTP 200 is a *soft 404*: search
engines index it, and monitoring never sees the failure. This is the mirror of the evidence rule in
`qa-flow` — an error page that returns 200 is indistinguishable from a working one to everything except
a human reading it.

```erb
<%# rendered by the framework's error handler; no app chrome, because the app may be what failed %>
<div class="center stack text-center" style="--space: var(--space-s)">
  <p class="text-step--1 text-muted-foreground"><%# the code, as text: "404" %></p>
  <h1 class="text-step-3"><%# what happened, in plain words %></h1>
  <p class="text-muted-foreground max-w-[50ch]"><%# what to do about it %></p>
  <div class="cluster justify-center"><%# back to safety: home, or the thing they probably wanted %></div>
</div>
```

**A 500 page must not depend on the app.** No database call, no current-user lookup, no asset the failed
boot might not have compiled — a 500 page that itself raises produces a blank browser default. Keep it
static and self-contained.

**Never blame the visitor.** "The page you requested no longer exists" beats "you have entered an
invalid URL", and it is usually truer — the link was probably ours.

## Auth (sign-in / sign-up / reset)

Answers *"who are you?"* One focused form and nothing to click away to.

**No shell at all** — this is the one archetype that uses neither the sidebar nor the stacked shell.
Showing app navigation to someone who is not signed in advertises destinations they cannot reach.

```erb
<div class="center" style="--measure: 24rem">
  <div class="box stack" style="--space: var(--space-s)">
    <%# brand mark links home — the only exit, and it must exist %>
    <h1 class="text-step-2"><%# "Sign in" — the action, not "Welcome back" %></h1>

    <%# Ui::Alert intent: :error for the failure summary, ABOVE the form. One message, %>
    <%# never per-field noise after a wrong password: it leaks which half was wrong %>

    <%= simple_form_for(...) do |f| %>
      <%# email: autocomplete="username", inputmode="email" %>
      <%# password: autocomplete="current-password" (new-password on sign-up) %>
      <%# submit: full width, and disabled-with-label while in flight, never a bare spinner %>
    <% end %>

    <div class="cluster justify-between text-step--1">
      <%# the one alternate route: forgot password, or sign-up ↔ sign-in %>
    </div>
  </div>
</div>
```

**`autocomplete` tokens are not optional polish.** Without `username` / `current-password` /
`new-password`, password managers cannot fill or save, and users fall back to weaker passwords they can
type. This is a security property of the markup.

**Say nothing about which credential was wrong.** "Email or password is incorrect" is the whole
message — anything more precise is an account-enumeration oracle.

**A password reset always reports success.** "If that address has an account, we have sent a link" is
the only safe response; confirming an address exists is the same leak by a slower route.

## Storefront

The shop's front door. Answers *"what do you sell, and where do I start?"* — a curated entry, never a
dump of the catalogue.

**Shell: stacked.** Same reasoning as Landing: there is no app rail to show a browsing visitor.

```erb
<div class="stack" style="--space: var(--space-xl)">
  <section aria-label="Featured"><%# one hero promotion — a second competes with the first %></section>

  <section class="stack" aria-label="Shop by category">
    <h2 class="text-step-2">Categories</h2>
    <div class="grid-auto" style="--min: 12rem"><%# category tiles: image + NAME, never image alone %></div>
  </section>

  <section class="stack" aria-label="New arrivals">
    <%# a reel of product cards, each a full link to the product — not a card with a nested button %>
  </section>
</div>
```

**A category tile's image is never the label.** `alt=""` on the image and the name as real text, or the
tile announces as an unlabelled link.

## Category

A filtered, sorted list. Answers *"which of these?"*

```erb
<div class="grid-auto items-start" style="--min: 14rem">
  <form method="get" class="stack" aria-label="Filter products">
    <%# filters are a FORM with a submit — see below. Checkbox groups in a fieldset+legend %>
  </form>

  <div class="stack">
    <div class="cluster justify-between items-baseline">
      <h1 class="text-step-3"><%# category name %></h1>
      <%# sort: a real <select> with a label — the value is a closed set, so no combobox %>
    </div>
    <p role="status" class="text-step--1 text-muted-foreground"><%# "24 products" — announced on change %></p>
    <div class="grid-auto" style="--min: 15rem"><%# product cards %></div>
    <nav aria-label="Pagination"><%# see below %></nav>
  </div>
</div>
```

**Filters must be a form that works without JavaScript.** Enhance with Turbo, but the `GET` submit is
the baseline: filter state then lives in the URL, which makes results shareable, back-button-correct,
and reachable by anyone whose JS failed to load.

**Announce the result count.** After a filter changes, a sighted user sees the grid redraw; nobody else
does. A `role="status"` line carrying "24 products" is the whole fix.

**Paginate by default; do not infinite-scroll.** Infinite scroll breaks the back button, strands
keyboard users before the footer, and has no addressable position. If you must, provide a "load more"
button — a real control, not a scroll listener.

## Product

One item. Answers *"is this the right thing, and can I buy it?"*

```erb
<div class="stack">
  <nav aria-label="Breadcrumb" class="text-step--1">…</nav>

  <div class="grid-auto items-start" style="--min: 20rem">
    <div class="stack" aria-label="Product images">
      <%# each image needs alt describing THE PRODUCT, not "product image 2" %>
      <%# thumbnails are buttons in a group, with the active one announced as selected %>
    </div>

    <div class="stack" style="--space: var(--space-s)">
      <h1 class="text-step-3"><%# product name %></h1>
      <%# price: see the discount rule below %>
      <%# stock state as TEXT — "In stock", "2 left", "Out of stock" — never colour alone %>
      <%# the basket count elsewhere on the page carries role="status" %>

      <%= simple_form_for(...) do |f| %>
        <%# variants: a fieldset + legend per axis, radios inside. NOT a styled div, and %>
        <%# NOT a select unless the axis genuinely has no visual dimension %>
        <%# unavailable variants are disabled AND say why: "Blue — out of stock" %>
        <%# quantity: a number input with a label, not bare +/- buttons %>
        <%# submit: "Add to basket" %>
      <% end %>

      <%# delivery + returns as a disclosure group — the two questions that block a purchase %>
    </div>
  </div>
</div>
```

**A discount needs two prices and a word.** Show the original and the current, and mark the original
with `<s>` plus `sr-only` "was" / "now". Colour and a strikethrough alone convey nothing to a screen
reader, and red-as-cheap is not universal.

**Adding to the basket must be announced.** The button click changes state elsewhere on the page (a
basket count in the header); that change needs `role="status"` on the count, or only sighted users learn
it worked. Same reason as the cart total: `role="status"` bundles polite *and* atomic, so the
announcement carries "Basket, 5 items" rather than a bare "5".

## Cart

A mutable list. Answers *"what am I about to buy, and can I still change it?"*

```erb
<div class="grid-auto items-start" style="--min: 18rem">
  <div class="stack">
    <h1 class="text-step-3">Basket</h1>
    <ul role="list" class="stack divide-y divide-border">
      <%# the Stacked list recipe (components.md); role="list" because Preflight unstyles it %>
      <%# per line: Ui::MediaObject — image, name (a link back), variant, unit price %>
      <%# quantity: labelled number input, "Update" reachable without JS %>
      <%# remove: an accessible name that NAMES THE ITEM — see below %>
    </ul>
  </div>

  <aside class="box stack" aria-label="Order summary">
    <%# subtotal, delivery, tax, total. Ui::DescriptionList with layout: :inline %>
    <%# the total carries role="status" — polite AND atomic; see below %>
    <%# checkout CTA %>
  </aside>
</div>
```

**A remove control must name what it removes.** An icon-only `×` announces as "button" and there are
six of them. `aria-label="Remove Blue T-shirt, medium"` — the item, not the row number.

**Quantity and total changes go in a live region — `role="status"`, not bare `aria-live`.** Change a
quantity and the total changes silently, so the consequence of the edit must be announced. Use
`role="status"` on the total: it carries an implicit `aria-live="polite"` **and** an implicit
`aria-atomic="true"`. Bare `aria-live="polite"` defaults `aria-atomic` to **false**, and then
*"assistive technologies will only present the changed node"* — so a total going from £48.00 to £52.00
announces as **"52.00"**, the number without its label. This is the single most-missed thing in commerce
a11y, and the one with a direct revenue cost.

**An empty basket is a page, not a blank.** Say it is empty and give one route back to browsing.

## Checkout — the purchase flow

A form under pressure. Answers *"how do I pay?"* — and nothing else, because every other element on
this page is a chance to abandon.

**This is the one full-page, multi-step flow in a Fidara UI, and it is a deliberate exception to
[crud-modal-pattern.md](crud-modal-pattern.md#the-one-exception-the-purchase-flow-is-full-page).**
Everything else that creates a record opens a modal on the page behind it. A purchase does not,
because the page behind it is the thing being abandoned: a modal keeps the shop in view and gives the
user a dismiss affordance — Esc, a backdrop click, a close button — over a financial commitment, and
its focus trap fights with a payment provider's iframe. Read the exception's four conditions before
claiming another flow qualifies; almost none do.

```erb
<div class="center stack" style="--measure: 34rem">
  <%# brand mark only. No nav, no promotions, no newsletter — the shell is deliberately stripped %>
  <ol role="list" class="cluster text-step--1" aria-label="Checkout progress">
    <%# Contact → Delivery → Payment → Review. The Stepper contract, not a tablist — components.md %>
  </ol>

  <%# the h1 is the CURRENT STEP, and focus moves here on advancing. tabindex="-1" makes it a target %>
  <h1 id="step-heading" tabindex="-1" class="text-step-2"><%# "Delivery" %></h1>

  <%# error summary: Ui::Alert intent: :error, ABOVE the form, focus moved to it on failure, %>
  <%# each message a link to the field it concerns %>

  <%= simple_form_for(...) do |f| %>
    <%# contact: email, autocomplete="email" %>
    <%= render Ui::AddressFieldsComponent.new(form: f, mode: :shipping) %>
    <%# delivery choice: fieldset + legend, radios, price and ETA in the label text %>
    <%# "Billing address is the same" — a real checkbox that populates, see 3.3.7 below %>
    <%# payment: the provider's iframe/element — never a hand-rolled card field %>
    <%# submit: full width, disabled-with-label in flight, and idempotent on double-submit %>
  <% end %>
</div>
```

**Never require an account to buy.** Offer guest checkout first and account creation *after* the order
is placed, from data you already have.

**Never lose what was typed.** On validation failure re-render with every field repopulated. Losing an
address is the most common abandonment cause that is entirely the implementation's fault.

**One column.** Multi-column forms produce ambiguous tab order and unreadable error association; the
summary belongs above or below, not beside.

**A double-submitted payment must not double-charge.** Turbo already *"set[s] the 'submitter' element's
disabled attribute when the submission begins, then remove[s] the attribute after the submission
ends"*, so the client-side half costs you nothing — which is precisely why it is not the guard. It
loses to a reloaded tab. **The server action must be idempotent**; the button state is feedback. Full
rule in `components.md` → Payment / card entry.

**A final review step is how a checkout meets 3.3.4, and it is AA.** Error Prevention (Legal,
Financial, Data) covers *"web pages that cause legal commitments or financial transactions for the user
to occur"* and requires at least one of **Reversible**, **Checked**, or **Confirmed** — *"a mechanism is
available for reviewing, confirming, and correcting information before final submission."* A review
step gives you Confirmed outright, which is why the flow has four steps and not three. The level
distinction against 3.3.6 lives once, in `components.md` → Stepper / wizard; do not restate it here
and let the two drift.

**"Billing address is the same" is not a convenience, it is 3.3.7 Redundant Entry at Level A.**
*"Information previously entered by or provided to the user that is required to be entered again in
the same process is either: auto-populated, or available for the user to select."* The Understanding
document's own example is *"a form on an e-commerce website allows the user to confirm that the
billing address and delivery address are the same address."* Its exceptions — essential re-entry,
security, or information no longer valid — do not cover an address. Carry the same rule across steps:
anything the user typed on step 1 is pre-filled on step 4, never asked twice.

**A cart or stock hold with a countdown is a time limit under 2.2.1 (Level A).** The practical route
is **Extend**: *"the user is warned before time expires and given at least 20 seconds to extend the
time limit with a simple action … and the user is allowed to extend the time limit at least ten
times."* Do not reach for the **Real-time Exception** — its example is an auction, *"and no alternative
to the time limit is possible"*, which a reservation timer you chose the length of is not.

**Money is `tabular-nums`; the order reference is `font-mono`.** They are different jobs and
[brand.md](brand.md) scopes `--font-mono` to *reference numbers, SLA timers, code, timestamps* — not
to money. `tabular-nums` is what makes a column of totals align in the interface face. Storage is the
rails-8 skill's call, not this one: `ecosystem-gems.md` says store integer minor units
(`price_cents`), so never round a float into a total you display.

**The confirmation is the last step of this flow, not a toast.** Land on a real page with the order
reference as text (`font-mono`), what was bought, what was charged, where it is going, and what
happens next. Offer account creation here, from data already captured. The receipt is the same content
rendered for print or PDF — one template, not a second design. **Never show a full payment number**:
the last four digits and a brand, from the provider's token.

**A redirect-based provider needs the form out of Turbo's hands.** `data-turbo="false"` *"disables
Turbo Drive on links and forms including descendants"*. Without it Turbo fetches the cross-origin
payment page, cannot render it, and the press appears to do nothing.

## Order detail

One order. Answers *"what did I buy, and where is it?"* The `Detail` anatomy with a status timeline.

```erb
<div class="stack">
  <nav aria-label="Breadcrumb" class="text-step--1">…</nav>
  <header class="cluster justify-between items-start">
    <div class="stack gap-1">
      <h1 class="text-step-3"><%# "Order #1234" %></h1>
      <%# placed date + status as TEXT with a Ui::Badge, never colour alone %>
    </div>
    <div class="cluster"><%# invoice download, reorder, support %></div>
  </header>

  <ol role="list" class="stack" aria-label="Order progress">
    <%# an ordered list because the sequence IS the meaning; the current step is marked in text %>
  </ol>

  <div class="grid-auto items-start" style="--min: 22rem">
    <div class="stack"><%# line items, read-only — quantities are no longer editable %></div>
    <aside class="stack" aria-label="Summary"><%# totals, address, payment method last 4 %></aside>
  </div>
</div>
```

**A progress tracker is an ordered list, and the current step must be readable.** Position conveyed by
colour or a filled dot alone is invisible; the current step says so in text ("Shipped — current").

**Never show a full payment number.** Last four digits and a brand, from the provider's token — the
number should not be in your database to display.

## Order history

A list of records. Answers *"what have I bought?"*

```erb
<div class="stack">
  <h1 class="text-step-3">Orders</h1>
  <%# a Ui::Table on wide screens; on narrow, a stack of Ui::Card — the same data, not a scroll %>
  <%# each row: order number (a link), date, item count, total, status badge + text %>
  <nav aria-label="Pagination">…</nav>
</div>
```

**A wide table becomes cards, not a horizontal scroll.** A commerce account page is read on a phone
more often than not, and a horizontally scrolling table hides the total — the one column that matters.

**An empty state names the action.** "No orders yet" plus a route to the storefront.

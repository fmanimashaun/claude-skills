# Visual assets — what actually fills the large visual area

Every marketing surface has a region that is neither text nor control: the right half of a hero, the
band behind a stats section, the left panel of a split sign-in, the whole middle of a 404. The system
has had nothing to say about it. Unspecified means invented per screen, and the three things an agent
reaches for when nothing is specified are all bad: leave it empty, generate something inconsistent,
or import stock art that undercuts the brand.

**Illustration is the hardest asset class to keep consistent** — a mismatched set is the fastest way
to make a site look cheap — so this doctrine deliberately biases away from it, and gives you
something cheaper and more consistent to reach for instead.

---

## Provenance — what has an upstream here, and what does not

This file mixes two kinds of statement, and conflating them is how wrong doctrine ships confidently.

- **Our design decisions, with no upstream to cite.** The tier hierarchy, "prefer specific over
  decorative", brand-geometric decoration as the default filler, the per-surface prescriptions, and
  the decision to keep illustration in last place. There is **no ARIA APG pattern for a decorative
  background or a product screenshot** — the APG example index carries none — so nothing here is
  dressed up with a borrowed citation. These were decided on
  [#135](https://github.com/fmanimashaun/claude-skills/issues/135).
- **Externally verifiable claims, verified and cited inline.** Tailwind v4 utility names and version
  floors, image-format Baseline status, the accessibility treatment of decorative content, and the
  Playwright capture API. Each carries its source and, where it moves, its **version boundary**.

Two corrections the verification produced, recorded because both would have shipped as plausible
errors:

- **`bg-gradient-to-*` does not exist in Tailwind v4** — not deprecated, *removed*, with no
  compatibility alias. It is `bg-linear-to-*`
  ([v4 release notes](https://tailwindcss.com/blog/tailwindcss-v4);
  [background-image](https://tailwindcss.com/docs/background-image)). Writing the v3 name produces
  no class at all, silently.
- **Mask utilities need Tailwind ≥ 4.1.0**, not merely "v4" — they landed in
  [v4.1.0](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.1.0). A project on 4.0.x gets
  nothing from `mask-*`.

---

## 1. The asset hierarchy — prefer the cheapest, most specific option

| Tier | Asset | Reach for it when |
|---|---|---|
| **1** | **Product screenshot**, framed in browser chrome | Any hero or feature section for a product that exists. **Specific and true beats decorative** |
| **1** | **Data-viz** (validated chart tokens) + **Lucide icons** | Stats, metrics, capability grids — see [data-viz.md](data-viz.md) |
| **2** | **Brand-geometric decoration** (§4) | Backgrounds, section transitions, and every surface with nothing to screenshot |
| **3** | **Generated designed graphic** — Canva brand template, exported (§3a) | A banner, feature graphic, social card or brand motion clip. It **inherits** the brand kit rather than being prompted toward it |
| **4** | **Generated illustration** — a metered model, per call (§3a) | A *concept* with nothing to depict and nothing to compose from. Costs money per attempt |
| **5** | **Commissioned illustration** | Flagship brand moments only |

**The ordering principle is specificity first, then cost.** A real screenshot of the actual product tells a
visitor something no illustration can: that the thing exists and looks like that. The strongest B2B
SaaS marketing works almost entirely in tiers 1–2, and the corpus audit found the same shape — the
SaaS landing hero's primary trust device is a browser-chrome-framed product screenshot, not artwork.
*(That is our reading of the corpora, not a published finding.)*

**Three rules apply across every tier:**

1. **Never mix illustration styles on one site.** One set, or none.
2. **Recolour any third-party set to role tokens**, so it cannot clash with a brand pack.
3. **Decoration is never load-bearing for meaning** — if removing it loses information, it was not
   decoration. See §8.

---

## 3a. Generated assets — tiers 3 and 4, and why they are ordered that way

The system **can** now reach for a generated asset, and the order is not arbitrary: it is
cheapest-and-most-brand-faithful first. Tier 3 **inherits** the brand; tier 4 is **prompted toward** it
and may miss.

| | tier 3 — designed graphic | tier 4 — generated illustration |
|---|---|---|
| produces | banners, feature graphics, social cards, MP4/GIF brand motion | illustration, texture, photographic concept |
| brand fidelity | inherited from a brand kit | prompted, and *hoped for* |
| marginal cost | none on an existing subscription | **per call**, every attempt |
| reach for it | the asset can be **composed** | the asset must be **imagined** |

That last row is the whole distinction. A design tool assembles from parts you gave it; a diffusion
model invents. If the thing you need can be composed, composing it is both cheaper and more faithful.

### Tier 3 is exported assets only — never a page

A design tool that can build whole pages **must not** be used to build one. Its page output is a hosted
artifact that cannot be exported as code (its export formats are PDF, JPG, PNG, PPTX, GIF, MP4, CSV —
there is no HTML), it uses none of our role tokens, and no gate we ship can see it. A page authored
there is a **fork of the design system**, which this file's own *"a pack is a theme, not a fork"* rule
forbids.

So the contract is narrow: **an exported asset that lands in `app/assets/` and is referenced by a view
we own.** Layout stays in Rails views built from primitives, always.

### Tier 4 is metered, and the ceiling has to refuse

- The ceiling is **checked before the call that would cross it**, never after. A limit enforced on the
  way out is a receipt.
- **An unset ceiling means refuse**, not unlimited. A budget defaulting to infinity is not a budget.
- **A reroll is a full charge.** Where a provider bills all-or-nothing, a *failed* generation is free
  but a *completed but unusable* one is paid for. So the prompt is composed from the surface class
  (`art-direction.md` §3) and the brand pack — never improvised. The cheap prompt is not the short one;
  it is the one that does not need rerolling.

### No provider configured — the rule that has not changed

Absent a working provider, behaviour is exactly as before: **satisfy the surface from tiers 1–2, or say
so and stop.** Name the surface and what the tiers could not carry. Never a placeholder, never stock
art, never a hand-rolled "illustration". A half-configured setup must say *which* thing is missing
rather than reporting the capability absent.

### The drift hazard, named because it cannot yet be gated

Tier 2 derives its identity from **`brand.json`**. Tier 3 inherits its identity from the **design
tool's own brand kit**. Those are two sources of truth for one brand, feeding adjacent surfaces on the
same page.

**`brand.json` is authoritative.** It is the copy under version control and under gate; the external
kit is a **mirror that must be checked**, not a second original. When they disagree, the pack wins and
the kit gets corrected.

This is **not gated** — the external kit's contents live behind a connector and not in the repo, so
nothing here can read both and compare. That is a real limitation, stated rather than papered over:
naming an ungated hazard is honest, implying it is gated would not be.

## 2. Tier 1 — product screenshots

### The frame

A screenshot floating on a page reads as a bug report. Frame it, and the frame is markup, not part of
the image — so it inherits the theme, stays crisp at any density, and costs no pixels.

```erb
<figure class="stack" style="--space: var(--space-2xs)">
  <div class="rounded-lg border border-border bg-card shadow-lg overflow-hidden">
    <div class="cluster gap-1.5 border-b border-border bg-muted px-3 py-2" aria-hidden="true">
      <span class="size-2.5 rounded-full bg-border"></span>
      <span class="size-2.5 rounded-full bg-border"></span>
      <span class="size-2.5 rounded-full bg-border"></span>
    </div>
    <picture>
      <source srcset="<%= image_path('marketing/dashboard.avif') %>" type="image/avif">
      <source srcset="<%= image_path('marketing/dashboard.webp') %>" type="image/webp">
      <%= image_tag 'marketing/dashboard.png',
            alt: 'The work-order dashboard: 12 open jobs grouped by engineer, each showing its SLA timer.',
            width: 2560, height: 1600, decoding: 'async', class: 'w-full h-auto' %>
    </picture>
  </div>
  <figcaption class="text-step--2 text-muted-foreground"><%# optional — what the reader is looking at %></figcaption>
</figure>
```

**The chrome bar is `aria-hidden`** because three dots are pure ornament (§8). The screenshot itself
is **not** — see below.

### Alt text: a screenshot is almost never decorative

WCAG **1.1.1 Non-text Content** requires a text alternative that *"serves the equivalent purpose"*
([Understanding 1.1.1](https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html)). A hero
screenshot is making an argument, so `alt="Screenshot of the dashboard"` fails it — that describes
the *file*, not the *claim*. Describe **what it shows that matters**, as the example above does. Only
a screenshot that repeats adjacent copy verbatim is decorative, and then it takes `alt=""`.

### Delivery — formats, and the two performance rules

**Format order is significant**: the browser takes the **first** matching `<source>` in document
order ([MDN `<picture>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/picture)),
so AVIF must precede WebP, which must precede the `<img>` fallback.

| Format | Baseline status (checked 2026‑07‑31) | Role |
|---|---|---|
| **AVIF** | **Newly available** (since 2024‑01‑25) | Best compression; first `<source>` |
| **WebP** | **Widely available** (since 2023‑03‑16) | The safe fallback that covers essentially everyone |
| **PNG** | Universal | Final `<img>` fallback |

*Do not describe AVIF as "widely available" — it has not reached that Baseline tier yet.* The `<img>`
fallback is **PNG rather than JPEG for UI screenshots** — that one is **our call**: screenshots are
sharp-edged text and 1px borders, which is exactly what JPEG's DCT smears.

**Two rules that are easy to get backwards:**

- **`width` and `height` on the `<img>` are mandatory.** They let the browser compute the aspect
  ratio before the bytes arrive, *"reducing or even preventing a layout shift"*
  ([MDN `<img>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/img)). Give the
  intrinsic pixel size and let `w-full h-auto` scale it.
- **Never `loading="lazy"` a hero screenshot.** It is usually the LCP element, and web.dev is
  explicit: *"Don't lazy-load images that are likely to be in-viewport when the page loads,
  especially LCP images"* ([web.dev](https://web.dev/articles/lazy-loading-images)). Lazy-load
  screenshots **below** the fold; leave the hero eager. `decoding="async"` is fine on both.

### Capturing them deterministically

Screenshots go stale, and a hand-captured one carries whatever window size, theme and half-open menu
the author had. Automate it — the project already declares how to boot itself in qa-flow's
`qa/qa.config.yml` `app:` block (`start`, `port`, `health`, `boot_timeout`), so **read that rather
than inventing a second launch mechanism.**

```js
// script/marketing_shots.mjs — run against the app booted per qa.config.yml `app:`
import { chromium } from 'playwright';

const SHOTS = [
  { name: 'dashboard', path: '/dashboard', clip: { x: 0, y: 0, width: 1280, height: 800 } },
];

const browser = await chromium.launch();

for (const scheme of ['light', 'dark']) {
  // deviceScaleFactor is a CONTEXT option, not a screenshot option — 2 gives a retina capture.
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    colorScheme: scheme,
  });
  const page = await context.newPage();

  for (const shot of SHOTS) {
    await page.goto(`${process.env.QA_BASE_URL}${shot.path}`, { waitUntil: 'networkidle' });
    await page.screenshot({
      path: `app/assets/images/marketing/${shot.name}-${scheme}.png`,
      clip: shot.clip,
      animations: 'disabled',
    });
  }
  await context.close();
}

await browser.close();
```

Four things in there are load-bearing, all verified against
[Playwright's docs](https://playwright.dev/docs/api/class-page#page-screenshot):

- **`animations: 'disabled'`** — *"stops CSS animations, CSS transitions and Web Animations"*;
  finite animations are fast-forwarded to completion and infinite ones are cancelled to their initial
  state. This is what makes a capture reproducible instead of catching a mid-transition frame.
- **`colorScheme`** is a **context** option and emulates `prefers-color-scheme`, so light and dark
  come from the same script. Our dark mode is `.dark`-class driven with a pre-paint script reading
  `localStorage`, so **verify the project actually flips** — if it keys only off the class, set it
  explicitly rather than trusting the media feature.
- **`deviceScaleFactor`** is a **context** option too, not a `screenshot()` one. This is the usual
  mistake.
- **You do not need to wait for fonts.** Playwright already awaits `document.fonts.ready` inside
  `screenshot()` by default — a manual `waitForFunction(() => document.fonts.ready)` is redundant.

**Do not combine `clip` with `fullPage`.** They conflict; pick one. And per the qa-flow evidence
rule, a clipped region beats an 8000px full-page capture for anything but a whole-page shot.

> **Scope note.** No shared capture harness ships today —
> [#105](https://github.com/fmanimashaun/claude-skills/issues/105) is still open. The script above is
> self-contained on purpose. When that harness lands, this recipe should call it rather than
> duplicating it.

---

## 3. Tier 1 — data-viz and icons

For stats, metrics and capability grids the answer is already written: the validated
`--color-chart-*` palette and the KPI/chart recipes in [data-viz.md](data-viz.md), and Lucide icons
per [brand.md](brand.md). **A real chart of real numbers outranks any decoration**, which is why this
sits at tier 1 alongside screenshots rather than below it.

Never colour decoration from the chart tokens. They carry categorical meaning; spending them on
ornament makes the meaning ambiguous exactly where a reader is trying to decode a legend.

---

## 4. Tier 2 — brand-geometric decoration

The distinctive part, and the reason this system does not need an illustrator.

The `fidara` mark is a **3-facet prism** plus a signal-orange accent bar. That is not merely a logo —
it is a **generative geometric system**. Decoration is derived from it in pure CSS, so there is no
asset pipeline, no export step, nothing to keep in sync, and it is **brand-parameterised by
construction**.

### 4.1 The decoration token contract

Decoration cannot name `fm-*` primitives. [brand.md](brand.md) is explicit that components consume
**roles only**, that a pack may name its primitives anything, and that `Ui::Logo` is the *one*
component permitted literal colours. Hard-coding cerulean into a background would make every client
pack render fidara's brand behind its own content.

So decoration reads **four optional custom properties, each with a role fallback**:

```css
/* In the PACK's theme.css :root — the one place naming a primitive is legal. */
:root {
  --decor-1: var(--color-fm-cerulean);   /* prism facet — left  */
  --decor-2: var(--color-fm-electric);   /* prism facet — right */
  --decor-3: var(--color-fm-cyan);       /* prism facet — top   */
  --decor-accent: var(--color-fm-orange);/* the 3px signal bar  */
}
```

**A pack that declares none of them still works.** Every recipe below reads
`var(--decor-1, var(--primary))`, so the fallback is a monochromatic composition built from the
pack's own primary — restrained, on-brand, and never a stock colour.

*These are deliberately **not** added to the role contract.* Verified against
`plugins/design-flow/scripts/brand_pack_lint.py`: the lint requires only the roles in its fixed
`ROLES` list, derives `-foreground` companions from that same list, and takes `DARK_REQUIRED` from a
fixed list too — so **extra `:root` properties are accepted today with no plugin change**, while
adding them as *required* roles would fail every existing pack. The same check is why they are not
`brand.json` fields: that manifest warns on unrecognised keys with *"a pack is colours + logo"*.

### 4.2 Recipe — facet mesh

The workhorse: a large, low-opacity wash using the three facet hues as stops. Layered radial
gradients read as depth in a way a single linear gradient does not.

```css
@utility decor-mesh {
  background-image:
    radial-gradient(60% 80% at 15% 20%, color-mix(in oklab, var(--decor-1, var(--primary)) 28%, transparent), transparent 70%),
    radial-gradient(50% 70% at 85% 10%, color-mix(in oklab, var(--decor-2, var(--primary)) 22%, transparent), transparent 70%),
    radial-gradient(70% 60% at 60% 90%, color-mix(in oklab, var(--decor-3, var(--primary)) 18%, transparent), transparent 70%);
}
```

`color-mix()` rather than an opacity utility, because the element itself must stay opaque — putting
the transparency in the *colour* keeps text layered above it at full contrast.

In Tailwind, the equivalent inline form uses **v4** syntax:
`bg-linear-to-br from-(--decor-1) via-(--decor-2) to-(--decor-3)`. Note the **parentheses**:
`from-(--decor-1)` is the documented shorthand that wraps the token in `var()` for you, whereas
`from-[--decor-1]` emits the raw token and silently does nothing
([adding custom styles](https://tailwindcss.com/docs/adding-custom-styles)). `bg-radial` and
`bg-conic` are available in v4 too, should a composition want them.

### 4.3 Recipe — angled section divider

The repeatable transition device between tonal sections. One shared cut depth, so every divider on
the site agrees instead of each section picking its own.

```css
@theme { --decor-cut: 3rem; }   /* the cut depth; a pack may re-cut it */

@utility decor-divider-b {
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - var(--decor-cut)), 0 100%);
}
@utility decor-divider-t {
  clip-path: polygon(0 var(--decor-cut), 100% 0, 100% 100%, 0 100%);
}
```

**The knob is a depth, not an angle, and that is deliberate.** It is tempting to express this as the
prism's shoulder angle — but a `clip-path` polygon takes points, so a fixed *angle* would need the
section's width to resolve, and the width is fluid. A fixed **depth** gives every divider on the site
the same visual weight at every viewport, which is the property we actually want; the resulting angle
varies, and that is fine.

Apply to the **section**, not to a spacer element — a divider that is its own element is one more
thing to keep in sync with the section's background.

### 4.4 Recipe — blurred beams

Large, soft, off-canvas shapes in brand hues. Both reference corpora use this; the difference is
that ours are in *our* palette.

```css
@utility decor-beam {
  position: absolute;
  inline-size: 40rem; block-size: 24rem;
  border-radius: 9999px;
  background: color-mix(in oklab, var(--decor-2, var(--primary)) 35%, transparent);
  filter: blur(96px);
  pointer-events: none;
}
```

**Budget: at most two beams per page, and never inside a scroll container.** Blur is genuinely
expensive to paint, not folklore — web.dev's paint-complexity guidance states that *"anything that
involves a blur (like a shadow, for example) is going to take longer to paint than, say, drawing a
red box"* ([web.dev](https://web.dev/articles/simplify-paint-complexity-and-reduce-paint-areas)).
Repainting a 96px blur on every scroll frame is how a marketing page ends up janky on a mid-range
phone.

**Do not reach for `will-change` to fix that.** MDN is direct: it is *"intended to be used as a last
resort to try to deal with existing performance problems"*, and excessive use *"will result in
excessive memory use"* ([MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/will-change)). Remove
a beam instead.

### 4.5 Recipe — edge accent

The 3px signal bar from the lockup, reused as a section marker. The cheapest way to make a page feel
deliberate.

```css
@utility decor-edge {
  border-inline-start: 3px solid var(--decor-accent, var(--primary));
}
```

Used on a pull-quote, a highlighted card, or the leading edge of a stats band — sparingly. `brand.md`
already governs the accent as a restraint colour; three of these on one screen spends it.

---

## 5. Motion for decoration — two named patterns

**Both names are introduced here.** [#135](https://github.com/fmanimashaun/claude-skills/issues/135)
refers to `gradient-drift` and `reveal-on-scroll` as though they were established patterns; they
appear **nowhere** in this repo. Rather than propagate names with no definition, they are defined
below, built from the tokens `motion.md` already ships, and renamed to the `decor-` prefix so it is
obvious which layer they belong to.

Everything in [motion.md](motion.md) still governs: two curves, distance-chosen durations, a
departure shorter than an arrival, and reduced motion changing the *behaviour* rather than only the
timing.

### 5.1 `decor-settle` — a one-shot arrival, deliberately not an ambient loop

```css
@theme {
  --animate-decor-settle: decor-settle 1200ms var(--ease-out) both;
  @keyframes decor-settle {
    from { opacity: 0; transform: translate3d(0, 1.5rem, 0) scale(0.98); }
    to   { opacity: 1; transform: none; }
  }
}
```

The `@keyframes` is **nested inside `@theme`** alongside its `--animate-*` variable — that is where
Tailwind v4 looks for it ([animation docs](https://tailwindcss.com/docs/animation)). Apply with
`motion-safe:animate-decor-settle`; `motion-safe` maps to
`@media (prefers-reduced-motion: no-preference)`
([variants](https://tailwindcss.com/docs/pseudo-class-variants)), which is the same direction
`motion.md` already gates on, and it fails safe.

**Why one-shot rather than a perpetual drift, which is what the issue asked for.** WCAG **2.2.2
Pause, Stop, Hide** applies to moving content that *(1)* starts automatically, *(2)* **lasts more
than five seconds**, and *(3)* is presented in parallel with other content — all three, together
([Understanding 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)). An
infinite background drift behind a hero satisfies all three, so it would need a **pause control** —
and `prefers-reduced-motion` is *not* that control; it is a different accommodation for a different
user. A 1.2s settle never engages the criterion at all.

If a project genuinely wants perpetual ambient motion, it owes the page a pause affordance. We do
not ship one, so we do not ship the loop. **This is a deliberate departure from #135, recorded
here.**

### 5.2 `decor-reveal` — content-safe scroll reveal

The dangerous one, because the obvious implementation breaks the page. A reveal written as
`opacity: 0` in CSS, promoted to `1` by JavaScript, **hides the content permanently** if the observer
never runs — a JS error, a slow parse, an unsupported browser, a bot. Content is not allowed to
depend on a script.

So: **the hidden state is applied by the script itself**, meaning no-JS renders fully visible.

```js
// app/javascript/controllers/reveal_controller.js
import { Controller } from '@hotwired/stimulus';

export default class extends Controller {
  static values = { stagger: { type: Number, default: 80 }, max: { type: Number, default: 1600 } };

  connect() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const items = Array.from(this.element.children);
    // motion.md §7: per-child delay x count must fit the cap, or a long list becomes a wait.
    const step = Math.min(this.staggerValue, this.maxValue / Math.max(items.length, 1));

    items.forEach((item, index) => {
      item.dataset.revealState = 'pending';
      item.style.transitionDelay = `${Math.round(index * step)}ms`;
    });

    this.observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.dataset.revealState = 'shown';
        this.observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -10% 0px' });

    items.forEach((item) => this.observer.observe(item));
  }

  disconnect() {
    this.observer?.disconnect();
  }
}
```

```css
@media (prefers-reduced-motion: no-preference) {
  [data-reveal-state] {
    transition: opacity var(--duration) var(--ease-out), translate var(--duration) var(--ease-out);
  }
  [data-reveal-state="pending"] { opacity: 0; translate: 0 10px; }
  [data-reveal-state="shown"]   { opacity: 1; translate: none; }
}
```

Three properties worth naming: the enter values are `motion.md` §3's (`opacity 0→1`, `translateY
10px→0` — and **scale never starts at zero**); the stagger is capped per §7; and the early `return`
under reduced motion means no `data-reveal-state` is ever written, so the content simply *is* there.
Style off `data-*` rather than toggling utility classes, per `interaction-stimulus.md`.

---

## 6. Per-surface prescriptions — the pages with nothing to screenshot

This is where the visual gap is widest, and it is exactly where convention reaches for illustration.
On these surfaces there is no product to show and little copy, so **tier 2 and expressive typography
become primary rather than fallback**, and motion carries proportionally more weight because there is
less to look at.

| Surface | Primary visual | Motion | Notes |
|---|---|---|---|
| **Auth — split** | `decor-mesh` panel (facets at large scale) behind the value-prop column | `decor-settle` on the panel only | A product screenshot may replace the panel *if* the product exists. **Never decorate behind the inputs** — the form column stays visually quiet |
| **Auth — focused** | `Ui::Logo` at `lg` + generous whitespace. **No decoration** | none | The card *is* the composition; decoration here reads as clutter |
| **404 / 500** | **Expressive typography** — the numeral at `text-step-5` in the display face, paired with one `decor-beam` | `decor-settle`, nothing scroll-based | Type + geometry, not character art. One clear recovery action |
| **Maintenance** | Same family as 404, plus status and ETA when known | none | Reassurance beats decoration. **No spinner** — it implies this finishes in seconds |
| **Empty state** | The shipped icon-chip idiom, scaled up (§6.1) | none | Cheap, and stylistically consistent *by construction* — which is the whole reason it beats a spot illustration |
| **Pre-launch hero** | Brand-geometric composition, typography-led | `decor-settle` + one `decor-reveal` group | With no product, the mark and the type *are* the visual |

Auth and error pages already have anatomies in
[page-anatomies.md](page-anatomies.md) — those govern structure and copy; this governs what fills the
space. Note that the focused-auth row *agrees* with that file's existing recipe (`center` + a single
box) rather than adding decoration to it.

### 6.1 Empty state — an oversized icon, done the way our doctrine actually allows

The shipped idiom in `components.md` is `cover > center > stack` with an icon chip
`size-16 rounded-full bg-muted`. Scale the icon by scaling **the chip's font size**, because a Lucide
icon is `1em` and inherits `currentColor` via the `with-icon` utility:

```erb
<div class="cover">
  <div class="center stack text-center" style="--space: var(--space-s)">
    <span class="with-icon size-16 justify-center rounded-full bg-muted text-step-3 text-muted-foreground">
      <%= lucide_icon "inbox" %>
    </span>
    <h2 class="text-step-1"><%# what belongs here %></h2>
    <p class="max-w-md text-muted-foreground"><%# the one action that puts it there %></p>
  </div>
</div>
```

**`lucide_icon` takes no `size:` or `class:`** — that is a non-negotiable the self-consistency lint
enforces, and the reason is that `with-icon` sets `inline-size: 1em` while SVG presentation
attributes carry zero CSS specificity. The chip's `text-step-3` is what makes the icon big.

**Two deliberate departures from #135, both recorded.** The issue proposed `bg-primary/10
text-primary` and `size-12`:

- We keep **`bg-muted`**. The issue is right that `bg-primary/10 text-primary` is an established
  icon-chip idiom — `components.md` uses it for the stat/KPI chip (`size-10 rounded-md`), soft-filled
  badges, avatars and the active pagination link. That is exactly why it is wrong here: in every one
  of those cases the primary tint marks something **active, selected or affirmative**, and an empty
  state is the opposite — a neutral, absent condition. `components.md` already specifies `bg-muted`
  for it, so adopting the tinted chip would both overload the tint and contradict every empty state
  already built.
- We keep **`size-16`** for the chip and express "oversized" through the *icon's* font size. Changing
  the chip's dimension would contradict `components.md` for every empty state already built.

---

## 7. Tiers 3 and 4 — illustration, and why it is last

Everything above resolves to something generated from tokens the pack already declares, the display
typeface, or Lucide. That is what makes these surfaces **stylistically identical to the rest of the
system by construction** — the exact property a purchased illustration set cannot guarantee.

When illustration genuinely is the answer — a *concept* with nothing to depict, like "integrations"
or "compliance" — the rules are firm:

- **One permissively-licensed set for the whole site.** Record the licence and its attribution
  requirement next to the assets. Never mix two sets: mismatched line weights and perspectives are
  visible even to people who cannot say why.
- **Recolour to role tokens**, so a brand swap carries the illustrations with it. A set that cannot
  be recoloured is the wrong set.
- **Never load-bearing for meaning** (§8).
- **Tier 4 (commissioned) is for flagship moments only** and needs a human decision, not an agent's.

---

## 8. The accessibility contract for decoration

Short, and the whole of it:

- **Decorative inline `<svg>` → `aria-hidden="true"`** (add `focusable="false"` for legacy engines).
  The APG's [Hiding Semantics](https://www.w3.org/WAI/ARIA/apg/practices/hiding-semantics/) practice
  covers this; `role="presentation"`/`role="none"` is equivalent for decorative images.
- **Decorative `<img>` → `alt=""`.** Prefer this over `aria-hidden`: W3C's
  [decorative images tutorial](https://www.w3.org/WAI/tutorials/images/decorative/) notes
  `role="presentation"` is *"not as widely supported as using a null `alt` attribute"*.
- **Never put `aria-hidden="true"` on, or around, anything focusable.** The attribute is inherited by
  descendants, so hiding a container hides a link inside it from assistive technology while leaving
  it in the tab order — a control a screen-reader user can reach but not identify. Decoration should
  carry `pointer-events: none` and contain no interactive elements at all.
- **Decoration is purely presentational**: if removing it loses information, it is content, and it
  needs a text alternative under WCAG 1.1.1.
- **Contrast is measured against what is actually behind the text.** A mesh under body copy changes
  the effective background; if it moves, the worst frame is the one that counts. Keep decoration out
  from behind running text — put it beside, above, or far enough below.

---

## 9. Brand-parameterisation — no new pack field

A client pack gets this whole system by declaring at most the four `--decor-*` properties in its own
`theme.css`, and gets a coherent monochromatic version by declaring **nothing at all**.

**There is deliberately no `geometry_seed` in `brand.json`.** The pack already supplies everything
the geometry needs — its hues and its mark — so a new manifest field would add a value with no
consumer, and `brand_pack_lint.py` warns on unrecognised manifest keys with *"a pack is colours +
logo"*. Adding a field to doctrine that our own lint rejects is precisely the claims-vs-enforcement
defect this repo keeps catching. `--decor-cut` is the one shape knob, and it lives in CSS with the
rest of the geometry.

This preserves `brand.md`'s central claim intact: a pack is **colours, logo, and the chart-palette
proof**.

---

## 10. What we deliberately did not do

- **No ambient infinite background motion.** §5.1 — it engages WCAG 2.2.2 and would owe the page a
  pause control we do not ship.
- **No illustration in the default path**, and no illustration set vendored into the system. The
  hierarchy exists to make reaching for one a conscious, recorded choice.
- **No SVG filter effects** (`feTurbulence` grain, displacement maps). They are the most expensive
  thing you can put in a paint, and the effect is decoration on decoration.
- **No decoration behind running text.** §8 — it is a contrast problem wearing a style.
- **No `mask-*` in the recipes above**, despite masks being the natural tool for a fading mesh edge.
  They need **Tailwind ≥ 4.1.0**, and the recipes here should work on any v4. Reach for `mask-b-from-*`
  in a project you know is on 4.1+, and record the floor.
- **No new role tokens and no new `brand.json` fields.** §4.1 and §9.
- **No improvising when generation is unavailable** (#503, #507). Tiers 1–2 produce assets from the
  running product and from `brand.json`; tiers 3–4 **generate** them through a configured provider
  (§3a). What this file still refuses is the gap between those: **if no provider is configured and
  tiers 1–2 cannot serve the surface, say so and stop.** Name the surface, name what tiers 1 and 2
  could not carry, and hand the decision back. Never a placeholder, never stock art, never a
  hand-rolled "illustration", never an empty box where an asset was implied.

  This paragraph previously said the system *"produces nothing"*, which was true when it was written
  and is now false. It is **rewritten rather than deleted**, because the rule it carried — the
  improvisation ban — is the half that survives generation and matters more with it: a provider that
  is present but misconfigured is a *new* way to end up with nothing, and the honest response is the
  same one.

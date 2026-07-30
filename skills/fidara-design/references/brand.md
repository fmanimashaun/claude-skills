# Brand

**One system, N brands.** The design system is a product used for client and freelance work
(marketing sites, landing pages, corporate sites), not only for Fidara's own apps. The system
stays central; each brand adapts **on top of** it. Build once, use everywhere.

A brand is expressed as a **brand pack** — a small, self-contained unit. `fidara` is the first
pack; a client brand is another. No pack is "the default that others deviate from".

## A pack is a theme, not a fork

Treat this system the way you treat Tailwind, Bootstrap or Flowbite: **you don't re-author the
system to use it.** You set your brand's colours, bring your logo, then build with the tokens
and components as given — colour tokens, shape tokens, spacing steps, component variants — and
you stick to them.

So for a client engagement the answer is deliberately small: **their colours and their logo.**
Nothing else needs to change, and the less that changes, the more of the system you actually
get to reuse. A pack that rewrites spacing, restyles components or adds its own utilities has
stopped being a theme and become a fork — which forfeits every future improvement to the
system and is the failure mode this whole model exists to prevent.

The corollary worth internalising: **"not in the pack" is not a limitation, it is the product.**
Layout, component behaviour, a11y and interaction are solved once, centrally, and every brand
inherits the fixes.

## Two levels: pack, then variant

Getting this hierarchy right matters, because collapsing it causes real damage:

- A **pack** is a genuinely distinct brand — its own palette, fonts, and mark. `fidara` is a
  pack. A client (`acme`) is a pack.
- A **variant** lives *inside* a pack. Same design values; it differs only in **lockup and
  endorsement**. **`fmworkflows` is a variant of the `fidara` pack, not a pack of its own** —
  it is a product *under* the parent brand and keys into fidara's design system.

Why the distinction is load-bearing: fidara and fmworkflows share palette, typefaces, spacing
and mark identically. Modelling fmworkflows as a second pack would mean two byte-identical
`theme.css` files — pure duplication, and a **drift hazard**: update the parent's palette and
the product silently diverges from it. A variant cannot drift from its pack, because it has no
values of its own to drift with.

The test for which one you need: *does it re-theme, or only re-label?* Re-theme → pack.
Re-label → variant.

## What a pack changes

| A pack declares | The system owns — never in a pack |
|---|---|
| Role **values** — the palette | Role token **names** (`--primary`, `--card`, `--border`, …) |
| Logo/mark assets + lockup | Layout primitives + page archetypes |
| Chart-palette validation result | Component API (variants/sizes/states/slots) |
| | Spacing/type scale, a11y rules, responsive doctrine, interactions |
| | The type *roles* (`sans` / `display` / `mono`) |

That is the entire surface: **colours, logo, and the proof the chart hues still work.**

Chart-palette validation is the one result that cannot be inherited even when the hues are:
changing the palette changes the **surface** those hues sit on, and hues that clear contrast on
fidara's navy can fail on a client's light beige. One command, not a re-authoring job — see
*Chart palette*.

### Escape hatch — rare, and it costs you something

Three things *can* be overridden when a brand genuinely demands it: `fonts`, the three
personality `knobs` (section rhythm, control radius, heading ramp), and `chart_hues`. Omit them
and they inherit fidara's calibrated defaults, which is the normal case.

Reach for these sparingly and record why. Every override is a place your brand stops matching
the system, so it is a place future system improvements land differently — or not at all. The
slots exist because a brand occasionally needs a softer radius language or a different
typeface, **not** because a pack is expected to restate them.

### Primitives are private to a pack; the role layer is the public API

This is the rule that makes a brand swap a single `@theme` layer instead of a refactor:

- **Components consume roles only** — `bg-primary`, `text-muted-foreground`, `border-border`.
  A component never names a primitive, so it never names a brand.
- **A pack may name its primitives anything.** `--color-fm-cerulean` is *fidara's private
  choice*, not system law. A client pack is free to use `--color-acme-*`, or no prefix at all.
  Nothing outside the pack may reference a primitive by name.
- Therefore the **contract is the role names**, and it is mechanically checkable — see
  *Completeness lint* below.

The one documented exception: the **logo mark's facet hues are fixed brand colors**, because a
mark is not themeable. `Ui::Logo` is the only component permitted to carry literal colors.

## Pack anatomy

```
brands/<slug>/
  brand.json     manifest — identity + variants (+ optional font/knob/hue overrides)
  theme.css      the @theme layer: primitives -> role mapping -> .dark re-points
  assets/        logo/mark SVGs (mark, lockup, reversed, monochrome)
```

### `brand.json`

**A typical client pack — the whole manifest.** Colours live in `theme.css`; this is the rest:

```json
{
  "slug": "acme",
  "name": "Acme Corp",
  "chart_palette_validated": true,
  "variants": { "acme": { "name": "Acme Corp", "endorsement": null, "mark": "mark.svg" } }
}
```

No `fonts`, no `knobs`, no `chart_hues` — all inherited. That is the shape of most client work.

**The `fidara` pack, which overrides everything it calibrated**, and carries a product variant:

```json
{
  "slug": "fidara",
  "name": "Fidara",
  "fonts": { "sans": "Bricolage Grotesque", "display": "Newsreader", "mono": "Overpass Mono" },
  "knobs": { "section_rhythm": "generous", "radius": "md-controls-lg-cards", "heading_ramp": "mid-range" },
  "chart_hues": ["#0077CC", "#00A3FF", "#00D4FF", "#FF6B35", "#22C55E"],
  "chart_palette_validated": true,
  "default_variant": "fmworkflows",
  "variants": {
    "fidara":      { "name": "Fidara",      "endorsement": null,        "mark": "prism.svg" },
    "fmworkflows": { "name": "fmworkflows", "endorsement": "by Fidara", "mark": "prism.svg" }
  }
}
```

**Required:** `slug`, `name`, `chart_palette_validated: true`, and `variants` with at least one
entry. **Optional overrides:** `fonts`, `knobs`, `chart_hues`, `default_variant`.

- `variants` — each carries only what re-labelling needs: display `name`, the `endorsement`
  string (or `null`), and which `mark` asset to use. **No variant carries values**, which is
  exactly what makes drift from its parent impossible. A single-brand pack declares one
  variant with `endorsement: null`.
- `endorsement` replaces the old two-value `fidara | fmworkflows` switch. Because it is a
  variant field, a client's "a Foo company" endorsement needs no code change.
- `chart_palette_validated` must be `true` — see *Chart palette*; it is the one result that
  cannot be inherited.

Selection is `<pack>` or `<pack>:<variant>` — `fidara:fmworkflows` is the product surface,
`fidara:fidara` the parent. Omitting the variant uses `default_variant`, else the sole variant.

### `theme.css`

Exactly the three tiers from [foundations-tokens.md](foundations-tokens.md), in order:
primitives in `@theme`, roles in `:root` + `@theme inline`, then `.dark` re-points. Nothing
else belongs in a pack — no component CSS, no utilities, no layout rules. If a pack needs to
change a component, the component is wrong, not the pack.

## Personality knobs (per-brand, `fidara` values shown)

Three axes are **brand-level choices, not system law.** They were decided for fidara after
measuring two reference corpora that genuinely disagree on them; another brand may choose
differently without touching a single component.

| Knob (`brand.json`) | `fidara` | Alternative |
|---|---|---|
| `section_rhythm` | `generous` — `--space-section` 96→128px | `compact` — 64→96px, for dense/utilitarian brands |
| `radius` | `md-controls-lg-cards` — controls `rounded-md`, cards `rounded-lg`, pills `rounded-full` | `soft` — all-`rounded-lg` (friendlier, more consumer); set `--radius` + the control radius together |
| `heading_ramp` | `mid-range` — `step-1`/`step-2` for card/section headings | `hero-heavy` — body jumps to `step-4`/`5` (more drama, less hierarchy) |

Because components consume **roles and scale steps** (never literal values), changing a knob
is a token edit inside the pack. This is what resolves the "choose one" tension from Phase 0:
the *default* is decided, the *system* supports both.

## Completeness lint (mechanical, not aspirational)

A pack that omits a role the components consume would let that role fall back to a stock
Tailwind color — a silent, brand-breaking default. So completeness is checked, not trusted:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/brand_pack_lint.py brands/<slug>
```

It verifies that `theme.css` defines **every role** in the contract, that surface roles have
their `-foreground` companion and a `.dark` re-point, that no `var()` points at an undefined
primitive, and that `brand.json` is complete with `chart_palette_validated: true`. A pack is
not finished until this exits 0.

**What the lint cannot prove — and what to do about it.** It checks a pack against the role
contract; it cannot check the contract against reality. If a pack lints clean but a surface
still renders a **stock Tailwind colour** in a real app, the contract itself is missing a role
the components consume — and every future pack inherits that hole. That is a doctrine defect,
not a project problem: report it with `/rails-flow:report` (component `design-flow` /
`fidara-design`), naming the utility that rendered unbranded, so the contract and the lint are
fixed upstream. The same applies to a missing `.dark` re-point that the lint accepted, or a
`Ui::Logo` endorsement on the wrong variant. First real run of a new pack **is** the
verification step — see the checklist in `/design-flow:setup`. Two subtleties the lint encodes, both easy to get wrong by
hand: `--background`'s companion is `--foreground` (not `--background-foreground`), and the
feedback roles plus `--ring` are deliberately **not** re-pointed on dark — requiring a dark
value for all 22 roles would be a wrong check.

## Chart palette — re-validate per pack

Running the palette validator is **part of creating a pack**, never a one-off inherited from
fidara. Hues that separate cleanly on fidara's navy surface may collide on another brand's.
See [data-viz.md](data-viz.md) for the validator and the ΔE / contrast bars it enforces.

## Distribution — everything you need is already public

**There is no private plugin to install.** This skill is complete on its own, and that is the
only mode: components are built **just-in-time in the project** from the doctrine here plus
[coverage.md](coverage.md), which names what to build each one from. Nothing at build time reads
a licensed design kit.

- The client repo contains only the **generated components** — original authorship,
  brand-parameterized — plus their brand pack.
- A client deliverable is therefore **their app + their brand pack**. Not the toolchain.
- **The licensed kits are never distributed at all.** Tailwind Plus / Flowbite licences cover
  *us building for clients*; they do not cover handing anyone a redistributable kit — and they
  forbid re-distributing components separately from an End Product, which a plugin payload would
  be. The kits inform *our doctrine* at authoring time, on a maintainer machine, and never travel
  further.
- **If an agent ever seems to need the kit to build a screen, that is a defect in this skill, not
  a missing download.** It means a `coverage.md` row is marked `derivable` when it is really
  `needs doctrine` — report it rather than working around it.

An earlier revision of this section told you to install a private `fidara-ui` plugin. That was
written under an inventory model, where the kit was a library agents referenced while building.
The just-in-time model replaced it: a kit-present branch would make the same prompt produce
**different output depending on whether a licensed plugin happened to be installed** — a
non-determinism nobody without the licence could even test. See the decision record on
[#190](https://github.com/fmanimashaun/claude-skills/pull/190#issuecomment-5127664883).

## The Prism mark (the `fidara` pack)

A single 3-facet prism — **left = cerulean `#0077CC`, right = electric `#00A3FF`, top = cyan
`#00D4FF`** — the three facets denote the three product modules (FM / IT / Fleet). Exact SVG
paths live in `01-logos/DESIGN-SPECIFICATIONS.md`. Full brand assets live per-repo under
`docs/design-system/brand-assets/`; the canonical superset is in
`fidara-solutions/fidara-platform`.

- Wordmark: **Bricolage Grotesque Black (900)**, uppercase, tight tracking, `foreground` on
  light / `fm-slate-50` on dark.
- Signal-orange accent bar: 3px, from the prism's left edge to center.
- **Clear space** = 1.5× prism height. **Min sizes:** prism 20px digital / 6mm print; lockup 140px.
- **Don'ts:** never stretch/rotate/recolor individual facets; no drop-shadows/glows/bevels; no
  reduced opacity except intentional watermarks. Variants: full-color · reversed · monochrome ·
  outline (watermark) · white (busy backgrounds).

The `fidara` pack carries two variants because the product and the parent differ only in
labelling. `fmworkflows` (the product) sets `endorsement: "by Fidara"` for marketing surfaces
and renders the mark + wordmark alone in product chrome; `fidara` (the parent) sets
`endorsement: null` — a parent does not endorse itself. That direction matters: the endorsement
exists to tie a **product** to its parent, so it belongs on the product variant. Expressing it
as a per-variant *string* rather than a boolean over two brand names is what makes it correct by
construction, and what lets a client's "an Acme company" endorsement work with no code change.

## Iconography

**Lucide** icons everywhere. Default **20px** (16 compact / 24 large), **stroke 1.5**,
`fill/stroke: currentColor` so they inherit text color; size to text with the `with-icon`
utility (`svg { size: 1em }`). Icons may take a module color only when denoting module
context. Icon choice is system-level; a pack does not swap icon sets.

## Typography roles (see foundations-tokens.md for the scale)

Families are a **pack field** (`brand.json` → `fonts`); the three *roles* are invariant:

- `--font-sans` — ~90% of text: UI, body, headings. (`fidara`: Bricolage Grotesque)
- `--font-display` — brand/marketing moments and the italic tagline only. (`fidara`: Newsreader)
- `--font-mono` — reference numbers (e.g. `WO-0142`), SLA timers, code, timestamps.
  (`fidara`: Overpass Mono)

Tracking: headings `-0.02em`; all-caps labels `+0.05–0.1em`; `antialiased`.

## Voice / meta (for marketing copy, not product chrome)

Per-pack. For `fidara`: Fidara Solutions Ltd. Etymology **Fi** (use) + **ara** (Yoruba:
magic); fmworkflows tagline "Operations, engineered." Keep product UI free of marketing
lines — endorsement and taglines are marketing-surface only, for every pack.

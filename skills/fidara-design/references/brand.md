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
entry. **Optional overrides:** `fonts`, `knobs`, `chart_hues`, `default_variant`, `wordmark`.

**`wordmark` is a PACK property, never a variant's** (#771). A variant re-*labels* — `name`,
`endorsement`, `mark`, and nothing else — so a second published lockup such as a landscape logo has
nowhere to live on it. Before this, a pack shipping one carried a permanent *"not referenced by any
variant"* warning it could never clear, and a warning nobody can clear is one everybody learns to
ignore, which costs more than the orphan detection it buys. It names one `.svg` in `assets/`, is
validated for existence exactly like a `mark`, and is then counted as referenced. **An asset named
by neither a variant nor the wordmark is still reported** — the check was narrowed, not disabled.

**A single-value feedback role cannot serve both grounds** (#775). `--success`, `--warning`,
`--info`, `--signal` and `--destructive` are declared once and inherited by `.dark` unless
re-pointed — and a value tuned dark enough to read on a light ground is too dark to read on a dark
one. Both shipped packs prove it from opposite sides: fidara's bright hues clear dark and fail
light; reliance's, darkened for 1.4.3 in light, clear light and fail dark. **Neither is a defect in
the pack** — it is what one value for two grounds means.

So the contract is: **re-point a feedback role in `.dark` whenever it must be legible there**, the
same way surfaces already are. Two roles are enforced, at the two thresholds WCAG actually states:

| role | clause | floor | why |
|---|---|---|---|
| `--ring` | **1.4.11** non-text | **3:1** | a focus indicator is a UI component state |
| `--*-ink` | **1.4.3** text | **4.5:1** | an `-ink` role exists to *be* text — that is why `--success-ink` was added beside `--success` |

The **base** feedback roles are deliberately not enumerated against the page. They serve as fills,
borders or icons depending on the component, so the right threshold depends on a usage the token
file cannot see — and picking one would fail both shipped packs for a rule neither clause states.
Judge those on the rendered component, where `/design-flow:audit` pass 3 already looks.

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
value for every role would be a wrong check.

## Starting a pack when the client has no palette

A new client routinely arrives with a logo and a vibe and nothing else, and a pack cannot be
finished without a palette. So there is a **small, measured candidate set** — ten palettes, each
a complete role mapping for light *and* dark, every text pair measured against WCAG 1.4.3.

**It is a starting point for client onboarding, not a style menu for fidara's own products.**
That distinction is the whole design. This system is prescriptive on purpose — one radius
language, one type scale, one component API — because consistency is what a client is buying.
A catalogue of hundreds of looks would undo exactly the drift-killing this skill exists to do.
Ten exist to make the first hour fast and correct; after that a pack has **one** palette, like
every other pack.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py --list
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py --emit harbor --out brands/acme
```

### Choosing one — a decision path, not a gallery

Walk it in order and stop at the first answer. Do not browse.

1. **Does the client have a logo with a colour that must be echoed in the UI?**
   Yes → skip the catalogue entirely and take the *snap* path below. No → continue.
2. **Must the product recede behind the client's own content or imagery?**
   Yes → `graphite`. It is the brand-light option: a near-black primary that does not compete.
3. **Match the logo's hue family.** blue → `harbor` (quiet) or `cobalt` (loud) · indigo/blue-violet
   → `indigo` · green → `pine` · teal/cyan → `teal` · purple → `amethyst` · red/burgundy →
   `garnet` · orange/amber → `ember` · brown/rust → `clay`.
4. **Tie-break on formality, using the neutral temperature.** `cool` neutrals read corporate and
   clinical; `warm` neutrals read human and unhurried; `pure` neutrals read contemporary and
   product-y. `--list` prints each candidate's ramp.
5. **One caution that is not taste.** A green or red brand sits next to the `success` and
   `destructive` roles. Neither is disqualifying, but it makes SC 1.4.1 (colour is never the only
   signal) load-bearing rather than nice-to-have — the icon + label rule is already mandatory, so
   just do not weaken it.

### The client DOES have brand colours — snap, measure, report

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py --snap "#C8102E" --neutral warm
```

It maps their colour onto the role structure, measures every text pair in both modes, and where
their colour cannot carry a role it reports the **nearest passing colour of the same hue** with
both numbers. That last part is the point: *"your red is 3.1:1 on white, the nearest passing one
of the same hue is #A8102A at 4.6:1"* is a conversation, whereas *"it fails"* is an argument.

**Their logo keeps their exact colour.** WCAG 1.4.3 exempts logotypes, and a mark is not
themeable — that is already the documented exception for `Ui::Logo`. What moves is the `--primary`
*role*, which is text and buttons.

Edited the pack afterwards? The numbers in its header are now stale. Re-measure it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py --measure brands/acme
```

### The bar, and where it comes from

Every candidate clears **4.5:1** on each text pair in both modes — WCAG 2.2 SC 1.4.3 (Level AA),
*"The visual presentation of text and images of text has a contrast ratio of at least 4.5:1"*
([spec](https://www.w3.org/TR/WCAG22/#contrast-minimum)). The 3:1 allowance is for **large-scale**
text only (≥18pt, or ≥14pt bold), and every pair measured here is body-sized in at least one
documented use, so the stricter number is the honest one.

Deliberately **not** gated: `--border` and `--input`. SC 1.4.11 asks 3:1 only of visual
information *required* to identify a component, and its Understanding note says plainly that
where a control has visible content helping users identify it, a boundary indication is not
required ([1.4.11](https://www.w3.org/TR/WCAG22/#non-text-contrast),
[understanding](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)). Gating a
flat border ratio would be stricter than the spec, and a rule stricter than the spec is a rule
people switch off.

### Type pairings are an offer, never a step

A pack that omits `fonts` inherits the system stack, and **inheriting is the right default** — it
keeps a client pack closer to the system, which is what preserves the one-update-benefits-every-
project property. So six pairings exist to be *offered*, and onboarding never requires a choice:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py --list-fonts
```

A pairing carries **three family names and nothing else**. It carries no type scale, and that
absence is doctrine rather than an omission: `--text-step-*` is a system-owned axis (see the
table above — the spacing/type scale is never in a pack), so one scale serves every pack and
every pairing. Precomputing a scale per pairing would fork the very axis the pack model exists to
keep central, and `palette_candidates.py --check` fails if a pairing ever grows one.

Family availability and licensing are the pack author's check, not a claim from this skill.

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

### Money is `tabular-nums`, not `--font-mono` (#91)

**Money is not on that third list, and this is the boundary crossed most often.** A reference number,
an SLA timer, a code snippet and a timestamp are the four things `--font-mono` is for; a price, a
subtotal and an invoice total are none of them. What a column of figures needs is **equal digit
widths**, and that is a numeral feature rather than a face: `font-variant-numeric: tabular-nums`
*"Enables display of tabular numerals (OpenType feature: `tnum`)"*
([CSS Fonts 3 §tabular-nums](https://www.w3.org/TR/css-fonts-3/#tabular-nums), W3C Recommendation
2018-09-20; [CSS Fonts 4](https://www.w3.org/TR/css-fonts-4/#valdef-font-variant-numeric-tabular-nums)
repeats it verbatim). Reaching for the mono face to align ten digits changes the face of everything
around them as well. So: **`tabular-nums` on money, `font-mono` on the reference beside it.**

**It only works if the pack's sans font really carries `tnum`, and nothing will tell you when it
does not.** *"When a font lacks support for a given underlying font feature, text is simply rendered
as if that font feature was not enabled; font fallback does not occur and no attempt is made to
synthesize the feature except where explicitly defined for specific properties"*
([CSS Fonts 3 §feature-precedence](https://www.w3.org/TR/css-fonts-3/#feature-precedence)) — and
`font-variant-numeric` is **not** among the properties the spec exempts, which are
`font-variant-position` and small caps. A pack that overrides `fonts.sans` with a face lacking `tnum`
therefore gets a **silent no-op**: the utility is in the markup, the figures still do not line up, and
nothing fails anywhere.

Measured against the font binaries rather than assumed: **Bricolage Grotesque implements `tnum`
functionally** — its default digits are proportional and the feature substitutes fixed-width figures,
so `fidara` gets the alignment it claims. Newsreader and Overpass Mono register the tag but inertly,
both being tabular already by default (Overpass Mono because every glyph shares one advance width,
which is what monospace means).

**`brand_pack_lint.py` cannot check this, and that is a property of the pack format rather than a gap
to file.** A pack declares a font *family name*, not a font *binary*, so the lint has nothing local to
inspect. Overriding `fonts.sans` is consequently the one override carrying a manual check: confirm the
face lists `tnum` before shipping it, or the rule above is decoration.

**Which of the two reads better for money has no upstream, so the choice above is ours.** No W3C or
WHATWG document takes a position on monospace versus tabular figures for currency, and none asks for
any markup around a money value — WCAG 2.2 does not contain the word "currency", and neither `<data>`
nor `<bdi>` carries a currency example in the HTML Standard. Anything claiming a spec *requires*
`<data>`, `<bdi>` or an `aria-label` on an amount is folklore; right-aligning a numeric column is
likewise a convention with no standard behind it. Decision recorded on
[#91](https://github.com/fmanimashaun/claude-skills/issues/91).

## Voice / meta (for marketing copy, not product chrome)

Per-pack. For `fidara`: Fidara Solutions Ltd. Etymology **Fi** (use) + **ara** (Yoruba:
magic); fmworkflows tagline "Operations, engineered." Keep product UI free of marketing
lines — endorsement and taglines are marketing-surface only, for every pack.

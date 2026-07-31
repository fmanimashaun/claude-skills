# Foundations — Tokens (Tailwind v4 `@theme`)

One `@theme` block in `app/assets/tailwind/application.css` is the single source of truth.
Three token tiers, resolved in order:

1. **Brand primitives** — raw Fidara values (`fm-*`). Never referenced directly by components.
2. **Semantic roles** — role-named tokens (`--primary`, `--background`, …) that map onto
   primitives. **This is all components touch.**
3. **Fluid scale** — Utopia `clamp()` type + space (the modular scale) + measure/radius/
   shadow/motion.

Dark mode re-points the *roles* under `.dark`; component classes never change.

## 1. Brand primitives

```css
@theme {
  /* dark surfaces */
  --color-fm-navy:     #0C1B33;  --color-fm-midnight: #152238;  --color-fm-ink: #1A2B45;
  /* accents (Prism facets / product modules) */
  --color-fm-cerulean: #0077CC;  --color-fm-cerulean-700: #0072C4;  --color-fm-cerulean-foreground: #FFFFFF;
  --color-fm-electric: #00A3FF;  --color-fm-electric-foreground: var(--color-fm-navy);
  --color-fm-cyan:     #00D4FF;
  --color-fm-orange:   #FF6B35;  --color-fm-coral: #FF8C5A;   /* CTAs/accent — use sparingly */
  /* feedback */
  --color-fm-success:  #22C55E;  --color-fm-warning: #F59E0B;  --color-fm-error: #EF4444;  --color-fm-info: #00A3FF;
  /* neutral slate — 11 shades (this @theme scale is authoritative; ignore the older 8-shade
     tailwind-config.js and the README table, which disagree) */
  --color-fm-slate-50:#F8F9FB; --color-fm-slate-100:#F1F3F7; --color-fm-slate-200:#E2E6ED;
  --color-fm-slate-300:#C8CDD8; --color-fm-slate-400:#8F96A3; --color-fm-slate-500:#5E6775;
  --color-fm-slate-600:#3D4654; --color-fm-slate-700:#2A3240; --color-fm-slate-800:#1C2531;
  --color-fm-slate-900:#0F1520; --color-fm-slate-950:#0A0E16;
  /* type families */
  --font-sans:    "Bricolage Grotesque", ui-sans-serif, system-ui, sans-serif; /* UI/body/headings */
  --font-display: "Newsreader", ui-serif, Georgia, serif;                       /* brand moments, italic tagline */
  --font-mono:    "Overpass Mono", ui-monospace, monospace;                     /* refs (WO-0142), timers, code */
}
```

## 2. Semantic roles (what components consume)

Declare roles as runtime CSS variables, then bind them into `@theme inline` so Tailwind
emits `bg-primary`, `text-muted-foreground`, `border-border`, `ring-ring`, etc. **Every
surface role has a `-foreground` companion** — always write `bg-X text-X-foreground`.

```css
:root {
  --background: var(--color-fm-slate-50);   --foreground: var(--color-fm-slate-900);
  --card: #FFFFFF;                           --card-foreground: var(--color-fm-slate-900);
  --popover: #FFFFFF;                        --popover-foreground: var(--color-fm-slate-900);
  --primary: var(--color-fm-cerulean-700);   --primary-foreground: #FFFFFF;   /* hover: primary/90 */
  --secondary: var(--color-fm-slate-100);    --secondary-foreground: var(--color-fm-slate-900);
  --muted: var(--color-fm-slate-100);        --muted-foreground: var(--color-fm-slate-500);
  --accent: var(--color-fm-slate-100);       --accent-foreground: var(--color-fm-slate-900); /* hover/active bg */
  --destructive: var(--color-fm-error);      --destructive-foreground: #FFFFFF;
  --success: var(--color-fm-success);        --warning: var(--color-fm-warning);  --info: var(--color-fm-info);
  --border: var(--color-fm-slate-200);       --input: var(--color-fm-slate-200);
  --ring: var(--color-fm-cerulean-700);      /* focus ring, used at /30 opacity */
}
.dark {
  --background: var(--color-fm-navy);        --foreground: var(--color-fm-slate-50);
  --card: var(--color-fm-ink);               --card-foreground: var(--color-fm-slate-50);
  --popover: var(--color-fm-midnight);       --popover-foreground: var(--color-fm-slate-50);
  --secondary: var(--color-fm-slate-800);    --secondary-foreground: var(--color-fm-slate-50);
  --muted: var(--color-fm-slate-800);        --muted-foreground: var(--color-fm-slate-400);
  --accent: var(--color-fm-slate-800);       --accent-foreground: var(--color-fm-slate-50);
  --border: var(--color-fm-slate-800);       --input: var(--color-fm-slate-800);
  --primary: var(--color-fm-electric);       /* brand lifts to electric on dark */
  --primary-foreground: var(--color-fm-navy);  /* NOT white: white on electric is 2.73:1 */
}
@theme inline {
  --color-background: var(--background); --color-foreground: var(--foreground);
  --color-card: var(--card); --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover); --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary); --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary); --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted); --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent); --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive); --color-destructive-foreground: var(--destructive-foreground);
  --color-success: var(--success); --color-warning: var(--warning); --color-info: var(--info);
  --color-border: var(--border); --color-input: var(--input); --color-ring: var(--ring);
}
```
`@variant dark (&:where(.dark, .dark *));` enables the class-based dark mode; a pre-paint
inline script sets `.dark` from `localStorage` to avoid a flash.

## 3. Fluid scale (Utopia) + measure, radius, shadow, motion

Type and space are **fluid** (`clamp()`), interpolating between a min viewport (~360px) and
max (~1240px) — no breakpoint jumps. This *is* the modular scale; it unifies the old
marketing-vs-product scales into one. Generate values with the Utopia calculators and paste
the `clamp()`s; the shape:

```css
@theme {
  /* fluid type — --text-step--2 … --text-step-5 (compose with the type families above) */
  --text-step--1: clamp(0.833rem, 0.80rem + 0.15vw, 0.9rem);
  --text-step-0:  clamp(1rem,    0.95rem + 0.25vw, 1.125rem);   /* body; base 14–16px range */
  --text-step-1:  clamp(1.2rem,  1.12rem + 0.4vw,  1.42rem);
  --text-step-2:  clamp(1.44rem, 1.31rem + 0.65vw, 1.8rem);
  --text-step-3:  clamp(1.73rem, 1.54rem + 0.97vw, 2.28rem);    /* … up to step-5 for heroes */

  /* fluid space — --space-3xs … --space-3xl + one-off pairs (--space-s-l) */
  --space-2xs: clamp(0.5rem, 0.46rem + 0.18vw, 0.625rem);
  --space-xs:  clamp(0.75rem, 0.70rem + 0.27vw, 0.9375rem);
  --space-s:   clamp(1rem,   0.93rem + 0.36vw, 1.25rem);
  --space-m:   clamp(1.5rem, 1.39rem + 0.54vw, 1.875rem);
  --space-l:   clamp(2rem,   1.86rem + 0.71vw, 2.5rem);         /* … xl/2xl/3xl similarly */

  /* structure */
  --measure: 65ch;                 /* long-form reading measure; cap running text at this */
  --width-prose: 42rem;            /* 672px — section lede / intro blocks (2–3 lines, not long-form) */
  --width-shell: 80rem;            /* 1280px — the page shell; both reference corpora converge here */
  /* section rhythm — fidara default is GENEROUS (brand-pack knob, see brand.md) */
  --space-section: clamp(6rem, 5.2rem + 3.4vw, 8rem);          /* 96px → 128px */
  --space-section-compact: clamp(4rem, 3.6rem + 1.8vw, 6rem);  /* 64px → 96px — dense pages */
  --radius: 0.5rem;                /* base=8px → cards rounded-lg; buttons rounded-md=6px; badges rounded-full */
  --radius-sm: calc(var(--radius) - 2px);  --radius-lg: calc(var(--radius) + 4px);
  /* soft, shallow shadow ramp — structure comes from 1px borders, not heavy shadows */
  --shadow-xs: 0 1px 2px rgb(12 27 51 / .04);
  --shadow-sm: 0 1px 3px rgb(12 27 51 / .06);
  --shadow-md: 0 4px 16px rgb(12 27 51 / .10);   /* toasts/dropdowns */
  --shadow-lg: 0 20px 60px rgb(12 27 51 / .15);  /* modals */
  /* motion — two curves (arrival + departure) and three durations chosen by TRAVEL DISTANCE,
     not by component type. Full rules in motion.md; the short version is that a departure is
     always shorter than an arrival, and an exit takes the tier below its entrance. */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);   /* arrival — decelerates into place */
  --ease-in: cubic-bezier(0.4, 0, 1, 1);       /* departure — accelerates away */
  --duration-fast: 120ms;                      /* under 20px: chips, labels, focus */
  --duration: 180ms;                           /* 20-200px: rows, cells, menu items (default) */
  --duration-slow: 280ms;                      /* over 200px: drawers, modals, cross-viewport */
}
```

Rules: size type/space in **`rem`/`em`** (never `px`) so zoom/root-size propagate; use `ch`
for the measure; never raw `vw` for type — always `clamp()`. Prefer **logical properties**
(`padding-inline`, `margin-block`, `inset`) for RTL/vertical-writing safety.

## Applying the scale (calibrated against two reference corpora)

Having a fluid scale is not enough — *which* step goes where is the part that drifts. These
assignments were calibrated by measuring two independent commercial kits (704 + 264 files).

**Chrome vs content — the single most useful rule.** Both corpora are overwhelmingly
`text-sm`-centric for interface chrome: 14px chrome beats 16px body by roughly **2.7 : 1** in
each (Tailwind UI 6494 vs 1575; Flowbite 1100 vs 413). Interface chrome is *smaller* than prose.

| Use | Step | Applies to |
|---|---|---|
| Meta / eyebrow / caption / table header | `text-step--2` | uppercase labels, timestamps, helper text |
| **App chrome** | **`text-step--1`** | nav, buttons, form labels+inputs, table cells, badges, breadcrumbs, menus |
| **Prose / content** | **`text-step-0`** | body copy, marketing paragraphs, article text, section ledes |
| Card / sub-section heading | `text-step-1` | card titles, list-group headings |
| Section heading | `text-step-2` | in-page section titles |
| Page title | `text-step-3` | the one `h1` of an app screen |
| Hero | `text-step-4`–`5` | marketing hero only |

Using `text-step-0` for app chrome makes product UI read oversized and loose — the most common
calibration error, and the reason this table exists.

**It had drifted inside our own reference implementations** (#306), which is the copy source, so the
error was propagating rather than sitting still. Eleven sites, not the six first reported: the button
`BASE` in **two** files, the form-input base in **two**, a `<table>` in **two**, plus the badge `md`
size, the checkbox label, a menu item and a tab. One file contradicted itself two lines apart — a
`:label` at `text-step--1` immediately above its `:input` at `text-step-0`.

**Where `text-step-0` is still correct, so this does not get over-corrected on the next pass.** The
remaining uses were audited one by one and are all content or a deliberate scale:

| Site | Why it stays |
|---|---|
| Alert body, card description, page lede | prose — the row above |
| `<dd>` values in a description list | the value is content; its `<dt>` is chrome at `text-step--1` |
| `AvatarComponent` `md` | a deliberate `sm`/`md`/`lg` = `--1`/`0`/`1` ramp on the avatar itself, not chrome text |

**Mechanical enforcement belongs in `rendered_conformance.py`, not a grep.** Chrome and content are
only reliably distinguishable in a *rendered* DOM; a static rule would have to guess from class
strings, and its false positives would land on the legitimate uses in the table above — which is how
a linter gets switched off. design-flow's browser-driven linter already resolves real elements, so a
`chrome-type-step` rule there can decide this correctly.

**Heading ramp — use the middle steps.** Tailwind UI jumps from body straight to hero
(`text-4xl`/`5xl` heavy, thin mid-range); Flowbite carries a fuller ladder
(`text-lg`/`xl`/`2xl` well used). Ours follows Flowbite here: reach for **`step-1`/`step-2`** for
card and section headings rather than jumping to hero sizes. A dense screen may have *no* heading
above `step-2`.

**Section rhythm.** Vertical space is what reads as "premium". Use `--space-section` for
marketing/landing sections (fidara default, generous) and `--space-section-compact` for dense
product pages. Do **not** express rhythm as a breakpoint pair (`py-24 sm:py-32`) — the `clamp()`
token scales continuously and needs no breakpoint.

**Shell vs measure — two levels, both corpora agree.** Wrap the page in `--width-shell`
(1280px) and constrain running text to `--width-prose` (672px) or `--measure` (65ch) inside it.
That single nesting is most of what reads as "designed". `--measure` is the stricter, more
readable value: prefer it for long-form, `--width-prose` for section ledes.

## Control density

Both corpora converge on the same default control padding (`px-3 py-2` — Tailwind UI 749,
Flowbite 129), so the size vocabulary is bound to it. Height and padding must agree:

| Size | Padding | Height | Use |
|---|---|---|---|
| `sm` | `px-2 py-1` | `h-8` | compact toolbars, table row actions, dense filters |
| **`md`** (default) | **`px-3 py-2`** | `h-9` | buttons, inputs, selects — the default everywhere |
| `lg` | `px-4 py-2.5` | `h-10` | primary page actions, marketing CTAs |

`min-h-touch` (44px) still wins on touch targets regardless of size — see the utilities below.

## Validated by measurement (do not "improve" these)

Two doctrine rules were checked against the corpora and **confirmed**, so they are settled:

- **Radius language** — measured distribution matches ours exactly: controls `rounded-md`
  (Tailwind UI 2068), cards `rounded-lg` (966), pills/avatars `rounded-full` (1379). *(Flowbite
  prefers a softer all-`rounded-lg` language — 911 vs only 10 `rounded-md`. Considered and
  rejected for fidara; it is available as a brand-pack knob, see brand.md.)*
- **Elevation idiom** — a 1px edge plus a minimal shadow, not heavy shadows: Tailwind UI
  `ring-1` 690 + `shadow-xs` 498; Flowbite `border` 302 + `shadow-xs` 116. Heavy shadows are rare
  in both. This is exactly "the 1px border separates; elevate only genuine overlays".

## Never bind markup to a numbered step

`bg-fm-cerulean-600`, `text-fm-slate-700` and friends are **forbidden in component code** — roles
only (`bg-primary`, `text-muted-foreground`).

This is not stylistic. A numbered step encodes a *fixed lightness*, so it cannot adapt to a dark
surface, and every dark adjustment must then be written inline. Measured consequence in the
reference corpora, which bind to numbered steps (`text-primary-700` ×439, `bg-primary-700` ×217):
**20,825 `dark:` utility classes across 72 pages** (~289/page), plus 2050 more in the other kit's
templates. fidara's role layer needs **zero**: `--primary` is re-pointed once under `.dark` and
every component follows. One indirection removes ~20k inline variants.

## Utilities to keep

Define these with `@utility` (the Tailwind **v4** custom-utility API) — **not** raw classes in
`@layer utilities`. In v4, `@utility` is the only mechanism that registers a class with the
variant engine, so `sm:pt-safe`, `hover:min-h-touch`, `md:pb-safe` etc. actually generate.
(Raw classes in `@layer utilities` still emit their base form but get **no** variants in v4,
because v4 uses native CSS cascade layers instead of hijacking `@layer` the way v3 did.)

```css
/* Page shell + prose measure — the two-level nesting both corpora converge on. */
@utility shell { max-inline-size: var(--width-shell); margin-inline: auto; }
@utility prose-measure { max-inline-size: var(--width-prose); }

/* Section rhythm — fluid, no breakpoint pair needed. */
@utility section-y { padding-block: var(--space-section); }
@utility section-y-compact { padding-block: var(--space-section-compact); }

/* WIRE min-h-touch on every tap target (was defined-but-unused). */
@utility min-h-touch { min-height: 44px; }

/* Safe-area insets for fixed chrome (mobile / Hotwire Native). Variant-capable: e.g. sm:pt-safe. */
@utility pt-safe { padding-top: env(safe-area-inset-top); }
@utility pb-safe { padding-bottom: env(safe-area-inset-bottom); }
@utility pl-safe { padding-left: env(safe-area-inset-left); }
@utility pr-safe { padding-right: env(safe-area-inset-right); }
@utility mb-safe { margin-bottom: env(safe-area-inset-bottom); }
```

## Chart color tokens

Charts get their **own** validated role scale (`--color-chart-1..8` + sequential/diverging ramps),
derived from these `fm-*` primitives but separate from `primary`/status — defined and validated in
[data-viz.md](data-viz.md). Never color charts from the brand primitives or `primary` directly.

## What this fixes (from the audit)

- Components reaching for raw `bg-blue-700` / `fm-cerulean` / `gray-*` → **role tokens**.
- Two/three conflicting slate scales → **the 11-shade `@theme` scale is canonical**.
- Two type scales (marketing vs product) → **one fluid Utopia scale**.
- `dark:` class sprawl → **roles re-point under `.dark`**, component classes stay put.

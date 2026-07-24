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
  --color-fm-cerulean: #0077CC;  --color-fm-cerulean-foreground: #FFFFFF;
  --color-fm-electric: #00A3FF;  --color-fm-electric-foreground: #FFFFFF;
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
  --primary: var(--color-fm-cerulean);       --primary-foreground: #FFFFFF;   /* hover: primary/90 */
  --secondary: var(--color-fm-slate-100);    --secondary-foreground: var(--color-fm-slate-900);
  --muted: var(--color-fm-slate-100);        --muted-foreground: var(--color-fm-slate-500);
  --accent: var(--color-fm-slate-100);       --accent-foreground: var(--color-fm-slate-900); /* hover/active bg */
  --destructive: var(--color-fm-error);      --destructive-foreground: #FFFFFF;
  --success: var(--color-fm-success);        --warning: var(--color-fm-warning);  --info: var(--color-fm-info);
  --border: var(--color-fm-slate-200);       --input: var(--color-fm-slate-200);
  --ring: var(--color-fm-cerulean);          /* focus ring, used at /30 opacity */
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
  --measure: 65ch;                 /* readable line length; cap running text at this */
  --radius: 0.5rem;                /* base=8px → cards rounded-lg; buttons rounded-md=6px; badges rounded-full */
  --radius-sm: calc(var(--radius) - 2px);  --radius-lg: calc(var(--radius) + 4px);
  /* soft, shallow shadow ramp — structure comes from 1px borders, not heavy shadows */
  --shadow-xs: 0 1px 2px rgb(12 27 51 / .04);
  --shadow-sm: 0 1px 3px rgb(12 27 51 / .06);
  --shadow-md: 0 4px 16px rgb(12 27 51 / .10);   /* toasts/dropdowns */
  --shadow-lg: 0 20px 60px rgb(12 27 51 / .15);  /* modals */
  /* motion */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --duration: 180ms;
}
```

Rules: size type/space in **`rem`/`em`** (never `px`) so zoom/root-size propagate; use `ch`
for the measure; never raw `vw` for type — always `clamp()`. Prefer **logical properties**
(`padding-inline`, `margin-block`, `inset`) for RTL/vertical-writing safety.

## Utilities to keep

Define these with `@utility` (the Tailwind **v4** custom-utility API) — **not** raw classes in
`@layer utilities`. In v4, `@utility` is the only mechanism that registers a class with the
variant engine, so `sm:pt-safe`, `hover:min-h-touch`, `md:pb-safe` etc. actually generate.
(Raw classes in `@layer utilities` still emit their base form but get **no** variants in v4,
because v4 uses native CSS cascade layers instead of hijacking `@layer` the way v3 did.)

```css
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

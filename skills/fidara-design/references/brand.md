# Brand

Two brands, **one system.** **Fidara** (parent) and **fmworkflows** (its product, "by
Fidara") share identical values — palette, typefaces, spacing, mark. The only difference is
the **token prefix**: brand kits label tokens `--fidara-*` vs `--fm-*`, but **all code uses
`fm-*`** (the de-facto shared prefix). So "switching brand" is a labeling/lockup concern, not
a re-theme. Full brand assets live per-repo under `docs/design-system/brand-assets/`; the
canonical superset is in `fidara-solutions/fidara-platform`.

## Parameterization

- Components/tokens are brand-neutral (they consume semantic roles, which map to `fm-*`).
- The **only** brand-specific outputs are the **logo lockup** and the **"by Fidara"
  endorsement**: product UI (fmworkflows) uses the Prism mark + wordmark *without* the
  endorsement; marketing surfaces add "by Fidara". Keep a single `brand` config value
  (`fidara | fmworkflows`) that selects the lockup asset + whether the endorsement shows.

## The Prism mark

A single 3-facet prism — **left = cerulean `#0077CC`, right = electric `#00A3FF`, top = cyan
`#00D4FF`** — the three facets denote the three product modules (FM / IT / Fleet). Exact SVG
paths live in `01-logos/DESIGN-SPECIFICATIONS.md`.
- Wordmark: **Bricolage Grotesque Black (900)**, uppercase, tight tracking, `foreground` on
  light / `fm-slate-50` on dark.
- Signal-orange accent bar: 3px, from the prism's left edge to center.
- **Clear space** = 1.5× prism height. **Min sizes:** prism 20px digital / 6mm print; lockup 140px.
- **Don'ts:** never stretch/rotate/recolor individual facets; no drop-shadows/glows/bevels; no
  reduced opacity except intentional watermarks. Variants: full-color · reversed · monochrome ·
  outline (watermark) · white (busy backgrounds).

## Iconography

**Lucide** icons everywhere. Default **20px** (16 compact / 24 large), **stroke 1.5**,
`fill/stroke: currentColor` so they inherit text color; size to text with the `with-icon`
utility (`svg { size: 1em }`). Icons may take a module color only when denoting module
context.

## Typography roles (see foundations-tokens.md for the scale)

- **Bricolage Grotesque** (`--font-sans`) — ~90% of text: UI, body, headings.
- **Newsreader** (`--font-display`) — brand/marketing moments and the italic tagline only.
- **Overpass Mono** (`--font-mono`) — reference numbers (e.g. `WO-0142`), SLA timers, code,
  timestamps.
Tracking: headings `-0.02em`; all-caps labels `+0.05–0.1em`; `antialiased`.

## Voice / meta (for marketing copy, not product chrome)

Fidara Solutions Ltd. Etymology: **Fi** (use) + **ara** (Yoruba: magic). fmworkflows tagline
"Operations, engineered." Keep product UI free of marketing lines; endorsement and taglines
are marketing-surface only.

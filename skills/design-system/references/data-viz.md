# Data Visualization

Charts, KPIs, and dashboards are part of the design system — not a free-for-all. A chart is
**read by people and rendered by an agent**, so color and form follow rules, not taste. This
layer adapts the design-system-agnostic data-viz method (form → color-by-job → **validate** →
marks → interaction → a11y) to fidara: the method is invariant; fidara only supplies the
**parameters** below, and the categorical palette was **run through the validator, not
eyeballed** (see [Validation](#validation)).

**Non-negotiable, up front:** components consume the **chart role tokens** (`--color-chart-*`)
and the rules here — never ad-hoc hex, never a rainbow, never a dual axis. Chart color is its
own token scale, distinct from the `primary`/status roles.

## The procedure (in order — color is LAST)

1. **Pick the form by the data's job.** magnitude→bar · change-over-time→line/area ·
   part-of-whole→stacked bar (donut only ≤3 slices) · identity/ranking→bar · correlation→scatter ·
   a single headline→**a stat tile, not a chart**. When one number tells the story, ship a KPI tile.
2. **Assign color by the job it does** (below): categorical (identity), sequential (magnitude),
   diverging (polarity), status (state). Assign categorical slots **in fixed order, never cycled**.
3. **Validate** the categorical palette (already done for the shipped tokens; **re-run if you
   change a hue** — `node scripts/validate_palette.js` from the dataviz skill).
4. **Marks:** thin marks, 2px lines, ≥8px markers, 4px rounded bar ends on the baseline, a 2px
   surface gap between adjacent/stacked fills, recessive grid/axes.
5. **Interaction:** crosshair+tooltip on line/area, per-mark tooltip on bar/dot; filters in one row
   above the chart. (A bare stat tile is the only form with no hover.)
6. **Accessibility pass** + **look at the rendered output** (the validator checks color, not layout).

## Parameters (the fidara instance)

| Parameter | fidara value |
|---|---|
| **Ramps** | the `fm-*` brand hues + the 11-step slate scale (foundations-tokens) |
| **Categorical** | 8 fixed slots, brand-anchored (blue=cerulean, orange=fm-orange), validated order below |
| **Sequential** | one hue — **cerulean**, light→dark |
| **Diverging** | **cerulean ↔ error-red**, neutral **slate** midpoint (warm/cool poles; gray mid reads as "nothing") |
| **Status** | the existing semantic roles — `info` / `success` / `warning` / `destructive` — **reserved**, never a categorical slot, always shipped with an icon + label (never color alone) |
| **Surfaces** | light = `--background` (`#F8F9FB`) / `--card` (`#fff`); dark = `--card` on `fm-navy` (`#0C1B33`) |
| **Texture** | one 45°/135° hatch fill, for the CVD / print / forced-colors fallback |

### Categorical palette (validated — both modes are *selected*, dark is the same 8 hues re-stepped)

| Slot | Hue | Light | Dark |
|---|---|---|---|
| 1 | blue (cerulean) | `#0077CC` | `#3987e5` |
| 2 | orange (fm-orange) | `#FF6B35` | `#d95926` |
| 3 | aqua | `#1baf7a` | `#199e70` |
| 4 | yellow | `#eda100` | `#c98500` |
| 5 | magenta | `#e87ba4` | `#d55181` |
| 6 | green | `#008300` | `#33a852` |
| 7 | violet | `#4a3aa7` | `#9085e9` |
| 8 | red | `#e34948` | `#e66767` |

The **ordering is the CVD-safety mechanism**, not cosmetic. A 9th series is never a generated
hue — it folds into "Other", small multiples, or a composite encoding.

## Tokens — define chart slots in `@theme` (v4), re-point under `.dark`

Same architecture as the other role tokens (`@theme inline` → `bg-chart-1`/`text-chart-1`
utilities that re-point in dark):

```css
:root {
  --chart-1: #0077CC; --chart-2: #FF6B35; --chart-3: #1baf7a; --chart-4: #eda100;
  --chart-5: #e87ba4; --chart-6: #008300; --chart-7: #4a3aa7; --chart-8: #e34948;
  /* sequential (cerulean, light→dark) — near-zero recedes toward surface */
  --chart-seq-100: #cde2fb; --chart-seq-300: #6da7ec; --chart-seq-500: #256abf; --chart-seq-700: #0d366b;
  /* diverging (cerulean ↔ red, slate midpoint) */
  --chart-div-neg: #0077CC; --chart-div-mid: #F0EFEC; --chart-div-pos: #e34948;
}
.dark {
  --chart-1: #3987e5; --chart-2: #d95926; --chart-3: #199e70; --chart-4: #c98500;
  --chart-5: #d55181; --chart-6: #33a852; --chart-7: #9085e9; --chart-8: #e66767;
  --chart-div-mid: #383835;
}
@theme inline {
  --color-chart-1: var(--chart-1); --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3); --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5); --color-chart-6: var(--chart-6);
  --color-chart-7: var(--chart-7); --color-chart-8: var(--chart-8);
}
```
Now `fill-chart-1`, `bg-chart-2`, `text-chart-3` etc. exist and swap in dark automatically.
Charts render against these roles + the `--foreground`/`--muted-foreground` **text** tokens.

## Recipes

### KPI / stat tile (`app/components/ui/stat_component.rb`)
```ruby
# frozen_string_literal: true
module Ui
  class StatComponent < ViewComponent::Base
    renders_one :spark  # optional inline sparkline (<svg>)
    def initialize(label:, value:, delta: nil, intent: :neutral)
      @label, @value, @delta, @intent = label, value, delta, intent.to_sym
    end
    # delta uses STATUS ink (never a chart slot), with an arrow glyph — not color alone
    def delta_class
      { up: "text-success", down: "text-destructive", neutral: "text-muted-foreground" }
        .fetch(@delta&.dig(:dir) || :neutral)
    end
  end
end
```
```erb
<%# box + stack; value in text-step-3, label muted, delta carries an arrow + status ink %>
<div class="box bg-card text-card-foreground rounded-lg border border-border stack" style="--space: var(--space-2xs)">
  <p class="text-step--1 text-muted-foreground"><%= @label %></p>
  <p class="text-step-3 font-bold tabular-nums"><%= @value %></p>
  <% if @delta %><p class="cluster text-step--1 <%= delta_class %>" style="--space: var(--space-3xs)">
    <span aria-hidden="true"><%= @delta[:dir] == :down ? "↓" : "↑" %></span><%= @delta[:label] %></p><% end %>
  <% if spark? %><div class="mt-1"><%= spark %></div><% end %>
</div>
```
Host KPI rows in `grid-auto` (`--min: 12rem`). The value wears **text tokens**, never a chart hue.

### Bar chart marks (inline SVG or any lib — the rules are the same)
```erb
<%# each bar = a fixed categorical slot; 4px rounded top on the baseline; 2px gap between bars %>
<rect class="fill-chart-1" rx="4" x="…" y="…" width="…" height="…" />
<rect class="fill-chart-2" rx="4" … />
<%# ≥2 series → a legend is ALWAYS present; ≤4 series also get direct labels %>
```
Wire real charts with **Chartkick + Groundwork/Chart.js** or inline SVG; whichever, the color/mark
rules here are library-agnostic. Feed the lib the `--color-chart-*` values (read them off the
computed style, or mirror them in the lib's dataset colors).

## Non-negotiables (charts)

- **Chart role tokens only** (`--color-chart-*`, sequential/diverging ramps) — never ad-hoc hex.
- **Fixed categorical order, never cycled.** Color follows the **entity**, not its rank — a filter
  that drops a series must not repaint the survivors. Cap at 8; a 9th → "Other"/facet.
- **One axis.** Never a dual-axis (two y-scales) chart — the #1 chart mistake. Different scales →
  two charts, small multiples, or index to a common base.
- **Sequential = one hue light→dark. Diverging = two hues + a neutral (slate) midpoint.** No rainbow.
- **Identity is never color-alone:** ≥2 series → a legend is always present; ≤4 → also direct-label.
  Provide a **table view**; make **texture** available for CVD/print/forced-colors.
- **Text wears text tokens** (`foreground`/`muted-foreground`), never a series color.
- **Status colors are reserved** (good/warning/serious/critical) — never "series 4"; always icon + label.
- **Dark mode is selected, not flipped** — the dark steps above were validated against the navy
  surface, not auto-derived.
- **Re-validate if you change a hue:** `node scripts/validate_palette.js "<hexes>" --mode light`
  then `--mode dark --surface "#0C1B33"`. Ship only a passing order.

## Validation

The shipped categorical palette was validated with the data-viz method's `validate_palette.js`
(the "compute it, don't eyeball it" rule):

- **Light** (surface `#F8F9FB`): all hard gates PASS — worst adjacent CVD ΔE **9.1**, normal-vision
  ΔE **19.6**. Four slots (orange, aqua, yellow, magenta) sit below 3:1 on the light surface → the
  **relief rule** applies: visible direct labels or a table view (already mandated above).
- **Dark** (surface `fm-navy #0C1B33`): lightness, chroma, normal-vision (ΔE **19.3**) and contrast
  (all ≥ 3:1) PASS; the green↔magenta adjacency is CVD ΔE **6.1** (6–8 floor band) → legal **with
  secondary encoding**, which fidara already requires (legend + direct labels for ≥2 series).

Basis: WCAG 1.4.11 non-text contrast (≥3:1); the Tailwind v4 `@theme`→utility mechanism
(`--color-chart-*` → `bg-chart-*`), verified in this repo. Method source: Anthropic's `dataviz`
skill (design-system-agnostic; its palette is built to be swapped for a brand's and re-validated).

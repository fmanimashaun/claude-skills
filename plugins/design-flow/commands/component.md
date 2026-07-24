---
description: Author or refactor a UI component per the Fidara design system — compose layout primitives + semantic role tokens, apply the variant/size/state vocabulary, add a11y and prescribed responsive behavior.
argument-hint: "<component name or screen>  [e.g. pricing-card | settings form | data table]"
---

# /design-flow:component — $ARGUMENTS

Build (or fix) `$ARGUMENTS` to the **fidara-design** doctrine. Delegate to the
**ui-composer** agent. Never freehand CSS — compose.

## Order of operations (follow every time)

1. **Locate it in the catalog** (`skills/fidara-design/references/components.md` /
   `forms.md`). If it's a catalog component, use that recipe + variant/size/state axes; if it's
   a screen, build it by **composing** existing components + layout primitives. For the
   concrete code, reference `reference-implementation.md` (Button/Card + Stimulus mixins) and
   `component-implementations.md` (the full worked catalog) — mirror those exact shapes.
   **If it's a CRUD screen** (list + create/edit/delete), follow `crud-modal-pattern.md`:
   mutations open in the shared `turbo-frame` modal and update the list via Turbo Stream —
   never build a full-page new/edit form. **If it's a chart / KPI / dashboard**, follow
   `data-viz.md`: pick the form by the data's job, use the `--color-chart-*` tokens (never ad-hoc
   hex), one axis, legend + direct labels; re-run the palette validator if you change a hue.
2. **Pick semantic role tokens** (foundations-tokens.md) — `bg-primary text-primary-foreground`,
   `border-border`, `text-muted-foreground`, `focus-visible:ring-ring/30`. **Never** raw `fm-*`
   or stock `blue-700`/`gray-*` in component code.
3. **Compose layout primitives** (layout-primitives.md) — `box > stack`, `grid-auto`, `cluster`,
   `Layout::Sidebar`/`Switcher`, etc. Spacing via parent `gap`, from the `--space-*` scale.
4. **Express variants server-side** — a Ruby base+variants+sizes+defaults map on the
   ViewComponent (the cva pattern, no JS dep). Reuse the shared size vocabulary (`sm/md/lg`).
5. **Interaction** (interaction-stimulus.md) — if interactive, wire the right Stimulus
   controller/mixins; style state off `data-[state=…]`/`aria-*`; full keyboard + ARIA.
6. **Responsive** (responsive.md) — fluid + intrinsic first; a breakpoint only for a structural
   swap; `min-h-touch` on tap targets.
7. **a11y checklist** — focus-visible ring, roles/ARIA, `sr-only` for icon-only, no color-only
   state, contrast.

## Output

The ViewComponent (`.rb` + `.html.erb`) and/or refactored partial, using role tokens only,
plus a one-line note of the variants/sizes/states exposed and the responsive behavior. If a
needed token/recipe is missing from the system, flag it (propose a system addition) rather than
inventing an ad-hoc value.

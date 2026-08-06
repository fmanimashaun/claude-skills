---
description: Author or refactor a UI component per the Fidara design system — compose layout primitives + semantic role tokens, apply the variant/size/state vocabulary, add a11y and prescribed responsive behavior.
argument-hint: "<component name or screen>  [e.g. pricing-card | settings form | data table]"
---

# /design-flow:component — $ARGUMENTS

Build (or fix) `$ARGUMENTS` to the **fidara-design** doctrine. Delegate to the
**ui-composer** agent. Never freehand CSS — compose.

## Preconditions

**The `fidara-design` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`fidara-design`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

## `--variants N` — when the brief has no single right answer

`$ARGUMENTS` ending in `--variants N` (default 3) hands off to **`/design-flow:variants`**: N
brand-conformant compositions of the same brief plus a switcher to compare them live in the app.
Use it when the brief has many defensible solutions — a hero, a pricing page, a landing section,
a dashboard's first screen — where one output invites a yes/no and the useful question is *which
of these three, and why?*. Everything below still applies to **each** variant; variant mode
changes how many outputs there are, never what the doctrine is. Without the flag, one output.

## Order of operations (follow every time)

1. **Locate it in the catalog** (`skills/fidara-design/references/components.md` /
   `forms.md`). If it's a catalog component, use that recipe + variant/size/state axes.
   **If it's a screen — a page, a dashboard, a settings area, anything above component
   scale — start from `page-anatomies.md`, not from a blank template.** Pick a shell
   (sidebar / stacked / multi-column), pick an anatomy (home-dashboard / detail / settings),
   then fill each region by **composing** existing components + layout primitives. A screen
   is composed, not designed; inventing page structure is where breakpoint chains, nested
   cards and inconsistent heading ramps come from. That file also carries the
   primitive-instead-of-breakpoint substitution table and the chrome-vs-content type
   assignments, so apply both before writing markup. For the
   concrete code, reference `reference-implementation.md` (Button/Card + Stimulus mixins) and
   `component-implementations.md` (the full worked catalog) — mirror those exact shapes.

   **If the surface is MARKETING** — a landing page, pricing, a feature section, a hero: anything a
   prospect rather than a logged-in user reads — three more references are mandatory before writing
   markup, each answering a question the component catalog does not.
   - `skills/fidara-design/references/marketing-copy.md` (#131) — the copy contract for that section archetype: who the one reader
     is, the claim and its proof, specific over generic. **Draft against the contract; never invent
     positioning** — that is the human's decision. A confident placeholder is worse than an obvious
     one, so no `Lorem ipsum` and no `Your headline here`: if you do not know the claim, say so in
     the output instead of filling the slot.
   - `skills/fidara-design/references/visual-assets.md` (#135) — the asset tier, preferring specific over decorative: a product
     screenshot beats brand geometry, which beats stock illustration. Geometry derives from the
     prism facets and accent bar using **role tokens**, is `aria-hidden`, and never carries meaning.
     Never mix illustration styles on one surface.
   - `skills/fidara-design/references/motion.md` (#136) — named patterns only, tokenised durations, a defined static end-state.
     Motion never carries information, and every pattern has a reduced-motion fallback.
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

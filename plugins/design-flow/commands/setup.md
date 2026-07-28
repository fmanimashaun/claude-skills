---
description: Scaffold the Fidara design system into a Rails 8 + Hotwire + Tailwind v4 project — @theme token architecture (brand primitives -> semantic roles -> Utopia fluid scale), layout-primitive @utility recipes, base ViewComponents, dark mode. Idempotent; brand-parameterized.
argument-hint: "[brand pack: <pack> or <pack>:<variant>, e.g. fidara:fmworkflows]"
---

# /design-flow:setup — $ARGUMENTS

Install the **fidara-design** system into this project. Follow the skill doctrine
(`skills/fidara-design/SKILL.md` + references) exactly — this command applies it.

## Preconditions

Rails 8 + Hotwire (importmap) + **Tailwind v4** (`tailwindcss-rails`, CSS-first `@theme`, no
`tailwind.config.js`/npm). Confirm `app/assets/tailwind/application.css` exists.

`$ARGUMENTS` selects the **brand pack**: `<pack>` or `<pack>:<variant>` (e.g. `fidara`,
`fidara:fmworkflows`, `acme`). Default `fidara:fmworkflows`. Read the pack from
`brands/<pack>/` — its `theme.css` supplies the palette and its `brand.json` supplies identity
and variants. **A pack is a theme, not a fork**: it changes colours and the logo, and inherits
everything else. Generating the theme layer is therefore the ONLY brand-dependent step here;
steps 2-6 are brand-neutral and identical for every pack.

**Lint the pack before generating anything** — a pack missing a role would render a stock
Tailwind colour rather than fail. Resolve the pack directory before linting, because the two
live in different places:

```bash
LINT=${CLAUDE_PLUGIN_ROOT}/scripts/brand_pack_lint.py
# a project's own pack (the client case) sits in the repo; the shipped reference packs
# (fidara, _template) sit inside the plugin
if [ -d "brands/<pack>" ]; then PACK="brands/<pack>"
else PACK="${CLAUDE_PLUGIN_ROOT}/brands/<pack>"; fi
python3 "$LINT" "$PACK"
```

Refuse to scaffold on a non-zero exit; report which roles are missing. If neither path exists,
say so and offer to scaffold a new pack by copying `${CLAUDE_PLUGIN_ROOT}/brands/_template` into
`brands/<pack>` — the template deliberately fails the lint until its palette is validated, which
is the reminder to run the data-viz validator for this brand.

## Idempotency

Own only what you scaffold; re-runnable. Wrap generated `@theme`/token blocks and `@utility`
recipes between markers; on re-run refresh inside the markers only, leaving hand edits intact.
Never overwrite an existing customized component without showing a diff. Stage only files you
authored; `git status` after.

## Scaffold (per foundations-tokens.md)

1. **`application.css`** — the full `@theme`: the **pack's** primitives (whatever it names them —
   `fm-*` is fidara's own choice, not a system prefix) + the 3 font roles,
   semantic roles via `@theme inline` with `:root`/`.dark`, the Utopia fluid `--text-step-*` /
   `--space-*` (`clamp()`) scale, `--measure/--radius/--shadow-*/--ease-out/--duration`,
   `@variant dark`, `@plugin @tailwindcss/forms` + `typography`, and the `min-h-touch`/safe-area
   utilities. Add the pre-paint dark-mode `<script>` to the layout.
2. **Layout `@utility` recipes** (layout-primitives.md): `stack`, `cluster`, `center`, `box`,
   `grid-auto`, `frame`, `cover`, `reel`, `with-icon`.
3. **Base ViewComponents** (`app/components/`): `Layout::Sidebar`, `Layout::Switcher`,
   `Layout::Container`, and `Ui::Button`, `Ui::Card`, `Ui::Badge`, `Ui::Alert`, `Ui::Modal`,
   `Ui::Avatar`, `Ui::EmptyState`, **`Ui::Logo`** — each with the variant/size/state map + slots
   from components.md. (If the project doesn't use ViewComponent yet, add the gem, or fall back to
   the helper-DSL variant — ask which.)
   **`Ui::Logo`** renders the Prism mark/lockup (`variant: :mark|:lockup`, `size: :sm|:md|:lg`
   ≥20px, `brand_variant:` selecting the pack variant whose `endorsement` string is rendered — no
   brand name is ever hardcoded) so no screen hand-rolls a text eyebrow.
   Facet hues are fixed brand colors — the documented exception to role-tokens-only. If
   `docs/design-system/brand-assets/01-logos/` exists, use its exact SVG paths; otherwise scaffold
   the canonical 3-facet prism from component-implementations.md and tell the user to swap in the
   official asset. Pair it with the **auth/focused-page** recipe (`cover > center > stack`) for
   sign-in / splash / onboarding screens.
4. **Stimulus mixins + controllers** (interaction-stimulus.md): the four mixins (list-navigation,
   focus-trap+restore, dismissable-layer, anchored-position) and the `modal`/`dropdown`/`tabs`/
   `sidebar`/`theme`/`toast` controllers built on them.

Use **[references/reference-implementation.md](../../skills/fidara-design/references/reference-implementation.md)**
as the canonical source for steps 3–4: copy the ViewComponent pattern (Button/Card shown) and
the four Stimulus mixins verbatim, then extend the catalog by mirroring those exact shapes.
Mobile (Hotwire Native parity) is Phase 2 — see references/mobile.md; this command targets web.
5. **Fonts**: from the pack's `fonts` override if present, else the system default stack
   (Bricolage Grotesque / Newsreader / Overpass Mono). Wire the three *roles*, never literal
   families in components.
6. **Lucide** icon helper (`with-icon`, `1em`, `currentColor`).
7. **Brand config for `Ui::Logo`**: generate `config/initializers/brand.rb` from the pack's
   `brand.json` so `Rails.configuration.x.brand` exposes `default_variant` and `variants`
   (each with `name`, `endorsement`, `mark`). `Ui::Logo` reads identity from there — **never
   hardcode a brand name in a component.**

## Brand-pack verification — and file an issue when it fails

The pack lint proves a pack is *internally* complete. It cannot prove the generated theme
actually works in a real app, so **this first run is the verification**. Check all four, and on
any failure file an issue with `/rails-flow:report` (component `design-flow` / `fidara-design`)
before continuing:

1. **Tailwind builds.** The generated `@theme` + role layer compiles without error.
2. **Roles resolve.** Spot-check a few rendered surfaces in light *and* dark: `bg-primary`,
   `bg-card`, `text-muted-foreground`, `border-border`. **If a pack passed the lint but something
   still renders a stock Tailwind colour, the 22-role contract is incomplete** — that is the
   highest-value defect to report, because it means the lint is checking the wrong set and every
   future pack inherits the hole. Include which utility rendered unbranded.
3. **`Ui::Logo` renders** the pack's mark, and the endorsement matches the selected variant —
   present for a product variant, absent for a parent (a parent does not endorse itself). Getting
   "X by X" or a missing endorsement means the manifest wiring is wrong.
4. **Dark mode re-points.** Toggling theme changes the surfaces; a surface that stays put means a
   `.dark` re-point is missing from the pack or the lint's `DARK_REQUIRED` set is wrong.

Report the **pack slug, the lint output, the failing step, and the exact build/render error**. A
pack-related failure is almost always a doctrine or lint defect rather than a project problem —
which is precisely why it belongs upstream instead of being patched locally.

## Report

Files created, brand selected, ViewComponent decision, and the entry points:
`/design-flow:component` to author UI, `/design-flow:audit` to check drift. Remind that a new
`@theme` needs a Tailwind rebuild. Finally: if any generated component fails to compile or
render in this app, it's a toolchain defect — report it with **`/rails-flow:report`**
(component `design-flow` / `fidara-design`) so the doctrine gets fixed upstream.

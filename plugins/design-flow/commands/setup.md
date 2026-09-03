---
description: Scaffold the design system into a Rails 8 + Hotwire + Tailwind v4 project — @theme token architecture (brand primitives -> semantic roles -> Utopia fluid scale), layout-primitive @utility recipes, base ViewComponents, dark mode. Idempotent; brand-parameterized.
argument-hint: "[brand pack: <pack> or <pack>:<variant>, e.g. fidara:fmworkflows]"
---

# /design-flow:setup — $ARGUMENTS

Install the **design-system** system into this project. Follow the skill doctrine
(`skills/design-system/SKILL.md` + references) exactly — this command applies it.

## Preconditions

**The `design-system` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`design-system`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

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

Refuse to scaffold on a non-zero exit; report which roles are missing.

### If the pack does not exist yet — offer candidates, never a blank file

Say the pack is missing, then offer the three ways to create one. Do **not** hand over
`_template` and leave the user inventing hexes: a palette invented on the spot is a palette
nobody measured, and it ships in the client's colours.

```bash
CANDIDATES=${CLAUDE_PLUGIN_ROOT}/scripts/palette_candidates.py
python3 "$CANDIDATES" --list                       # 10 measured starting palettes
python3 "$CANDIDATES" --emit harbor --out brands/<pack>   # no client palette at all
python3 "$CANDIDATES" --snap "#RRGGBB" --out brands/<pack> # client HAS a brand colour
```

- **No usable palette** — walk the decision path in
  [references/brand.md](../../skills/design-system/references/brand.md) (*Starting a pack when the
  client has no palette*). It is an ordered path: logo colour → does the product recede → hue
  family → formality. Ask for the client's sector and their logo colour; do not paste the whole
  catalogue and ask them to browse. Every candidate is already measured against WCAG 1.4.3 in
  both modes.
- **Client has brand colours** — `--snap`. It maps their colour onto the role structure, measures
  it, and where their colour cannot carry a role it names the nearest passing colour of the same
  hue **with both numbers**. Report those numbers verbatim; the mark keeps their exact colour
  (WCAG 1.4.3 exempts logotypes), only the `--primary` role moves.
- **Copying `${CLAUDE_PLUGIN_ROOT}/brands/_template`** is still available for a hand-authored
  pack. Its worked-example values are measured too, but the moment they are replaced they are not
  — re-measure with `python3 "$CANDIDATES" --measure brands/<pack>`.

Whichever route, the new pack arrives with `chart_palette_validated: false` and therefore
**fails the lint on purpose**. That failure is the reminder to run the data-viz palette validator
against *this* pack's surfaces — it is required even when the chart hues are inherited, because
changing the palette changes the surface those hues sit on.

**Typefaces are an offer, not a step.** Omitting `fonts` inherits the system stack and that is the
right default. Mention `python3 "$CANDIDATES" --list-fonts` once; do not make it a question the
user has to answer before the pack can be created.

## Idempotency

Own only what you scaffold; re-runnable. Wrap generated `@theme`/token blocks and `@utility`
recipes between **these exact markers** — as CSS comments, so they survive in `application.css`:

```css
/* design-flow:tokens:begin — managed by /design-flow:setup; edits here are overwritten on re-run */
…
/* design-flow:tokens:end */
```

**Inside is the plugin's; outside is yours.** A local extension — a project's own primitive, an extra
role it needs — goes **outside** the markers and is never touched. On re-run, refresh inside only.

The marker used to be unspecified (#754): the contract said "between markers" and named none, so every
scaffold invented its own string and "hand edits stay intact" held only if the next run guessed the
same one. It also left `check_token_drift.py` nothing to key on — without a line between plugin-owned
and project-owned tokens, a drift check either flags every legitimate extension or checks nothing.
Never overwrite an existing customized component without showing a diff. Stage only files you
authored; `git status` after.

## Scaffold (per foundations-tokens.md)

1. **`application.css`** — the full `@theme`: the **pack's** primitives (whatever it names them —
   `fm-*` is fidara's own choice, not a system prefix) + the 3 font roles,
   semantic roles via `@theme inline` with `:root`/`.dark`, the Utopia fluid `--text-step-*` /
   `--space-*` (`clamp()`) scale, `--measure/--radius/--shadow-*/--ease-out/--duration`,
   the `radius` knob expanded to the five steps `brand_pack_lint.RADIUS_RAMP_STEPS` names (`--radius`,
   `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl` — one definition, shared with `check_token_drift`),
   `@custom-variant dark`, `@plugin @tailwindcss/forms` + `typography`, and the `min-h-touch`/safe-area
   utilities. Add the pre-paint dark-mode `<script>` to the layout.
2. **Layout `@utility` recipes** (layout-primitives.md): `stack`, `cluster`, `center`, `box`,
   `grid-auto`, `frame`, `cover`, `reel`, `with-icon`.
3. **Base ViewComponents** (`app/components/`): `Layout::Sidebar`, `Layout::Switcher`,
   `Layout::Container`, and `Ui::Button`, `Ui::Card`, `Ui::Badge`, `Ui::Alert`, `Ui::Modal`,
   `Ui::Avatar`, `Ui::EmptyState`, **`Ui::Logo`**, **`Ui::Toast`**, **`Ui::Dropdown`**,
   `Ui::Tabs`, **`Ui::PasswordStrength`** — each with the variant/size/state map + slots
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
   `sidebar`/`theme`/`toast`/`password-strength` controllers built on them.
   **A controller without its component is dead code.** Every controller here except `sidebar` and
   `theme` drives a component in step 3 — `toast`, `dropdown` and `tabs` were shipped orphaned
   (#483), and `scripts/lint_self_consistency.py`'s `orphaned-controller` rule now fails the build
   if that recurs.
4b. **The `#toasts` container, in the layout** (`reference-implementation.md` →
   *Three things this block may not drop*):

   ```erb
   <turbo-frame id="modal"></turbo-frame>
   <div id="toasts" aria-live="polite"
        class="fixed top-4 right-4 z-[100] stack max-w-sm pointer-events-none"></div>
   ```

   **Not optional, and not cosmetic.** `crud-modal-pattern.md` emits every success with
   `turbo_stream.prepend("toasts", ToastComponent.new(...))` — three call sites in the doctrine — so
   without this `div` the target does not exist and **every CRUD success path silently drops its
   feedback**. `aria-live` belongs on the **container**, which must be in the DOM before content is
   inserted into it. Do not move the attribute onto the toast, and do not add a second flash surface:
   routing flash through Turbo Stream **replaces** the `_flash`/`_flash_messages` partial pair rather
   than sitting beside it.

   **The toast's own role is conditional, and flattening it is an accessibility regression.** The
   shipped component renders `role="<%= intent == :error ? 'alert' : 'status' %>"` — scaffold that
   expression, not a literal. `status` implies `aria-live="polite"`; `alert` implies `assertive`. A
   toast hard-coded to `status` announces an error politely, so a screen-reader user hears it only
   after whatever is already queued. This step previously said the toast *"carries `role="status"` and
   nothing beside it"*, which misread the doctrine's *"the ROLE carries the severity, and nothing
   beside it"* — a sentence about **not adding `aria-live`**, not about fixing the role's value.

   So the layout renders **no flash partial**. A scaffold that leaves one in ships two notification
   surfaces, and the inline one is permanent — which is how a project ends up with all-permanent
   notices and no auto-dismiss anywhere.

Use **[references/reference-implementation.md](../../skills/design-system/references/reference-implementation.md)**
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

   **Write the pack SLUG too** — `config.x.brand.pack = "<slug>"` (#788). It is the only record of
   which pack this project scaffolded from, and `check_token_drift.py` needs it to know what to
   compare the managed token block against. **`default_variant` is not a substitute**: for the
   `fidara` pack it is `fmworkflows`, which is a variant, not a pack directory. Without the slug the
   drift check refuses rather than guessing — correct, but it means the check cannot run.

   ```ruby
   # config/initializers/brand.rb
   Rails.application.configure do
     config.x.brand = ActiveSupport::OrderedOptions.new
     config.x.brand.pack = "reliance"          # the pack this project scaffolded from
     config.x.brand.default_variant = "reliance"
     config.x.brand.variants = {
       "reliance" => { name: "Reliance Health", endorsement: nil,             mark: "reliance-mark.svg" },
       "retask"   => { name: "Retask",          endorsement: "by Reliance Health", mark: "reliance-mark.svg" },
     }
   end
   ```

## Brand-pack verification — and file an issue when it fails

The pack lint proves a pack is *internally* complete. It cannot prove the generated theme
actually works in a real app, so **this first run is the verification**. Check all four, and on
any failure file an issue with `/rails-flow:report` (component `design-flow` / `design-system`)
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
`@theme` needs a Tailwind rebuild. Point at **`/design-flow:canvas`** for pre-code composition —
it writes a Claude Design prompt carrying this project's own tokens and component catalog, and
`/design-flow:port` brings the result back as ERB. Finally: if any generated component fails to compile or
render in this app, it's a toolchain defect — report it with **`/rails-flow:report`**
(component `design-flow` / `design-system`) so the doctrine gets fixed upstream.

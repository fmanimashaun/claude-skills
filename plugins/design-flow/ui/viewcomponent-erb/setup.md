# `/design-flow:setup` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:setup` after `ui_adapter.py` resolves this adapter. The command owns the brand-pack steps (choose, lint, create), the
asset-home check and the verification; this file is the Rails 8 stack's preconditions, markers and scaffold.

## Preconditions for this adapter

Rails 8 + Hotwire (importmap) + **Tailwind v4** (`tailwindcss-rails`, CSS-first `@theme`, no
`tailwind.config.js`/npm). Confirm `app/assets/tailwind/application.css` exists.


The brand record is `config/initializers/brand.rb` (`config.x.brand.pack`): if it already records a pack that differs from the one asked
for, stop and say so.

## Markers and idempotency

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
   `docs/design/assets/brand/01-logos/` exists, use its exact SVG paths; otherwise scaffold
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

Use **rails-stack's `skills/design-system/references/reference-implementation.md`** (in rails-stack)
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


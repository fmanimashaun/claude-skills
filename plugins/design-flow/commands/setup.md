---
description: Scaffold the design system into the project through its UI adapter — token architecture (brand primitives -> semantic roles -> Utopia fluid scale), layout-primitive recipes, base components, dark mode. Idempotent; brand-parameterized.
argument-hint: "[brand pack: <pack> or <pack>:<variant>, e.g. fidara:fmworkflows]"
---

# /design-flow:setup — $ARGUMENTS

Install the **design-system** system into this project. Follow the skill doctrine
(rails-stack's `skills/design-system/SKILL.md` + references) exactly — this command applies it.

## Preconditions

**The `design-system` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`design-system`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

The stack facts the scaffold needs (framework, CSS toolchain, where the tokens live) are the UI adapter's, resolved below.

`$ARGUMENTS` selects the **brand pack**: `<pack>` or `<pack>:<variant>` (e.g. `fidara`,
`fidara:fmworkflows`, `acme`). **A project uses exactly one pack** (#919). If `$ARGUMENTS` is empty, do not
assume: list the packs that ship (`ls "${CLAUDE_PLUGIN_ROOT}/brands"` plus any `brands/` in the project) and
ask which one — `fidara:fmworkflows` is the default only once the user confirms it. If
the project's brand record (where, is the adapter's) already records a pack and it differs from the pack asked for,
stop and say so: scaffolding a second pack over the first's managed block leaves two packs' roles in one
block, which is what `check_token_drift` reports as drift. State the chosen pack in the first line of your
report. Read the pack from
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
  rails-stack's `skills/design-system/references/brand.md`, section *Starting a pack when the
  client has no palette*, in rails-stack. It is an ordered path: logo colour → does the product recede → hue
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

**Nothing may still sit at an old place (#1779).** design-flow's files moved under `docs/design/`, and a project that has not moved them yet would be misread: it would scaffold placeholder logos over the real ones (the brand logos moved to `docs/design/assets/brand/`). Run this first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_home.py" --check
```

Exit 1 means an old place still holds files. **Stop**, run the command it prints (`asset_home.py --migrate`, once), and start this command again.

## Which stack renders this

Resolve the project's UI adapter from its stack descriptor:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py"
```

It prints JSON: `dir` (the adapter directory), `tokens_file` and `agents.composer`. **Exit 2 means it cannot say** (no recognised stack, a
stack with no UI adapter yet): quote its message and stop; never scaffold another stack's design system. Read **`<dir>/setup.md`**: it holds
the stack's preconditions (confirm them before writing anything), the markers that fence the managed blocks, and the scaffold steps. The
brand-pack steps above and the verification below are the same for every stack.

## Idempotency

Own only what you scaffold; re-runnable. Wrap generated token blocks and recipes between the **exact markers** the adapter's `setup.md`
names. **Inside is the plugin's; outside is yours.** A local extension — a project's own primitive, an extra role it needs — goes
**outside** the markers and is never touched. On re-run, refresh inside only. The marker is also what `check_token_drift.py` keys on: without
a line between plugin-owned and project-owned tokens, a drift check either flags every legitimate extension or checks nothing (#754). Never
overwrite an existing customized component without showing a diff. Stage only files you authored; `git status` after.

## Scaffold

Follow the adapter's scaffold steps in order, using the brand pack chosen above for the theme layer only.

## Brand-pack verification — and file an issue when it fails

The pack lint proves a pack is *internally* complete. It cannot prove the generated theme
actually works in a real app, so **this first run is the verification**. Check all four, and on
any failure file an issue with `/rails-flow:report` (component `design-flow` / `design-system`)
before continuing:

1. **The token layer builds.** The generated token and role layer compiles without error.
2. **Roles resolve.** Spot-check a few rendered surfaces in light *and* dark: `bg-primary`,
   `bg-card`, `text-muted-foreground`, `border-border`. **If a pack passed the lint but something
   still renders a stock Tailwind colour, the 22-role contract is incomplete** — that is the
   highest-value defect to report, because it means the lint is checking the wrong set and every
   future pack inherits the hole. Include which utility rendered unbranded.
3. **The logo component renders** the pack's mark, and the endorsement matches the selected variant —
   present for a product variant, absent for a parent (a parent does not endorse itself). Getting
   "X by X" or a missing endorsement means the manifest wiring is wrong.
4. **Dark mode re-points.** Toggling theme changes the surfaces; a surface that stays put means a
   `.dark` re-point is missing from the pack or the lint's `DARK_REQUIRED` set is wrong.

Report the **pack slug, the lint output, the failing step, and the exact build/render error**. A
pack-related failure is almost always a doctrine or lint defect rather than a project problem —
which is precisely why it belongs upstream instead of being patched locally.

## Report

Files created, brand selected, the component-library decision, and the entry points:
`/design-flow:component` to author UI, `/design-flow:audit` to check drift. Remind that a new
token layer needs a rebuild.
Then give the next step:

**Next: the application shell, as mock-ups.** If `docs/product/mockups/shell.md` does not exist, this project has no recorded shell. Before any feature UI, produce mock-ups of the application's core shell (layout, navigation) and its foundation screens, following the design system you just scaffolded, and get them approved. The approved shell mock-up is recorded in `docs/product/mockups/shell.md` (`Kind: shell`, see `check_mockup_gate.py --adopt-shell`); every later UI mock-up must be drawn inside it. `/design-flow:canvas` and `/design-flow:port` (Claude Design import) remain available as an optional way to draw a mock-up, not the way a screen enters the project.

Finally: if any generated component fails to compile or
render in this app, it's a toolchain defect — report it with **`/rails-flow:report`**
(component `design-flow` / `design-system`) so the doctrine gets fixed upstream.

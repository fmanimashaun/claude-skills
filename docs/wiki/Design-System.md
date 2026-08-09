# Design system

`fidara-design` is the design doctrine; `design-flow` is the flow that applies it. The system is
token-first: components read tokens, tokens come from a brand pack, and a brand swap is a config
change rather than a rewrite.

## The order of work

1. **[Reference research](https://github.com/fmanimashaun/claude-skills/blob/main/skills/fidara-design/references/reference-research.md)** — before
   any design. Gather references for the *kind of problem*, work out **why** each works, and build
   from the mechanisms rather than the surface. Skip it and you do not get nothing: you get the
   median of everything the model has seen, which is the stock-SaaS look.
2. **`/design-flow:setup`** — tokens, brand pack, the base system.
3. **`/design-flow:component`** — build against the system, just-in-time, never batch-built.
4. **`/design-flow:audit`** — conformance is the gate; **`critique`** is the lens and is advisory.

## Research first, and it is enforced

Research settles the **style**, and the style settles which assets exist at all — a `minimalist-ink`
family needs line art on brand grounds, a `character-world` family needs a recurring cast. Different
rows, different counts, different money.

So `/design-flow:assets --check` refuses a plan with no research record. The failure is otherwise
invisible: a plan written without research looks *exactly* like one written with it.

Three rules the research record must satisfy: **three sources minimum and never all from one
category** (direct competitors converged by copying each other), **a mechanism rather than a brand
name** (*"looks like Linear"* cannot be applied to a different subject), and **something rejected**
(a record where everything was adopted is a shopping list).

## The asset pipeline

Four tiers, and only the last two cost money:

| tier | what | cost |
|---|---|---|
| 1 | product screenshot | free — the product *is* the asset |
| 2 | brand geometry from `brand.json` | free — CSS/SVG from tokens |
| 3/4 | illustration, motion | **paid**, and last on purpose |

`/design-flow:assets` scaffolds the config — **the agent generates by default, so no API key is
written at all** — holds the plan of what the product needs, and refuses to start a plan the budget cannot finish — because generating until the
money stops leaves an *arbitrary* half-built set, and a half-built family is not a cheaper library,
it is an incoherent one.

`/design-flow:generate` **mostly refuses**, and that is the design. It refuses an unsearched library,
an unrecorded tier-1/2 refusal, a free-typed prompt, a missing aggregator, a cost over the ceiling,
or a ladder climb with no stated acceptance check — each **before** any call.

Groups are **atomic**: a hero still and the motion loop that animates it are one artefact in two
files, so buying the loop alone is worse than buying neither.

## pen.dev — optional, on both sides of the code boundary

If a composition surface is available, design-flow uses it for two distinct jobs. **Neither is ever
required**: no command stops for want of pen, and a machine without it behaves exactly as it did
before the tier existed.

**Making assets.** A custom icon or spot illustration is composed and then **compiled** to SVG, not
exported — every design tool's SVG export emits hardcoded hex, which `design-auditor` refuses by
name, while a compiled asset is `fill="var(--primary)"` and serves light and dark from one file. An
OG or social card is **exported** raster instead, because its value is real type at a fixed size and
there is nothing to compile to.

**Exploring screens.** Divergence in `/design-flow:variants` costs N × ERB — every option is a full
`ui-composer` dispatch writing real view code before it can be compared. The `design-explorer` agent
composes the options in pen instead, so the ERB price is paid once, for the one that won.

**What joins the two is the mirrored library.** `pen_library.py` generates a `.pen` document from
`theme.css` and `components.md` — the same rows `ui-composer` builds from — covering **all 51
component rows** with role tokens in both themes. That is what makes exploring meaningful rather than
decorative: compose from components the codebase does not have and you have chosen something
unbuildable.

The library file doubles as the scratchpad, so compositions live beside the components and a rebuild
preserves them. `check_component_shapes.py` fails the build if a component is added to the catalogue
without a shape, because a component missing from pen is one an agent reaches past and never misses.

## Two files that are not the same thing

- `docs/assets/plan.json` — **what the product needs**, written once from the brief
- `docs/assets/manifest.json` — **what the project owns**, appended as each asset lands

The gap between them is the remaining work. Keep only the manifest and a library nobody has finished
planning looks finished.

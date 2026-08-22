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

## Claude Design — composing before the code exists

Pre-code composition is Claude Design's job. `/design-flow:canvas` writes the prompt — carrying this
project's **own** `@theme` role tokens, the real component catalog from `component-shapes.json`, and
the band sequence for the surface — and `/design-flow:port` brings the chosen artboard back as ERB
that uses the components the codebase actually has.

That last part is what makes composing meaningful rather than decorative: **choose a composition
made of components the codebase does not have and you have chosen something unbuildable.** So
`check_component_shapes.py` fails the build if a component is added to the catalogue without a shape
entry — a component missing from the catalog is one the canvas invents instead of reaching for.

`/design-flow:variants` remains the other route, and answers a different question: it generates N
compositions as **running screens** plus a switcher, so an aesthetic decision is made by comparing
real pages rather than pictures. It costs N × ERB, deliberately.

**A pen.dev tier used to sit here**, composing options and compiling icons to token-native SVG. It
was retired in #766 — Claude Design covers the composition half, and keeping both meant two homes
for one concern.

## Two files that are not the same thing

- `docs/assets/plan.json` — **what the product needs**, written once from the brief
- `docs/assets/manifest.json` — **what the project owns**, appended as each asset lands

The gap between them is the remaining work. Keep only the manifest and a library nobody has finished
planning looks finished.

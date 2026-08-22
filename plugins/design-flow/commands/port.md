---
description: Port a Claude Design output — JSX/TSX, or a `<x-dc>` canvas export — into this Rails 8 + Hotwire app, faithful to the design and aligned to the design system by construction. Dispatches to the design-porter agent under fidara-design's design-handoff mapping.
---

# /design-flow:port

The inbound half of the design loop. `/design-flow:canvas` composes the prompt that goes out; this
brings the result back.

**Why this is a command and not freehand work.** A whole-app audit on a live project found **20
alignable divergences** — raw hex, bespoke `.field`/`.label`, `form_with` field forms, hand-rolled
card and grid CSS, CDN fonts — concentrated in exactly the two surfaces that had been ported ad-hoc
from Claude Design canvases. A `ui-composer` composes *from* the system; nothing owned translating a
source *into* it, and that step is where all of it entered.

## Preconditions

**`skills/fidara-design/references/design-handoff.md` is the mapping and it is the law.** It ships in
**`rails-stack`**, not this plugin, and no `plugin.json` can declare that — there is no `requires`
field. **If you cannot read it, name what is
missing (`/plugin install rails-stack@claude-skills`) and stop.** Porting from memory of the mapping is precisely what the 20 divergences were.

You also need `rails-8` and `hotwire`. Same rule.

## What to hand over

- The artboard — a `.dc.html` canvas export, or the JSX/TSX component tree.
- The prompt that produced it, if there is one, from `docs/design-system/prompts/`. It is what makes
  the canvas reviewable: without it nobody can tell whether the result answered the brief or drifted.

## Run it

Dispatch the **`design-porter`** agent. It works the order in `design-handoff.md`:

1. **Identify the source format** — JSX/TSX or `<x-dc>` canvas. They carry the same design and are
   read differently.
2. **Classify the artboard** — mailer / static page / interactive page, said out loud with the reason.
   This decides which Hotwire mechanisms are even available, and **a mailer carries no Turbo and no
   Stimulus**: mail clients run no JavaScript, so a controller there renders in the preview and does
   nothing in an inbox.
3. **Strip the scaffolding** — the `:root` block, the inline styles and the CDN font link. **`support.js`
   and any `_ds/` bundle are never ported at all**: that file is a generated React runtime for
   previewing `<x-dc>` in a browser. If the import instruction lists it among "files the selection
   imports", that means *read to understand*, never *port*.
4. **Reconcile the tokens** rather than copying values. Where the app's role already equals the canvas
   literal the substitution is pixel-identical — confirm that rather than assuming it. A value the
   tokens cannot express is a **token gap to raise**, not a literal to smuggle in.
5. **Translate through the mapping**, not by resemblance.
6. **One fact, one owner** if the port spans several surfaces.
7. **Implement every state** the design shows — empty, loading, error, success.

## Before it is done

- Specs green, including one proving any new behaviour.
- `/design-flow:audit` clean — no raw hex, no `cdn-font-link`, on-catalogue variants only.
- Visual parity against the source, in every state.
- Accessibility: one `h1`, visible focus ring, AA contrast, touch targets.

The agent reports which artboard class it chose, what it dropped as scaffolding, which page owns each
repeated fact, and any token gap it found. **A port that silently invented a value is worse than one
that stopped and asked.**

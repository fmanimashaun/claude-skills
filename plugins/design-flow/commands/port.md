---
description: Port a Claude Design output — JSX/TSX, or a `<x-dc>` canvas export — into this app, faithful to the design and aligned to the design system by construction. Resolves the project's UI adapter from its stack descriptor and dispatches to that adapter's porter agent.
---

# /design-flow:port

The inbound half of the design loop. `/design-flow:canvas` composes the prompt that goes out; this
brings the result back.

**Why this is a command and not freehand work.** A whole-app audit on a live project found **20
alignable divergences** — raw hex, bespoke field and label styles, hand-built form markup, hand-rolled
card and grid CSS, CDN fonts — concentrated in exactly the two surfaces that had been ported ad-hoc
from Claude Design canvases. A composer agent composes *from* the system; nothing owned translating a
source *into* it, and that step is where all of it entered.

## Which stack renders this

The porting steps are the stack's, not this command's. Resolve the adapter the project's stack descriptor names:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py"
```

It prints JSON: `dir` (the adapter directory), `agents.porter` (the agent to dispatch), `tokens_file`. **Exit 2 means it cannot say**
(no recognised stack, a stack with no UI adapter yet, an unreadable manifest): quote its message and stop. Do not fall back to another
stack's steps. A project without a stack plugin installed can name the adapter itself with `--implementation <id>`.

## Preconditions

**Nothing may still sit at an old place (#1779).** design-flow's files moved under `docs/design/`, and a project that has not moved them yet would be misread: it would find no prompt for the surface it is porting (the prompts moved to `docs/design/prompts/`). Run this first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/asset_home.py" --check
```

Exit 1 means an old place still holds files. **Stop**, run the command it prints (`asset_home.py --migrate`, once), and start this command again.

## What to hand over

- The artboard — a `.dc.html` canvas export, or the JSX/TSX component tree.
- The prompt that produced it, if there is one, from `docs/design/prompts/`. It is what makes
  the canvas reviewable: without it nobody can tell whether the result answered the brief or drifted.

## Run it

Read **`<dir>/port.md`** and follow it: its preconditions, the checklist extraction, the porter's order of work and the
"before it is done" list are that stack's. Dispatch the **`design-flow:<agents.porter>`** agent it names.

Whatever the stack, a port that silently invented a value is worse than one that stopped and asked: the porter reports which
artboard class it chose, what it dropped as scaffolding, which page owns each repeated fact, and any token gap it found.

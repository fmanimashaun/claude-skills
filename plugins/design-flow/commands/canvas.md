---
description: Compose a Claude Design prompt for one surface that carries this project's own tokens, component catalog and band sequence — so the canvas comes back speaking the system and the port is a reconciliation rather than a translation. Saves to docs/design-system/prompts/.
---

# /design-flow:canvas

The outbound half of the design loop. `/design-flow:port` brings a canvas *in*; this decides what that will cost.

**Why generate the prompt at all.** A real artboard measured during this command's design declared
**50 of its own `:root` tokens** and made **755 `var(--…)`** references. Those names happened to match
the project's, and nothing had made them match — the prompt was hand-written, and the alignment was
luck. When it is not luck, the canvas invents a vocabulary and the port becomes a translation between
two systems, judgement call by judgement call. That is where a whole-app audit found **20 alignable
divergences**.

## Preconditions

**`skills/fidara-design/references/` must be readable.** It ships in **`rails-stack`**, not this
plugin, and no `plugin.json` can declare that — there is no `requires` field. The catalog and the band
sequence come from there. **If you cannot read it, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** A prompt composed from memory of the catalog
invites the canvas to draw components that do not exist, which is the whole failure being prevented.

## 1. Name the surface, and read what governs it

Which surface is this — dashboard, detail, settings, auth, a marketing page? The band sequence and the
shell come from `page-anatomies.md`; do not invent page structure, for the same reason
`/design-flow:component` step 1 forbids it.

## 2. Compose the derived half

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/design_prompt.py" --surface <surface>
```

It emits the part that would rot if retyped: this project's **role tokens read from its own
`@theme`**, the **component catalog derived from `component-shapes.json`**, and the **band sequence**.

**Read its output before using it.** If it reports the prompt is incomplete — no `@theme` found, no
catalog, no anatomy for that surface — that gap leads the document deliberately. Fix it rather than
sending the prompt: a prompt that quietly omits the token list still looks like a prompt, and the
canvas it produces is the one nobody can port.

## 3. Author the judgement half

The script will not write this and should not. Add, in the project's own words:

- **What the surface is for**, and who arrives at it expecting what.
- **The tone**, and where it sits against the brand — `art-direction.md` governs; do not restate it.
- **Which states must be shown.** An artboard shows a moment; the surface has to hold empty, loading,
  error and populated. Ask for all of them explicitly or you will receive only the flattering one.
- **What is out of scope**, so the canvas does not design a feature nobody asked for.

## 4. Save it where the loop expects it

`docs/design-system/prompts/<surface-slug>.md`. That directory is the record of what was asked for,
and it is what makes a returned canvas reviewable — without it, nobody can tell whether the canvas
answered the brief or drifted from it.

## 5. When the canvas comes back

Hand it to **`/design-flow:port`** (the `design-porter` agent) and read
`fidara-design/references/design-handoff.md` first. If step 2 reported no gaps, the returned `:root`
should carry **your** token names — which is what makes §2's *"drop the `:root` block"* safe by
construction rather than by careful reading.

---
description: Scaffold native-shell parity (Phase 2) into the app through its UI adapter — native-app detection + body flags, JSON path configuration, bridge components, safe-area + min-h-touch wiring, and table->summary cards. Reuses the existing design system; the native shells stay in their own repos.
argument-hint: "[surface: ios | android | both]"
disable-model-invocation: true
---

# /design-flow:mobile — $ARGUMENTS

Add the **web side** of native-shell parity so the same UI runs in the native shells with correct chrome. This is Phase 2 — web is
already done; this does NOT modify any native app repo (Kotlin/Swift shells live there).

## Which stack renders this

Native parity is built from the stack's own mechanisms, so it is the adapter's. Resolve it from the project's stack descriptor:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py"
```

It prints JSON: `dir` (the adapter directory) and `agents.composer`. **Exit 2 means it cannot say** (no recognised stack, or a stack whose
adapter ships no `mobile.md`): quote its message and stop; never fall back to another stack. Read **`<dir>/mobile.md`**, follow its scaffold,
and delegate to the **`design-flow:<agents.composer>`** agent. Doctrine: rails-stack's `skills/design-system/references/mobile.md`;
code: `mobile-reference-implementation.md`.

## Preconditions

**The `design-system` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`design-system`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

The app is already set up with `/design-flow:setup` (tokens, primitives, components). `$ARGUMENTS` = which native surface(s) to
configure paths for (`ios | android | both`; default `both`). Idempotent; marker-guarded; stage only files you author.

## Guardrails

- **Never gate core functionality on the native app** — bridges only enhance.
- No mobile token fork — reuse the same tokens; the fluid scale handles the viewport.
- The native shell/UI (Kotlin/Swift) is out of scope — this is the web contract the shells consume. Native visual parity comes later via
  Phase 3 token export.

## Report

Files created (concern, path configs, bridge controllers, updated layout), the surfaces
configured, and a reminder to verify the bridges in a real native-shell build (this scaffolds
the web contract; the native side is exercised in the app repos).

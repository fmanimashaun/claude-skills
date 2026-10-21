---
description: Export native design tokens (Phase 3) from the app's token source of truth — generate Android (colors.xml + Theme.Fidara) and iOS (SwiftUI Color) token files so fully-native screens match the web by construction. Writes to tmp/; does NOT modify native app repos.
argument-hint: "[android | ios | both]"
disable-model-invocation: true
---

# /design-flow:tokens — $ARGUMENTS

Generate native token files from the single token source of truth, so fully-native
Android/iOS screens match the web. Follow rails-stack's `skills/design-system/references/native-tokens.md`.
This runs in the **app** (which owns the tokens); it writes outputs to `tmp/` for the
maintainer to carry into the native repos — it **never** writes into a native app repo.

## Preconditions

**The `design-system` skill must be readable.** It ships in the **`rails-stack`** plugin, not
this one, and no `plugin.json` can declare that — there is no `requires` field. So confirm you can read
`design-system`'s `SKILL.md` before doing anything. **If you cannot, name what is missing
(`/plugin install rails-stack@claude-skills`) and stop.** Do not proceed from memory of the catalog:
this command's own agents call that doctrine *"the law"*, and improvising it is how a scaffold invents
tokens and components that no gate will recognise (#513).

An app set up with `/design-flow:setup` (so its token file carries the primitives and the role tokens). `$ARGUMENTS` = target(s) (`android | ios | both`; default `both`).

## Which stack renders this

How the tokens are read and exported is the stack's. Resolve the project's UI adapter from its stack descriptor:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py"
```

It prints JSON with `dir` and `tokens_file`. **Exit 2 means it cannot say**: quote its message and stop; never fall back to another
stack. Read **`<dir>/tokens.md`** and do what it says; it names the source of truth, the exporter and the output layout.

## Guardrails

- **Generated, never hand-edited** — re-run on token changes; keep the token source canonical.
- Same **role names** across web/Android/iOS (a native screen reads like the web).
- Output stays in `tmp/`; the maintainer copies it into the native app repo via **that repo's**
  flow. This command does not touch native repos.

## Report

Files written under `tmp/design-tokens/{android,ios}/`, token counts, and the next step
(carry into the native repo). Note that visual parity holds only if native screens consume the
exported roles rather than hardcoding values.

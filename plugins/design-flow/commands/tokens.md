---
description: Export native design tokens (Phase 3) from the Rails app's Tailwind @theme — generate Android (colors.xml + Theme.Fidara) and iOS (SwiftUI Color) token files so fully-native screens match the web by construction. Writes to tmp/; does NOT modify native app repos.
argument-hint: "[android | ios | both]"
---

# /design-flow:tokens — $ARGUMENTS

Generate native token files from the `@theme` single source of truth, so fully-native
Android/iOS screens match the web. Follow `skills/fidara-design/references/native-tokens.md`.
This runs in the **Rails app** (which owns the `@theme`); it writes outputs to `tmp/` for the
maintainer to carry into the native repos — it **never** writes into a native app repo.

## Preconditions

A Rails app set up with `/design-flow:setup` (so `app/assets/tailwind/application.css` has the
`@theme` + `:root` role tokens). `$ARGUMENTS` = target(s) (`android | ios | both`; default `both`).

## Do (per native-tokens.md)

1. Install/refresh `bin/export_design_tokens` (the reference Ruby script) if absent.
2. Run it: parse `application.css`, **resolve role → primitive → hex**, and emit to
   `tmp/design-tokens/`:
   - **Android**: `values/colors.xml` (`fd_*`) + `theme_map.xml` (`Theme.Fidara` mapping
     Material 3 attrs → `fd_*`); dark mode → `values-night/colors.xml` from the `.dark` roles.
   - **iOS**: `FidaraTokens.swift` (`Color.fd*`); dark → asset-catalog dark variants.
3. Also export radius (→ ShapeAppearance / Swift constants), spacing (→ dimens / constants),
   and the type families (Bricolage/Newsreader/Overpass as downloadable-font references). Fluid
   `--text-step-*` → fixed native sizes (the `clamp()` max), documented as such.
4. Report a diff summary: N color roles + radius/spacing/type exported, per target.

## Guardrails

- **Generated, never hand-edited** — re-run on token changes; keep the `@theme` canonical.
- Same **role names** across web/Android/iOS (a native screen reads like the web).
- Output stays in `tmp/`; the maintainer copies it into the native app repo via **that repo's**
  flow. This command does not touch native repos.

## Report

Files written under `tmp/design-tokens/{android,ios}/`, token counts, and the next step
(carry into the native repo). Note that visual parity holds only if native screens consume the
exported roles rather than hardcoding values.

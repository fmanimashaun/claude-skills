# `/design-flow:tokens` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:tokens` after `ui_adapter.py` resolves this adapter. The source of truth is the Tailwind v4 `@theme` plus the
`:root` role tokens in `app/assets/tailwind/application.css` (the adapter's `tokens_file`). The command owns the guardrails and the report.

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


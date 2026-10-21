# Native Token Export (Phase 3)

Fully-native screens (Android/Kotlin, iOS/Swift) must match the web by **construction**, not
by hand. The `@theme` block ([foundations-tokens.md](foundations-tokens.md)) is the single
source of truth; native resource files are **generated** from it. Never hand-diverge native
values — re-run the export.

The bridge is the **semantic role names**: they translate 1:1 to Material 3 / iOS color roles,
so a screen written natively uses the same vocabulary as the web.

## Role → platform mapping

| Fidara role (web) | Material 3 (Android) | iOS (SwiftUI) |
|---|---|---|
| `background` / `foreground` | `colorBackground` / `colorOnBackground` | `Color.background` / `.foreground` |
| `card` / `card-foreground` | `colorSurfaceContainer` / `colorOnSurface` | `.card` / `.cardForeground` |
| `popover` / `popover-foreground` | `colorSurfaceContainerHigh` / `colorOnSurface` | `.popover` / … |
| `primary` / `primary-foreground` | `colorPrimary` / `colorOnPrimary` | `.primary` / `.onPrimary` |
| `secondary` / `secondary-foreground` | `colorSecondaryContainer` / `colorOnSecondaryContainer` | `.secondary` / … |
| `muted` / `muted-foreground` | `colorSurfaceVariant` / `colorOnSurfaceVariant` | `.muted` / `.mutedForeground` |
| `accent` / `accent-foreground` | `colorTertiaryContainer` / `colorOnTertiaryContainer` | `.accent` / … |
| `destructive` / `destructive-foreground` | `colorError` / `colorOnError` | `.destructive` / `.onDestructive` |
| `border` / `input` | `colorOutlineVariant` | `.border` / `.input` |
| `ring` | (focus indicator color) | `.ring` |

Radius → Material `ShapeAppearance` (sm/md/lg from `--radius`); type families → downloadable
fonts (Bricolage/Newsreader/Overpass); spacing → `dimens.xml` / Swift constants.

**Fluid type is web-only.** Native uses fixed sizes: export each `--text-step-*` as a single
value (the `clamp()` **max**, the comfortable desktop size) — or emit min+max and let native
pick per size class. Document which; don't try to reproduce `clamp()` natively.

## Reference export script (parse `@theme` → native files)

`bin/export_design_tokens` (Ruby, dependency-light). It resolves **role → primitive → hex**
(roles are `var(--color-fm-…)`), then writes Android + iOS token files. Reference quality —
adapt paths/roles to the project.

```ruby
#!/usr/bin/env ruby
# frozen_string_literal: true
# Reads app/assets/tailwind/application.css and emits native token files from the @theme.
require "fileutils"
css = File.read("app/assets/tailwind/application.css")

# 1) primitives: --color-fm-*: #hex  (and any literal-hex vars)
prim = css.scan(/--([\w-]+):\s*(#[0-9A-Fa-f]{3,8})\b/).to_h
# 2) roles: --primary: var(--color-fm-cerulean)  → resolve to hex via prim
roles = {}
css.scan(/--([\w-]+):\s*var\(--([\w-]+)\)/).each { |name, ref| roles[name] = prim[ref] if prim[ref] }
# (also capture roles defined as a literal hex)
css.scan(/--([\w-]+):\s*(#[0-9A-Fa-f]{3,8})\b/).each { |name, hex| roles[name] ||= hex }

ROLE_TO_M3 = {
  "background" => "colorBackground", "foreground" => "colorOnBackground",
  "primary" => "colorPrimary", "primary-foreground" => "colorOnPrimary",
  "secondary" => "colorSecondaryContainer", "muted" => "colorSurfaceVariant",
  "muted-foreground" => "colorOnSurfaceVariant", "destructive" => "colorError",
  "destructive-foreground" => "colorOnError", "border" => "colorOutlineVariant",
  "card" => "colorSurfaceContainer", "ring" => "colorPrimary" # focus
}.freeze

# --- Android: res/values/colors.xml + a theme snippet ---
FileUtils.mkdir_p("tmp/design-tokens/android/values")
File.open("tmp/design-tokens/android/values/colors.xml", "w") do |f|
  f.puts %(<?xml version="1.0" encoding="utf-8"?>\n<resources>)
  roles.each { |name, hex| f.puts %(  <color name="fd_#{name.tr('-', '_')}">#{hex.upcase}</color>) }
  f.puts "</resources>"
end
File.open("tmp/design-tokens/android/values/theme_map.xml", "w") do |f|
  f.puts %(<!-- Theme.Fidara: map M3 attrs to fd_* colors -->\n<resources>\n  <style name="Theme.Fidara" parent="Theme.Material3.DayNight">)
  ROLE_TO_M3.each { |role, attr| f.puts %(    <item name="#{attr}">@color/fd_#{role.tr('-', '_')}</item>) if roles[role] }
  f.puts "  </style>\n</resources>"
end

# --- iOS: a SwiftUI Color extension ---
FileUtils.mkdir_p("tmp/design-tokens/ios")
def hex_to_rgb(h) = h.delete("#").scan(/../).first(3).map { |x| (x.to_i(16) / 255.0).round(4) }
File.open("tmp/design-tokens/ios/FidaraTokens.swift", "w") do |f|
  f.puts "import SwiftUI\n\npublic extension Color {"
  roles.each do |name, hex|
    r, g, b = hex_to_rgb(hex)
    f.puts %(    static let fd#{name.split('-').map(&:capitalize).join} = Color(red: #{r}, green: #{g}, blue: #{b}))
  end
  f.puts "}"
end
puts "Exported #{roles.size} role tokens -> tmp/design-tokens/{android,ios}/"
```

Output (into `tmp/design-tokens/`, for the maintainer to copy into the native app repos — the
export never writes into native repos itself):
- `android/values/colors.xml` (`fd_*` colors) + `theme_map.xml` (`Theme.Fidara` mapping M3
  attrs → `fd_*`).
- `ios/FidaraTokens.swift` (`Color.fd*` constants).

## Doctrine

- **Generated, never hand-edited.** Re-run on any token change; commit the outputs in the
  native repo via that repo's own flow (not from here).
- **Same role names** across web/Android/iOS so a native screen reads like the web.
- Export **colors + radius + spacing + type families** first; dark mode = export the `.dark`
  role values into a `values-night/colors.xml` (Android) / dark asset variant (iOS).
- This marketplace ships the **doctrine + reference script**; the actual run happens in the
  Rails app (which has the `@theme`) via `/design-flow:tokens`, and the outputs are carried
  into the native app repos by their maintainers. We do not modify native repos here.

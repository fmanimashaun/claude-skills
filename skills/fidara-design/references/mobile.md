# Mobile Parity

The design system is **one system across web and mobile.** Mobile is not a separate design —
it's the same tokens, primitives, and components rendered in a native shell, plus a thin layer
of native chrome. This keeps a single source of truth: fix a token or component once, both
surfaces update.

## Model: Hotwire Native (web-first), native chrome on top

The primary mobile path is **Hotwire Native** (iOS + Android): the app is a native shell
wrapping the same server-rendered Hotwire screens. So **95% of UI is the web UI** — the
tokens, layout primitives, and catalog components render unchanged in the native webview. The
native side adds only what a webview can't: a native tab bar, native navigation/transitions,
and platform integrations via bridge components.

- **Detect the shell:** `turbo_native_app?` → emit `body.mobile-app` (+ `native-tabs` meta) and
  a `native-bridge` Stimulus controller. Web-only chrome (e.g. the web top-nav) hides under
  `body.mobile-app`; native provides its own.
- **Path configuration** decides which routes are native screens vs webview, modal vs push,
  and which get a native title/tab. Keep it in `config/` and treat it as design surface (it
  defines the app's navigation model).
- **Bridge components** (Strada-style): a web element declares a bridge; the native side renders
  the platform-native equivalent (e.g. a submit button becomes a native nav-bar button, a menu
  becomes a native action sheet). Design these as *progressive enhancement* — the web control
  works if the bridge is absent.

## Tokens & responsive on mobile

- **Same `@theme`.** No mobile token fork; the fluid Utopia scale already handles small
  viewports (that's the point of fluid + intrinsic — a phone is just a narrow container).
- **Safe areas are mandatory on native.** Apply `pt-safe`/`pb-safe`/`pl-safe`/`pr-safe` to fixed
  chrome (headers, bottom bars, FABs) so content clears notches/home indicators. (These
  utilities exist but were unused — the native shell is where they earn their keep.)
- **Touch targets:** `min-h-touch` (44px) is non-negotiable on mobile — it matches iOS HIG (44pt)
  and Material (48dp ≈ our 44 floor). Wire it on every interactive control.
- **Density:** prefer the comfortable defaults on mobile; don't ship the compact density to touch.
- **Motion & gestures:** respect `prefers-reduced-motion`; keep transitions short; let native
  handle scroll/overscroll and back-gesture (don't trap them).

## Component behavior on mobile (from the catalog)

- **Nav** → the sidebar is already a mobile drawer `<lg`; under a native shell, prefer the
  **native tab bar** for top-level nav and reserve the drawer for secondary. Header collapses as
  specified in [responsive.md](responsive.md).
- **Modal/Drawer** → the same Imposter + focus-trap components work in the webview; via a bridge
  they can promote to native sheets. Keep Esc/back-button parity (Android back closes the top
  dismissable layer).
- **Tables** → use the card-stack fallback on mobile (not horizontal scroll) — thumb-friendly.
- **Toasts** → keep clear of the safe-area + native tab bar.
- **Forms** → native keyboards; `inputmode`/`autocomplete` set correctly; inputs stay `min-h-touch`.

## Fully-native screens (Android/Kotlin, iOS/Swift)

Where a screen must be fully native (performance, deep platform integration — e.g. fmworkflows'
Android app), the design system still governs it: **mirror the tokens** in the platform's
resource system so the look matches.
- **Android:** map the `@theme` values into `res/values/colors.xml` + a Material 3 theme
  (`Theme.Fidara`), the type scale into text appearances (Bricolage/Newsreader/Overpass via
  downloadable fonts), the spacing scale into dimens, `--radius` into shape appearances. Use the
  **same semantic role names** (primary/surface/on-surface…) so tokens translate 1:1.
- **iOS:** the analogous asset catalog + a tokens file.
- **Single source of truth:** the `@theme` block is canonical; native resource files are
  generated/derived from it (a future token-export step), never hand-diverged.

## Phased plan

1. **Phase 1 — Web (done).** Tokens, layout primitives, component catalog, responsive doctrine.
2. **Phase 2 — Hotwire Native parity (reference code ready).** `native_app?`/`body.mobile-app`
   wiring; safe-area + `min-h-touch` on chrome; JSON path configuration; the first bridge
   components (nav-button, action-sheet menu, native tab bar); table→card-stack on mobile.
   **Largest win for least effort** — reuses all the web components. Concrete web-side code:
   [mobile-reference-implementation.md](mobile-reference-implementation.md); scaffold it with
   **`/design-flow:mobile`**. (Native Kotlin/Swift shells live in their own app repos.)
3. **Phase 3 — Native token export (reference code ready).** Emits Android (`colors.xml` +
   `Theme.Fidara`) and iOS (SwiftUI `Color`) tokens from the `@theme` so fully-native screens
   match by construction. Mapping + reference export script:
   [native-tokens.md](native-tokens.md); run it with **`/design-flow:tokens`**. Output lands in
   `tmp/` for the maintainer to carry into the native repos — the export never writes into them.

`/design-flow:setup` targets web (Phase 1); `/design-flow:mobile` scaffolds Phase 2;
`/design-flow:tokens` runs Phase 3. This file is the contract all three build to.

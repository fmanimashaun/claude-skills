---
description: Scaffold Hotwire Native parity (Phase 2) into a Rails 8 + Hotwire app — native-app detection + body flags, JSON path configuration, bridge components (button/menu/tab-bar), safe-area + min-h-touch wiring, and table->card-stack. Reuses the existing design system; the native shells stay in their own repos.
argument-hint: "[surface: ios | android | both]"
---

# /design-flow:mobile — $ARGUMENTS

Add the **web side** of Hotwire Native parity so the same UI runs in the native shells with
correct chrome. Delegate to **ui-composer**; follow `skills/fidara-design/references/mobile.md`
(doctrine) + `mobile-reference-implementation.md` (code). This is Phase 2 — web is already done;
this does NOT modify any native app repo (Kotlin/Swift shells live there).

## Preconditions

A Rails 8 + Hotwire app already set up with `/design-flow:setup` (tokens, primitives,
components). `$ARGUMENTS` = which native surface(s) to configure paths for (`ios | android |
both`; default `both`). Idempotent; marker-guarded; stage only files you author.

## Scaffold (per mobile-reference-implementation.md)

1. **Native detection** — a `NativeApp` controller concern (`native_app?` from the UA) + set
   `body.mobile-app` and the `turbo-native:tabs` meta in the layout; hide web-only chrome
   (`[data-web-chrome]`) under `.mobile-app`.
2. **Path configuration** — routes + JSON views (`/configurations/ios`, `/configurations/android`)
   mapping URL patterns to native presentation (modal for `new`/`edit`, default + pull-to-refresh
   otherwise). Keep iOS/Android parallel.
3. **Bridge components** — `app/javascript/bridge/`: base usage + `button` (nav-bar action) and
   `menu` (action sheet) controllers extending `BridgeComponent`, wired as **progressive
   enhancement** (the web control works without the shell). Plus the native tab-bar config.
4. **Safe-area + touch** — apply `pt-safe`/`pb-safe`/… to fixed chrome and `min-h-touch` (44px)
   to every interactive control.
5. **Table → card-stack** — convert dense tables to the `hidden md:table` + `md:hidden` card
   list recipe (thumb-friendly; no horizontal scroll on phones).

## Guardrails

- **Never gate core functionality on the native app** — bridges only enhance.
- No mobile token fork — reuse the same `@theme`; the fluid scale handles the viewport.
- The native shell/UI (Kotlin/Swift) is out of scope — this is the Rails/Hotwire/JS contract
  the shells consume. Native visual parity comes later via Phase 3 token export.

## Report

Files created (concern, path configs, bridge controllers, updated layout), the surfaces
configured, and a reminder to verify the bridges in a real Hotwire Native build (this scaffolds
the web contract; the native side is exercised in the app repos).

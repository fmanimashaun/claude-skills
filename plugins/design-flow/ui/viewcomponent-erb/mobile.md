# `/design-flow:mobile` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:mobile` after `ui_adapter.py` resolves this adapter. The command owns the goal, the preconditions, the
guardrails and the report; this file is the scaffold for a Rails 8 + Hotwire app.

The app is a Rails 8 + Hotwire app already set up with `/design-flow:setup`.

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
5. **Table → summary cards** — below 768px render each row as a designed summary card (name,
   reference, status; 2–3 facts; one action and a chevron), per the design-system skill's
   `mobile-reference-implementation.md` §5. No horizontal scroll at any width.

## Guardrails specific to this adapter

The native shell/UI (Kotlin/Swift) is out of scope — this is the Rails/Hotwire/JS contract the shells consume.

## Report

Name the files created: the concern, path configs, bridge controllers and the updated layout. Remind the user to verify the bridges in
a real Hotwire Native build.

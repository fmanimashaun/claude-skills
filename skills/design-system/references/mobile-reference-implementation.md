# Mobile Reference Implementation (Phase 2 — Hotwire Native parity)

Concrete, copy-ready code for the web/Hotwire side of Hotwire Native parity — the part that
lives in the Rails app. The native shells (Kotlin/Swift) live in their own app repos and are
out of scope here; this file gives the **contract** they build to. Everything reuses the same
tokens/primitives/components; mobile only adds shell integration + a little native chrome.
`/design-flow:mobile` scaffolds this.

## 1. Detect the native shell + set body flags

Hotwire Native requests carry a native user-agent; expose it to views and toggle chrome.

```ruby
# app/controllers/concerns/native_app.rb
module NativeApp
  extend ActiveSupport::Concern
  included do
    helper_method :native_app?
    # Hotwire Native sets a "Turbo Native" / "Hotwire Native" token in the UA
    def native_app? = request.user_agent.to_s.match?(/Hotwire Native|Turbo Native/i)
  end
end
```
```erb
<%# layout <body> — hide web-only chrome under .mobile-app; add safe-area + native flags %>
<body class="min-h-svh bg-background text-foreground antialiased <%= 'mobile-app' if native_app? %>"
      data-controller="theme <%= 'native-bridge' if native_app? %>">
  <% if native_app? %><meta name="turbo-native:tabs" content="enabled"><% end %>
  …
</body>
```
```css
/* application.css — web chrome that the native shell replaces */
.mobile-app [data-web-chrome] { display: none; }        /* web top-nav / footer hidden in-app */
.mobile-app .app-main { padding-block: 0; }               /* native provides nav bar + tab bar */
```

## 2. Path configuration (native navigation model)

Serve a JSON path-config the native apps fetch; it maps URL patterns to native presentations
(push vs modal, which get a native tab/title). Treat it as design surface — it defines the
app's navigation.

```ruby
# config/routes.rb
get "/configurations/ios",     to: "configurations#ios"
get "/configurations/android", to: "configurations#android"
```
```jsonc
// app/views/configurations/ios.json.jbuilder → renders this shape
{
  "settings": { "screenshots_enabled": true },
  "rules": [
    { "patterns": ["/new$", "/edit$"], "properties": { "context": "modal" } },
    { "patterns": ["/.*"],             "properties": { "context": "default", "pull_to_refresh_enabled": true } }
  ]
}
```
Keep iOS/Android configs parallel; differences are platform presentation only, never brand.

## 3. Bridge components (progressive enhancement)

A web element declares a bridge; the native side renders the platform-native equivalent
(nav-bar button, action sheet, tab bar). The web control must **work without the bridge** —
the native app only enhances it. JS extends `BridgeComponent` from `@hotwired/hotwire-native-bridge`.

```js
// app/javascript/bridge/button_controller.js — promote a submit/link to a native nav-bar button
import { BridgeComponent } from "@hotwired/hotwire-native-bridge"
export default class extends BridgeComponent {
  static component = "button"
  static targets = ["title"]
  connect() {
    super.connect()
    const title = this.titleTarget.textContent.trim()
    this.send("connect", { title }, () => this.titleTarget.click()) // native taps trigger the web control
  }
}
```
```erb
<%# the button works as a normal web button; native enhances it into a nav-bar action %>
<button data-controller="bridge--button" data-bridge--button-target="title" class="…">Save</button>
```
```js
// app/javascript/bridge/menu_controller.js — a web dropdown -> a native action sheet
import { BridgeComponent } from "@hotwired/hotwire-native-bridge"
export default class extends BridgeComponent {
  static component = "menu"
  static targets = ["item"]
  connect() {
    super.connect()
    const items = this.itemTargets.map((el, i) => ({ title: el.textContent.trim(), index: i }))
    this.send("connect", { items }, (msg) => this.itemTargets[msg.data.index]?.click())
  }
}
```
First bridges to ship: **button** (nav-bar actions), **menu** (action sheet), **tab bar**
(top-level nav via the `turbo-native:tabs` meta + a native tab config). All degrade to the web
component when not in a shell.

## 4. Safe areas + touch (mandatory on native)

```erb
<%# fixed chrome must clear notches / home indicator; tap targets ≥ 44px %>
<header class="sticky top-0 pt-safe px-4 h-14 bg-background border-b border-border">…</header>
<nav class="fixed bottom-0 inset-x-0 pb-safe bg-card border-t border-border">  <%# native tab bar analog %>
  <a class="min-h-touch inline-flex flex-col items-center justify-center …">…</a>
</nav>
```
Wire `min-h-touch` on every interactive control (was defined-but-unused); apply `pt-safe`/
`pb-safe`/`pl-safe`/`pr-safe` to any fixed element.

## 5. Table → summary cards on a phone

The rules are [components.md → Table (CRUD)](components.md#table-crud) (#1391); this is their phone
half. Below 768px each row is a **designed summary card**, not its columns as label/value lines, and
the card opens the record into the modal frame as its [Details card](components.md#details-card) —
a floating card inset from the viewport on a phone, never an edge-to-edge sheet.

```erb
<table class="hidden md:table w-full text-step--1">…</table>   <%# 768px and wider: fits, no scroll %>
<%# The breakpoint sits on its own element: `md:hidden` and `stack` both set `display`. %>
<div class="md:hidden"><ul role="list" class="stack" style="--space: var(--space-xs)">
  <% rows.each do |r| %>
    <li class="relative box bg-card rounded-lg border border-border stack" style="--space: var(--space-2xs)">
      <div class="cluster items-start" style="--justify: space-between">
        <div class="stack gap-0">
          <%= link_to r.name, r.path, data: { turbo_frame: "modal" },
                      class: "font-semibold after:absolute after:inset-0" %>
          <span class="text-step--2 text-muted-foreground tabular-nums"><%= r.reference %></span>
        </div>
        <%= render Ui::BadgeComponent.new(variant: r.status_variant) { r.status } %>
      </div>
      <p class="text-step--1"><%= r.key_facts.join(" · ") %></p>   <%# 2–3 facts; label only an ambiguous one %>
      <div class="cluster" style="--justify: space-between">
        <%= render Ui::ButtonComponent.new(variant: :secondary, size: :sm, class: "relative z-10") { r.primary_action } %>
        <%= lucide_icon "chevron-right", aria: { hidden: true } %>
      </div>
    </li>
  <% end %>
</ul></div>
```

## Notes

- One system: no mobile token fork; the fluid Utopia scale already handles the narrow viewport.
- Bridge components are **enhancement** — never gate core functionality on the native app.
- Native (Kotlin/Swift) shell code lives in the native repos; this file is the web-side contract
  + the JSON path config they consume. Native visual parity comes via Phase 3 token export.
- Exact `@hotwired/hotwire-native-bridge` / path-config field names follow the current Hotwire
  Native docs — verify against them for the version in use; the shapes above are the pattern.

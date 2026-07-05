---
name: hotwire
description: >-
  Deep reference for the Hotwire stack from the official handbooks — Turbo
  (Drive, Frames, Streams, morphing page refreshes), Stimulus (controllers,
  actions, targets, values, outlets), and Hotwire Native (wrap a web app into
  iOS and Android apps with bridge components and path configuration). Use
  this skill whenever the user works with Turbo or Stimulus in any backend
  (Rails, Laravel, Django, Phoenix, plain HTML), mentions turbo-rails,
  stimulus-rails, @hotwired packages, turbo_frame_tag, turbo_stream,
  broadcasts, data-controller/data-action/data-*-target attributes, morphing,
  "SPA-like without a SPA", partial page updates, live updates over
  WebSockets — or wants a mobile app from their web app: Hotwire Native,
  Turbo Native, Strada, bridge components, path configuration, WKWebView/
  webview wrapper apps, or "turn my Rails app into an iOS/Android app". Pair
  with the rails-8 skill for Rails integration specifics.
---

# Hotwire: Turbo, Stimulus & Hotwire Native

Hotwire (HTML Over The Wire) is an approach, not a bundle: send server-rendered
HTML instead of JSON, and keep client-side JavaScript minimal. Three tools,
one escalation ladder — always start at the top:

1. **Turbo Drive** — every app has it for free: links and forms become fetch
   visits, no full page reloads. Zero code.
2. **Morphing page refreshes** — smooth full-page updates that preserve
   scroll/focus; broadcast a "refresh" signal for real-time with almost no
   code.
3. **Turbo Frames** — scope navigation to a page region (inline edit, tabs,
   lazy panels).
4. **Turbo Streams** — surgical CRUD mutations of specific elements, from form
   responses or WebSocket broadcasts.
5. **Stimulus** — the JavaScript sprinkle for what HTML-over-the-wire can't
   express (clipboard, drag, keyboard, third-party widgets).
6. **Hotwire Native** — wrap the finished web app in real iOS/Android shells;
   upgrade individual screens/controls to native only where it pays.

Choose the *lowest* rung that solves the problem; most "we need Streams" cases
are a Frame, and most "we need a Stimulus controller" cases are a Turbo
attribute.

## Version facts (as of this skill's writing)

- **Turbo 8.0.23** (Jan 2026) — npm `@hotwired/turbo`, Rails gem
  `turbo-rails`. Turbo 8 added morphing page refreshes.
- **Stimulus 3.2.2** — npm `@hotwired/stimulus`, Rails gem `stimulus-rails`.
- **Hotwire Native**: iOS **1.2.2**, Android **1.2.5**; web bridge npm
  `@hotwired/hotwire-native-bridge`. Hotwire Native supersedes the old
  "Turbo Native" + "Strada" pair (Strada lives on as *bridge components*).
- All are backend-agnostic; in Rails they ship by default via importmap.
  Verify versions with a web search if the current date is well past early
  2026.

## Non-negotiable ground rules

- **Server responses drive everything.** After a failed form submit, respond
  `422 Unprocessable Entity`; after a successful mutation, redirect with
  `303 See Other`. Turbo silently misbehaves without these statuses.
- **IDs are the contract.** Frames match on `id`; stream actions target `id`
  (or CSS with `targets`). Generate them consistently (`dom_id(record)` in
  Rails).
- **Progressive enhancement.** Everything must work as plain HTML requests
  first; Frames/Streams/Stimulus layer on top. A feature that only works with
  JS enabled is a design smell in Hotwire.
- **State lives in the DOM.** Stimulus values/classes/targets read and write
  the document; no client-side stores.

## Reference files — read before working in an area

| Read | When the task involves |
|---|---|
| `references/turbo.md` | Drive (visits, caching, prefetch, view transitions), morphing page refreshes, Frames (eager/lazy, targeting, breakout), Streams (the 8 actions, broadcasts, custom actions), events, `turbo-rails` helpers |
| `references/stimulus.md` | Controllers, lifecycle, actions (descriptors, options, key filters, parameters), targets, values, CSS classes, outlets, cross-controller communication, patterns and anti-patterns |
| `references/native.md` | Hotwire Native iOS/Android setup, navigation and the routing table, path configuration JSON, bridge components (web + Swift + Kotlin), native screens, web-side detection, turbo-rails native helpers |

A typical feature crosses files: a live-updating list with a native app is
Streams (`turbo.md`) + a controller sprinkle (`stimulus.md`) + path config
(`native.md`).

## Working in a Rails app

The **rails-8** skill owns Rails-side integration (broadcast models, view
helpers in ERB, testing Turbo responses, importmap pins); this skill owns the
Hotwire frameworks themselves. Load both for Rails frontend work. In non-Rails
backends, everything here still applies — install via npm/importmap CDN, and
replace `turbo-rails` broadcast helpers with your framework's WebSocket/SSE
channel emitting `<turbo-stream>` HTML.

## Definition of done for Hotwire work

State which rung of the ladder you used and why. Verify: the flow works with
a hard refresh (no-JS baseline), form errors re-render with 422, mutations
redirect with 303, Frames have matching ids on both ends, broadcasts render
from a model/job context without controller state, and Stimulus controllers
clean up in `disconnect()`. For Native work: the path configuration handles
the new routes and the screen behaves on both platforms or is explicitly
platform-scoped.

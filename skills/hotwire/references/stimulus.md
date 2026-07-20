# Stimulus (v3.2) — Modest JavaScript for the HTML You Have

Stimulus connects small controller classes to HTML via `data-` attributes. It
renders nothing; the server's HTML is the state, controllers add behavior.
Automatically (re)connects as Turbo swaps, streams, and morphs the DOM — this
is why Stimulus, not `DOMContentLoaded` listeners, is the Hotwire way to run
JS.

## Contents
1. Anatomy: identifiers, scopes, registration
2. Lifecycle callbacks
3. Actions
4. Targets
5. Values
6. CSS Classes
7. Outlets (controller-to-controller)
8. Communication patterns
9. A complete idiomatic controller
10. Patterns and anti-patterns

---

## 1. Anatomy: identifiers, scopes, registration

```html
<div data-controller="clipboard">        <!-- element = controller's scope -->
  <input data-clipboard-target="source" value="abc123" readonly>
  <button data-action="clipboard#copy">Copy</button>
</div>
```

- Filename → identifier: `clipboard_controller.js` → `clipboard`;
  `users/list_item_controller.js` → `users--list-item`;
  `date_picker_controller.js` → `date-picker`.
- One element can host several controllers
  (`data-controller="clipboard list-item"`); one controller can be
  instantiated on many elements (each gets its own instance and scope).
- Scope = the element + descendants, **excluding** nested elements carrying
  the same controller (nested scopes don't leak).
- Registration: with Rails importmap, `app/javascript/controllers/index.js`
  eager-loads/registers everything under `controllers/` (run
  `bin/rails stimulus:manifest:update` after adding files if pins are
  stale — the generator `bin/rails g stimulus clipboard` handles it). With a
  bundler: `application.register("clipboard", ClipboardController)`.
- Inside a controller: `this.element`, `this.identifier`,
  `this.application`, `this.dispatch(...)` (§8).

## 2. Lifecycle callbacks

```javascript
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  initialize() {}   // once, when first instantiated
  connect() {}      // every time the element enters the DOM (Turbo visits included)
  disconnect() {}   // every time it leaves — UNDO everything connect did
}
```

The `connect`/`disconnect` pair can fire many times per instance (frames,
streams, morphs, moves). Anything registered in `connect` — intervals,
third-party widgets, global listeners, observers — must be torn down in
`disconnect`, or Turbo navigation leaks them. Per-target lifecycle also
exists: `[name]TargetConnected(el)` / `[name]TargetDisconnected(el)` — fires
even for targets added later by streams (this is the idiomatic MutationObserver
replacement).

## 3. Actions

`data-action="event->controller#method"` wires DOM events to methods:

```html
<input data-action="input->search#filter keydown.esc->search#clear">
<div data-action="click@window->modal#closeIfOutside">
<form data-action="submit->form#validate:prevent">
```

- **Default events** let you omit `event->` for the common case: `click` on
  buttons/links, `submit` on forms, `input` on inputs/textareas, `change` on
  selects — `data-action="search#filter"` on an input means `input`.
- **Globals**: `@window` / `@document` after the event name — with automatic
  cleanup on disconnect (the reason to prefer this over manual
  `addEventListener` in `connect`).
- **Keyboard filters**: `keydown.enter`, `keyup.esc`, modifiers
  `keydown.ctrl+k` / `.meta+`, `.shift+`, `.alt+`; letters/digits and named
  keys (`up down left right home end page_up page_down space tab
  enter esc f1…`) supported.
- **Options** (suffix with `:`): `:prevent` (preventDefault), `:stop`
  (stopPropagation), `:once`, `:capture`, `:passive`, `:self` (only when
  `event.target` is the element itself). Custom options can be registered on
  the application.
- **Method signature**: `filter(event)` — plus **action parameters**: any
  `data-<controller>-<name>-param` on the acting element arrives typed in
  `event.params`:

```html
<button data-action="item#upvote"
        data-item-id-param="123"
        data-item-url-param="/items/123/upvote">…</button>
```

```javascript
upvote({ params: { id, url } }) { … }
```

Multiple space-separated descriptors run in order. Keep methods
action-shaped (verbs handling an event); computation goes in getters/private
methods.

## 4. Targets

Declare important elements; Stimulus maintains typed references:

```javascript
static targets = [ "input", "result" ]

this.inputTarget      // first match (throws if missing)
this.resultTargets    // all matches (array)
this.hasInputTarget   // boolean guard
```

```html
<input data-search-target="input">
<li data-search-target="result">…</li>   <!-- one element can be a target for several controllers -->
```

Use targets instead of `querySelector` — they respect scope, survive DOM
churn, and pair with the `*TargetConnected/Disconnected` callbacks (§2).
Optional UI must guard with `has*Target` before touching.

## 5. Values

Typed state read/written through `data-*-value` attributes — the DOM *is*
the store:

```javascript
static values = {
  url: String,
  refreshInterval: { type: Number, default: 5000 },
  filters: Array,           // Array/Object parse JSON from the attribute
  loading: Boolean
}
```

```html
<div data-controller="loader"
     data-loader-url-value="/messages"
     data-loader-filters-value='["unread"]'>
```

- Read/write: `this.urlValue`, `this.loadingValue = true` (writes back to the
  attribute); `this.hasUrlValue` guards.
- **Change callbacks** fire on connect (with defaults applied) and on every
  mutation — even when *someone else* (another controller, a stream, morph)
  edits the attribute:

```javascript
loadingValueChanged(current, previous) {
  this.element.classList.toggle("opacity-50", current)
}
```

This attribute-driven reactivity is the Stimulus idiom for state: server
renders an attribute → controller reacts; controller sets an attribute →
CSS/other controllers react.

## 6. CSS Classes

Never hardcode class names the HTML should own:

```javascript
static classes = [ "loading" ]
this.element.classList.add(...this.loadingClasses)   // plural handles multiple
// this.hasLoadingClass to guard
```

```html
<form data-controller="search" data-search-loading-class="opacity-50 cursor-wait">
```

Logical names in JS (`loading`), actual utility classes in HTML — controllers
stay reusable across designs.

## 7. Outlets (controller-to-controller)

Typed references to *other controllers' instances*, selected by CSS:

```javascript
// chat_controller.js
static outlets = [ "user-status" ]

markAllRead() {
  this.userStatusOutlets.forEach(status => status.markRead())  // call their public API
}
userStatusOutletConnected(controller, element) { … }
```

```html
<div data-controller="chat"
     data-chat-user-status-outlet=".online-user"></div>
<div class="online-user" data-controller="user-status">…</div>
```

Also available: `this.userStatusOutlet` (first, throws if none),
`hasUserStatusOutlet`, `userStatusOutletElements`. The outlet host element
must actually carry the outlet's controller. Use outlets for deliberate
APIs between sibling widgets; for loose "something happened" signals, prefer
events (§8).

## 8. Communication patterns

- **Child → parent (loose)**: `this.dispatch("copied", { detail: { text } })`
  emits `clipboard:copied` (prefixed with the identifier, bubbling);
  parent listens declaratively:
  `data-action="clipboard:copied->feedback#flash"`. Options:
  `{ target, detail, prefix, bubbles, cancelable }`.
- **Parent → child (strict)**: outlets (§7) calling documented methods.
- **Anyone → anyone**: dispatch on `@window` and listen with
  `data-action="theme:changed@window->chart#redraw"`.
- **Server → controller**: render new attributes/elements (values change
  callbacks + target connected callbacks pick them up) — don't invent a JSON
  side-channel.

## 9. A complete idiomatic controller

```javascript
// app/javascript/controllers/autosave_controller.js
import { Controller } from "@hotwired/stimulus"

// Connects to data-controller="autosave"
export default class extends Controller {
  static targets = [ "status" ]
  static classes = [ "saving" ]
  static values  = { delay: { type: Number, default: 800 } }

  connect() { this.timer = null }

  disconnect() { this.#cancel() }

  // <form data-controller="autosave" data-action="input->autosave#queue">
  queue() {
    this.#cancel()
    this.timer = setTimeout(() => this.#save(), this.delayValue)
  }

  async #save() {
    this.element.classList.add(...this.savingClasses)
    await fetch(this.element.action, {
      method: "POST",
      body: new FormData(this.element),
      headers: { "Accept": "text/vnd.turbo-stream.html" }
    })
    this.element.classList.remove(...this.savingClasses)
    if (this.hasStatusTarget) this.statusTarget.textContent = "Saved"
    this.dispatch("saved")
  }

  #cancel() { if (this.timer) clearTimeout(this.timer) }
}
```

Every convention in one place: values with defaults, guarded optional target,
classes from HTML, cleanup in `disconnect`, event dispatched for parents,
Turbo-friendly fetch.

## 10. Patterns and anti-patterns

Do: keep controllers **small and generic** (a `toggle`, `clipboard`,
`dropdown` reused everywhere beats `user-profile-page`); name by behavior,
not page; treat the HTML as the API (a designer should wire your controller
without reading JS); reach for Turbo first — visibility toggles, confirms,
frame loading need no Stimulus at all; wrap heavy third-party libraries in a
single controller with disciplined `disconnect()` cleanup.

Don't: render HTML strings in controllers (that's the server's job — request
a Turbo Stream instead); hold state in instance fields that must survive
navigation (use values → the DOM); `querySelector` across the document
(targets/outlets); listen for `DOMContentLoaded`/`turbo:load` globally when
`connect()` on the right element does it locally; build one god-controller
per page.

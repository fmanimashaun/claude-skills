# Reference Implementation

Concrete, copy-ready code for the parts the doctrine only specifies in prose: the
**ViewComponent pattern** (replicate it for the whole catalog) and the **four Stimulus
mixins** (the behavioral core every overlay reuses). Tokens and `@utility` layout recipes are
already concrete in [foundations-tokens.md](foundations-tokens.md) and
[layout-primitives.md](layout-primitives.md). `/design-flow:setup` scaffolds these into a
project; use them as the canonical shape.

## ViewComponent pattern (cva, server-side)

Every catalog component follows this shape: a frozen class-map (`BASE` + `VARIANT` + `SIZE` +
`DEFAULTS`), a small `classes` builder, slots for composition. No JS class-merge dep — order
classes so intent wins.

### Button — `app/components/ui/button_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class ButtonComponent < ViewComponent::Base
    BASE = "inline-flex items-center justify-center gap-2 rounded-md text-step-0 font-medium " \
           "transition-colors duration-[180ms] ease-out min-h-touch " \
           "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2 " \
           "disabled:opacity-50 disabled:pointer-events-none"
    VARIANT = {
      primary:     "bg-primary text-primary-foreground hover:bg-primary/90",
      secondary:   "bg-secondary text-secondary-foreground hover:bg-secondary/80",
      destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      outline:     "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
      ghost:       "hover:bg-accent hover:text-accent-foreground",
      link:        "text-primary underline-offset-4 hover:underline",
    }.freeze
    SIZE = { sm: "h-8 px-3", md: "h-9 px-4", lg: "h-10 px-6", icon: "size-9 p-0" }.freeze

    def initialize(variant: :primary, size: :md, type: "button", loading: false, **attrs)
      @variant = variant.to_sym; @size = size.to_sym
      @type = type; @loading = loading; @attrs = attrs
    end

    def call
      tag.button(type: @type, class: classes, aria: { busy: @loading || nil },
                 disabled: @attrs.delete(:disabled), **@attrs) do
        safe_join([(spinner if @loading), content].compact)
      end
    end

    private
    def classes = [BASE, VARIANT.fetch(@variant), SIZE.fetch(@size), @attrs.delete(:class)].compact.join(" ")
    # Loader spinner = the documented fixed-size exception (a spinner, not a Lucide content
    # icon): `size-4` + currentColor is intentional, not a `with-icon`/1em case. See
    # component-implementations.md "Icons (Lucide)".
    def spinner = tag.svg(class: "animate-spin size-4 text-current", aria: { hidden: true }) # Lucide loader-2 path
  end
end
```
Usage: `<%= render(Ui::ButtonComponent.new(variant: :outline, size: :sm)) { "Cancel" } %>`.
**Replicate this exact shape** for Badge, Alert, Input, Modal, etc. (axes per
[components.md](components.md)); only the maps change.

### Card — slot composition — `app/components/ui/card_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class CardComponent < ViewComponent::Base
    renders_one :media
    renders_one :header
    renders_one :footer
    def initialize(**attrs) = @attrs = attrs
    def classes = ["box bg-card text-card-foreground rounded-lg border border-border",
                   @attrs.delete(:class)].compact.join(" ")
  end
end
```
```erb
<%# card_component.html.erb %>
<div class="<%= classes %>" <%= tag.attributes(@attrs) %>>
  <%= media if media? %>
  <div class="stack" style="--space: var(--space-xs)">
    <%= header if header? %>
    <%= content %>
    <%= footer if footer? %>
  </div>
</div>
```
No shadow by default (the 1px border separates); host cards in `grid-auto`.

## Stimulus mixins (the behavioral core)

Four factories in `app/javascript/mixins/`; controllers compose them. This is the hard,
accessibility-critical part — build once, reuse. (Original implementations; skeletons show the
contract — flesh out edge cases per the APG in [interaction-stimulus.md](interaction-stimulus.md).)

### `list_navigation.js` — roving tabindex (menu, tabs, listbox, combobox)

```js
export function listNavigation(controller, { itemsTarget = "item", orientation = "vertical" } = {}) {
  const items = () => controller[`${itemsTarget}Targets`]
  const idx = () => items().findIndex((el) => el.tabIndex === 0)
  const focus = (i) => { const els = items(); if (!els.length) return
    els.forEach((el, n) => el.tabIndex = n === i ? 0 : -1); els[i].focus() }
  const nextKey = orientation === "vertical" ? "ArrowDown" : "ArrowRight"
  const prevKey = orientation === "vertical" ? "ArrowUp" : "ArrowLeft"
  return {
    init() { const els = items(); els.forEach((el, n) => el.tabIndex = n === 0 ? 0 : -1) },
    onKeydown(e) { const els = items(); const cur = Math.max(0, idx())
      if (e.key === nextKey) { e.preventDefault(); focus((cur + 1) % els.length) }
      else if (e.key === prevKey) { e.preventDefault(); focus((cur - 1 + els.length) % els.length) }
      else if (e.key === "Home") { e.preventDefault(); focus(0) }
      else if (e.key === "End") { e.preventDefault(); focus(els.length - 1) } },
    focusFirst() { focus(0) },
  }
}
```

### `focus_trap.js` — trap + restore (modal, drawer only)

```js
const SEL = 'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])'
export function focusTrap(container) {
  let opener = null
  const nodes = () => [...container.querySelectorAll(SEL)].filter((el) => el.offsetParent !== null)
  function onKeydown(e) {
    if (e.key !== "Tab") return
    const els = nodes(); if (!els.length) return
    const first = els[0], last = els[els.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
  return {
    activate() { opener = document.activeElement; document.addEventListener("keydown", onKeydown)
      document.body.style.overflow = "hidden"; (nodes()[0] || container).focus() },
    deactivate() { document.removeEventListener("keydown", onKeydown)
      document.body.style.overflow = ""; opener?.focus() },
  }
}
```

### `dismissable_layer.js` — Esc + outside-click, stacked (dropdown/popover/tooltip/modal/drawer)

```js
const stack = []
export function dismissableLayer(el, onDismiss) {
  function onKey(e) { if (e.key === "Escape" && stack.at(-1) === layer) { e.stopPropagation(); onDismiss() } }
  function onClick(e) { if (stack.at(-1) === layer && !el.contains(e.target)) onDismiss() }
  const layer = {
    open() { stack.push(layer); document.addEventListener("keydown", onKey, true)
      setTimeout(() => document.addEventListener("click", onClick, true)) },
    close() { const i = stack.indexOf(layer); if (i > -1) stack.splice(i, 1)
      document.removeEventListener("keydown", onKey, true); document.removeEventListener("click", onClick, true) },
  }
  return layer
}
```

### `anchored_position.js` — place + collision-flip (dropdown/popover/tooltip/combobox)

```js
export function anchoredPosition(anchor, floating, { placement = "bottom-start", gap = 6 } = {}) {
  return function update() {
    const a = anchor.getBoundingClientRect(), f = floating.getBoundingClientRect()
    let [side, align] = placement.split("-")
    let top = side === "top" ? a.top - f.height - gap : a.bottom + gap
    if (side === "bottom" && top + f.height > innerHeight && a.top - f.height - gap > 0) top = a.top - f.height - gap
    let left = align === "end" ? a.right - f.width : a.left
    left = Math.max(gap, Math.min(left, innerWidth - f.width - gap))
    Object.assign(floating.style, { position: "fixed", top: `${top}px`, left: `${left}px` })
  } // call on open + on scroll/resize; prefer CSS anchor positioning where supported
}
```

### Example controller composing mixins — `dropdown_controller.js`

```js
import { Controller } from "@hotwired/stimulus"
import { listNavigation } from "mixins/list_navigation"
import { dismissableLayer } from "mixins/dismissable_layer"
import { anchoredPosition } from "mixins/anchored_position"
export default class extends Controller {
  static targets = ["menu", "item"]
  connect() { this.nav = listNavigation(this); this.nav.init()
    this.reposition = anchoredPosition(this.element, this.menuTarget) }
  toggle() { this.menuTarget.dataset.state === "open" ? this.close() : this.open() }
  open() { this.menuTarget.dataset.state = "open"; this.element.setAttribute("aria-expanded", "true")
    this.reposition(); this.nav.focusFirst()
    this.layer = dismissableLayer(this.element, () => this.close()); this.layer.open() }
  close() { this.menuTarget.dataset.state = "closed"; this.element.setAttribute("aria-expanded", "false")
    this.layer?.close() }
  keydown(e) { this.nav.onKeydown(e) }
}
```

## Base layout (compose primitives)

```erb
<%# application shell — Layout::Sidebar + header, content in a Center that scrolls %>
<body class="min-h-svh bg-background text-foreground antialiased" data-controller="theme">
  <%= render(Layout::SidebarComponent.new(side_width: "18rem")) do |s| %>
    <% s.with_sidebar { render "shared/nav_links" } %>
    <% s.with_main do %>
      <%= render "shared/header" %>
      <main class="flex-1 overflow-y-auto">
        <div class="center" style="--gutter: var(--space-m)">
          <%= render "shared/flash_messages" %>
          <%= yield %>
        </div>
      </main>
    <% end %>
  <% end %>
  <turbo-frame id="modal"></turbo-frame>   <%# the shared modal frame — all CRUD renders here %>
  <div id="toasts" class="fixed top-4 right-4 z-[100] stack max-w-sm pointer-events-none"></div>
</body>
```

That empty `<turbo-frame id="modal">` is load-bearing: **CRUD is modal-driven and in-page** —
create/edit/delete render into it and update the list via Turbo Stream, never a full-page
form. The full flow (triggers, stream responses, delete confirmation, `modal_controller`) is
in [crud-modal-pattern.md](crud-modal-pattern.md).

Everything here uses **role tokens + primitives only** — no raw colors, no bespoke layout CSS.
The **rest of the catalog** is worked out the same way in
[component-implementations.md](component-implementations.md) (Badge, Alert, form controls,
Modal, Dropdown, Tabs, Toast, Tooltip, Avatar, EmptyState, Sidebar, Switcher). Mirror these
shapes for anything new.

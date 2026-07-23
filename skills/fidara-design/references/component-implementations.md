# Component Implementations (full catalog)

Worked ViewComponent code for the whole catalog, extending the pattern from
[reference-implementation.md](reference-implementation.md) (Button/Card + the four Stimulus
mixins). Every component uses **semantic role tokens** + **layout primitives** only, the shared
`sm/md/lg` size vocabulary, and attribute-driven state (`data-[state]`, `aria-*`). Copy these
shapes; don't invent new ones. Behavioral components reference the mixins/controllers already
defined.

## Icons (Lucide) — the one call-site shape

Every icon below is **Lucide via the `lucide-rails` gem**, sized and colored by the **`with-icon`**
utility, never by a per-call pixel size. The call site is always:

```ruby
# in a component: emit the raw <svg>, no size/color args
def close_icon = helpers.lucide_icon("x")
```
```erb
<%# wrap it (or its button) in `with-icon` — svg becomes 1em + currentColor %>
<span class="with-icon"><%= close_icon %></span>
```

Why no `size:`: `with-icon`'s `& svg { inline-size: 1em; block-size: 1em; fill: currentColor }`
([layout-primitives.md](layout-primitives.md)) wins over the gem's presentational
`width`/`height` attributes — SVG presentation attributes carry **zero CSS specificity**, so the
utility overrides them with no `!important` and no specificity fight. So the `lucide-rails`
initializer should set **stroke-width only** (`"stroke-width" => "1.5"`); do **not** hardcode
`width`/`height` px there — the icon sizes to its text via `with-icon`, per the SKILL
non-negotiable ("Lucide icons, `1em`-sized, `currentColor`"). (Genuinely fixed-size glyphs like
the Button loader-spinner are the documented exception — `animate-spin size-4`, not a content icon.)

## Badge — `app/components/ui/badge_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class BadgeComponent < ViewComponent::Base
    BASE = "inline-flex items-center gap-1 rounded-full font-medium"
    VARIANT = {
      primary:     "bg-primary/10 text-primary",
      secondary:   "bg-secondary text-secondary-foreground",
      success:     "bg-success/10 text-success",
      warning:     "bg-warning/10 text-warning",
      destructive: "bg-destructive/10 text-destructive",
      muted:       "bg-muted text-muted-foreground",
      outline:     "border border-border text-foreground",
    }.freeze
    SIZE = { sm: "px-2 py-0.5 text-step--1", md: "px-2.5 py-0.5 text-step-0" }.freeze
    def initialize(variant: :primary, size: :sm, dot: false, **attrs)
      @variant, @size, @dot, @attrs = variant.to_sym, size.to_sym, dot, attrs
    end
    def call
      tag.span(class: [BASE, VARIANT.fetch(@variant), SIZE.fetch(@size), @attrs.delete(:class)].compact.join(" "), **@attrs) do
        safe_join([(tag.span(class: "size-1.5 rounded-full bg-current") if @dot), content].compact)
      end
    end
  end
end
```

## Alert — `app/components/ui/alert_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class AlertComponent < ViewComponent::Base
    renders_one :title
    INTENT = {
      default: "border-border [&_.alert-icon]:text-foreground",
      info:    "border-info [&_.alert-icon]:text-info",
      success: "border-success [&_.alert-icon]:text-success",
      warning: "border-warning [&_.alert-icon]:text-warning",
      error:   "border-destructive [&_.alert-icon]:text-destructive",
    }.freeze
    def initialize(intent: :default, dismissible: false, **attrs)
      @intent, @dismissible, @attrs = intent.to_sym, dismissible, attrs
    end
    def classes
      ["box bg-card text-card-foreground rounded-lg border border-l-4", INTENT.fetch(@intent),
       @attrs.delete(:class)].compact.join(" ")
    end
    def role = @intent == :error ? "alert" : "status"
    ICON = { default: "info", info: "info", success: "circle-check",
             warning: "triangle-alert", error: "circle-x" }.freeze
    # Lucide via lucide-rails; size/color come from `with-icon` (1em) + currentColor — never a
    # px arg. See "Icons (Lucide)" at the top for why we don't pass size:.
    def icon = helpers.lucide_icon(ICON.fetch(@intent))
    def close_icon = helpers.lucide_icon("x")
  end
end
```
```erb
<%# alert_component.html.erb %>
<div class="<%= classes %>" role="<%= role %>"
     <%= "data-controller=dismiss" if @dismissible %> <%= tag.attributes(@attrs) %>>
  <div class="cluster" style="--space: var(--space-2xs); --align: start">
    <span class="alert-icon with-icon shrink-0"><%= icon %></span>  <%# with-icon → svg 1em, currentColor %>
    <div class="stack" style="--space: var(--space-3xs)">
      <% if title? %><p class="font-medium"><%= title %></p><% end %>
      <div class="text-muted-foreground text-step-0"><%= content %></div>
    </div>
    <% if @dismissible %>
      <button type="button" data-action="dismiss#close" aria-label="Dismiss"
              class="with-icon ml-auto min-h-touch rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"><span class="sr-only">Dismiss</span><%= close_icon %></button>
    <% end %>
  </div>
</div>
```

## Form controls

### Field wrapper — `app/components/ui/field_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class FieldComponent < ViewComponent::Base
    renders_one :control
    def initialize(label:, hint: nil, error: nil, for_id: nil)
      @label, @hint, @error, @for_id = label, hint, error, for_id
    end
    def described_by = @error ? "#{@for_id}-error" : (@hint ? "#{@for_id}-hint" : nil)
  end
end
```
```erb
<%# field_component.html.erb — stack: label -> control -> hint/error %>
<div class="stack" style="--space: var(--space-3xs)">
  <label for="<%= @for_id %>" class="text-step--1 font-medium text-foreground"><%= @label %></label>
  <%= control %>
  <% if @error %><p id="<%= @for_id %>-error" class="text-step--1 text-destructive"><%= @error %></p>
  <% elsif @hint %><p id="<%= @for_id %>-hint" class="text-step--1 text-muted-foreground"><%= @hint %></p><% end %>
</div>
```

### Input recipe (helper) — `app/helpers/ui_helper.rb`

```ruby
module UiHelper
  INPUT_BASE = "block w-full rounded-md border bg-background text-step-0 text-foreground px-3 " \
               "placeholder:text-muted-foreground min-h-touch transition-colors " \
               "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:border-ring " \
               "disabled:opacity-50 disabled:cursor-not-allowed"
  INPUT_SIZE = { sm: "h-8", md: "h-9", lg: "h-10" }.freeze
  def input_classes(state: :default, size: :md)
    border = state == :error ? "border-destructive focus-visible:ring-destructive/30" :
             state == :success ? "border-success" : "border-input"
    [INPUT_BASE, INPUT_SIZE.fetch(size), border].join(" ")
  end
end
```
Textarea: same classes minus the fixed height (`min-h-[…]`). Select: native `<select>` with the
same recipe + a trailing chevron.

### Checkbox / Radio / Switch

```erb
<%# checkbox / radio — wrap in a cluster so control + label align %>
<label class="cluster min-h-touch" style="--space: var(--space-2xs)">
  <%= check_box_tag name, "1", checked, class: "size-4 rounded border-input text-primary focus-visible:ring-ring/30" %>
  <span class="text-step-0"><%= label %></span>
</label>
```
```erb
<%# switch — role=switch, track uses --primary when on; Stimulus toggles aria-checked %>
<button type="button" role="switch" aria-checked="false" data-controller="switch" data-action="switch#toggle"
        class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors min-h-touch
               aria-[checked=true]:bg-primary aria-[checked=false]:bg-input focus-visible:ring-2 focus-visible:ring-ring/30">
  <span class="size-5 rounded-full bg-background translate-x-0.5 transition-transform
               aria-[checked=true]:translate-x-5"></span>
</button>
```

## Modal — `app/components/ui/modal_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class ModalComponent < ViewComponent::Base
    renders_one :title
    renders_one :actions
    SIZE = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl", full: "max-w-full mx-4" }.freeze
    def initialize(size: :md, labelledby: "modal-title")
      @size, @labelledby = size.to_sym, labelledby
    end
    # A modal is a card-class surface → `rounded-lg` (= --radius-lg = 12px via the token),
    # NOT an arbitrary `rounded-[12px]`. Stay in the radius vocabulary (SKILL non-negotiable).
    def panel = ["imposter bg-popover text-popover-foreground rounded-lg shadow-lg w-full", SIZE.fetch(@size)].join(" ")
    # Lucide via lucide-rails; NO px size — `with-icon` sizes it to 1em and `currentColor`
    # inherits (CSS overrides the gem's width/height attrs). See "Icons (Lucide)" at the top.
    def close_icon = helpers.lucide_icon("x")
  end
end
```
```erb
<%# modal_component.html.erb — rendered into <turbo-frame id="modal">; modal controller = trap+dismiss %>
<div data-controller="modal" data-action="keydown.esc->modal#close" class="fixed inset-0 z-50">
  <div class="fixed inset-0 bg-fm-navy/50 backdrop-blur-sm" data-action="click->modal#backdrop"></div>
  <div class="<%= panel %> p-4 sm:p-0" role="dialog" aria-modal="true" aria-labelledby="<%= @labelledby %>"
       data-modal-target="panel">
    <div class="box stack" style="--space: var(--space-s)">
      <div class="cluster" style="--justify: space-between">
        <h2 id="<%= @labelledby %>" class="text-step-1 font-semibold"><%= title %></h2>
        <button type="button" data-action="modal#close" aria-label="Close"
                class="with-icon min-h-touch rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"><span class="sr-only">Close</span><%= close_icon %></button>
      </div>
      <div class="max-h-[70vh] overflow-y-auto"><%= content %></div>
      <% if actions? %><div class="cluster" style="--justify: flex-end"><%= actions %></div><% end %>
    </div>
  </div>
</div>
```

## Dropdown — `app/components/ui/dropdown_component.rb`

```erb
<%# uses the dropdown_controller (list-nav + dismissable + anchored) from reference-implementation %>
<div class="relative inline-block" data-controller="dropdown">
  <button type="button" data-action="dropdown#toggle" aria-haspopup="menu" aria-expanded="false"
          aria-controls="<%= id %>" class="… aria-expanded:bg-accent min-h-touch"><%= trigger %></button>
  <div id="<%= id %>" role="menu" data-dropdown-target="menu"
       class="hidden data-[state=open]:block absolute right-0 z-10 mt-1 w-48 bg-popover text-popover-foreground
              rounded-md border border-border shadow-md divide-y divide-border p-1">
    <% items.each do |it| %>
      <a href="<%= it[:href] %>" role="menuitem" data-dropdown-target="item" tabindex="-1"
         class="block rounded-sm px-3 py-2 text-step-0 hover:bg-accent hover:text-accent-foreground min-h-touch"><%= it[:label] %></a>
    <% end %>
  </div>
</div>
```

## Tabs — `app/components/ui/tabs_component.rb`

```erb
<%# tabs_controller uses list-navigation; panels toggle by data-[state=active] %>
<div data-controller="tabs">
  <div role="tablist" class="cluster border-b border-border" style="--space: 0">
    <% tabs.each_with_index do |t, i| %>
      <button role="tab" data-tabs-target="tab" data-action="tabs#select" tabindex="<%= i.zero? ? 0 : -1 %>"
              aria-selected="<%= i.zero? %>" aria-controls="panel-<%= i %>"
              class="px-4 py-2 text-step-0 border-b-2 border-transparent -mb-px min-h-touch
                     aria-[selected=true]:border-primary aria-[selected=true]:text-primary"><%= t[:label] %></button>
    <% end %>
  </div>
  <% tabs.each_with_index do |t, i| %>
    <div id="panel-<%= i %>" role="tabpanel" data-tabs-target="panel" class="pt-4 <%= 'hidden' unless i.zero? %>"><%= t[:content] %></div>
  <% end %>
</div>
```

## Toast — `app/components/ui/toast_component.rb`

```erb
<%# container in the layout; toasts appended via Turbo Stream. toast_controller auto-dismisses %>
<div id="toasts" class="fixed top-4 right-4 z-[100] stack max-w-sm pointer-events-none" style="--space: var(--space-2xs)"></div>

<%# a toast (turbo_stream.prepend "toasts") — role/status live region + dismiss %>
<div class="box bg-card text-card-foreground rounded-lg border border-l-4 border-<%= intent %> shadow-md pointer-events-auto"
     role="<%= intent == :error ? 'alert' : 'status' %>" aria-live="<%= intent == :error ? 'assertive' : 'polite' %>"
     data-controller="toast" data-toast-timeout-value="5000">
  <div class="cluster" style="--justify: space-between"><span><%= message %></span>
    <button data-action="toast#close" aria-label="Dismiss" class="min-h-touch"><span class="sr-only">Dismiss</span>×</button></div>
</div>
```

## Tooltip — `app/components/ui/tooltip_component.rb`

```erb
<%# anchored-position + dismissable; shows on hover AND focus %>
<span class="relative inline-flex" data-controller="tooltip"
      data-action="mouseenter->tooltip#show focus->tooltip#show mouseleave->tooltip#hide blur->tooltip#hide">
  <%= trigger %>  <%# aria-describedby="tip-#{id}" %>
  <span id="tip-<%= id %>" role="tooltip" data-tooltip-target="content"
        class="hidden data-[state=open]:block absolute z-20 rounded-md bg-popover text-popover-foreground
               text-step--1 px-2 py-1 shadow-md border border-border"><%= content %></span>
</span>
```

## Avatar — `app/components/ui/avatar_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class AvatarComponent < ViewComponent::Base
    SIZE = { sm: "size-8 text-step--1", md: "size-10 text-step-0", lg: "size-12 text-step-1" }.freeze
    def initialize(src: nil, initials: nil, size: :md, **attrs)
      @src, @initials, @size, @attrs = src, initials, size.to_sym, attrs
    end
    def classes = ["rounded-full overflow-hidden inline-flex items-center justify-center", SIZE.fetch(@size), @attrs.delete(:class)].compact.join(" ")
  end
end
```
```erb
<span class="<%= classes %> <%= 'bg-primary/10 text-primary font-semibold' unless @src %>" <%= tag.attributes(@attrs) %>>
  <%= @src ? image_tag(@src, class: "size-full object-cover", alt: "") : @initials %>
</span>
```

## Empty state — `app/components/ui/empty_state_component.rb`

```erb
<%# cover > center > stack %>
<div class="cover" style="--min-height: 40vh">
  <div class="cover-centered center text-center stack" style="--space: var(--space-s)">
    <span class="mx-auto size-16 rounded-full bg-muted inline-flex items-center justify-center text-muted-foreground"><%= icon %></span>
    <div class="stack" style="--space: var(--space-3xs)">
      <p class="text-step-1 font-semibold"><%= title %></p>
      <p class="max-w-md mx-auto text-muted-foreground"><%= description %></p>
    </div>
    <% if action? %><div class="cluster" style="--justify: center"><%= action %></div><% end %>
  </div>
</div>
```

## Layout components (parameterized primitives)

### Sidebar — `app/components/layout/sidebar_component.rb`

```ruby
# frozen_string_literal: true
module Layout
  class SidebarComponent < ViewComponent::Base
    renders_one :sidebar
    renders_one :main
    def initialize(side_width: "18rem", content_min: "50%", space: "var(--space-m)", side: :left)
      @side_width, @content_min, @space, @side = side_width, content_min, space, side
    end
    def style = "display:flex;flex-wrap:wrap;gap:#{@space}"
  end
end
```
```erb
<div style="<%= style %>" data-controller="sidebar">
  <div style="flex-basis:<%= @side_width %>;flex-grow:1" data-sidebar-target="rail"><%= sidebar %></div>
  <div style="flex-basis:0;flex-grow:999;min-inline-size:<%= @content_min %>"><%= main %></div>
</div>
```

### Switcher — `app/components/layout/switcher_component.rb`

```ruby
# frozen_string_literal: true
module Layout
  class SwitcherComponent < ViewComponent::Base
    renders_many :items
    def initialize(threshold: "30rem", space: "var(--space-s)", limit: 4)
      @threshold, @space, @limit = threshold, space, limit
    end
    def container_style = "display:flex;flex-wrap:wrap;gap:#{@space}"
    def item_style = "flex-grow:1;flex-basis:calc((#{@threshold} - 100%) * 999)"
  end
end
```
```erb
<div style="<%= container_style %>">
  <% items.each { |it| %><div style="<%= item_style %>"><%= it %></div><% } %>
</div>
```

---

**Coverage.** With Button + Card (reference-implementation.md) plus the above, the full catalog
from [components.md](components.md) has worked code. Pagination stays the Pagy-based
`shared/_pagination` partial; CRUD tables stay the `shared/_crud_*` partials — both refactored
to role tokens (see components.md). Extend any new component by mirroring these exact shapes:
frozen `BASE`/`VARIANT`/`SIZE` map, role tokens, primitive composition, attribute-driven state,
a11y baked in.

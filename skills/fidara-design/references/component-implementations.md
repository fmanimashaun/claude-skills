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

## Logo / Brand mark — `app/components/ui/logo_component.rb`

The canonical way to render the **Prism mark** + wordmark — so no screen hand-rolls a text
eyebrow. The three facet hues are **fixed brand colors** (brand.md: *never recolor facets*) — the
one place raw brand hex is correct, not role tokens. Swap the inline paths for your exact asset
from `docs/design-system/brand-assets/01-logos/` if the geometry differs.

```ruby
# frozen_string_literal: true
module Ui
  class LogoComponent < ViewComponent::Base
    SIZE = { sm: 20, md: 28, lg: 40 }.freeze          # prism height (px); brand.md min = 20
    # `variant:` is the LOCKUP form (mark vs lockup); `brand_variant:` picks the brand pack's
    # variant (product surface vs parent). No brand NAMES appear here — identity comes from the
    # pack manifest, so a client brand needs no code change.
    def initialize(variant: :lockup, size: :md, brand_variant: nil)
      @variant = variant.to_sym                        # :mark (prism only) | :lockup (+ wordmark)
      @px = (SIZE[size.to_sym] || size.to_i).clamp(20, 200)   # enforce the 20px minimum
      brand = Rails.configuration.x.brand              # generated from brands/<pack>/brand.json
      key = (brand_variant || brand.default_variant).to_s
      v = brand.variants[key] || brand.variants[brand.default_variant.to_s]
      @label = v.fetch(:name)
      @endorsement = v[:endorsement]                   # nil for a parent/standalone brand
    end
    attr_reader :label
    # The endorsement ties a PRODUCT to its parent ("fmworkflows by Fidara"), so it lives on the
    # product variant, not the parent. The old boolean had it backwards — it rendered
    # "Fidara by Fidara" — which a two-value enum made easy to get wrong and hard to notice.
    def endorsement? = @endorsement.present?
  end
end
```
```erb
<%# clear-space (brand.md 1.5×) is a placement rule — keep the lockup uncrowded; the gap here
    sizes to the mark. Wordmark = Bricolage Black on `foreground` (re-points to slate-50 in dark). %>
<span class="with-icon" style="--space: <%= (@px * 0.45).round %>px" role="img" aria-label="<%= label %>">
  <svg width="<%= @px %>" height="<%= @px %>" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 2 L21 7 L12 12 L3 7 Z"  fill="#00D4FF"/> <%# top facet   — cyan     %>
    <path d="M3 7 L12 12 L12 22 L3 17 Z" fill="#0077CC"/> <%# left facet  — cerulean %>
    <path d="M21 7 L12 12 L12 22 L21 17 Z" fill="#00A3FF"/> <%# right facet — electric %>
  </svg>
  <% if @variant == :lockup %>
    <span class="stack" style="--space: 0">
      <span class="font-black uppercase tracking-tight leading-none text-foreground"
            style="font-size: <%= (@px * 0.85).round %>px"><%= label.upcase %></span>
      <%# the endorsement STRING comes from the pack variant — never a literal brand name %>
      <% if endorsement? %><span class="text-step--1 text-muted-foreground"><%= @endorsement %></span><% end %>
    </span>
  <% end %>
</span>
```
Usage: `<%= render(Ui::LogoComponent.new(variant: :mark, size: :sm)) %>` (compact chrome) ·
`<%= render(Ui::LogoComponent.new(brand_variant: "fmworkflows")) %>` (product lockup + its
pack-defined endorsement; omit `brand_variant:` to use the pack's `default_variant`). Dark mode
is automatic (`text-foreground`); for busy/photographic backgrounds use the reversed/white variant
(wrap in a context that sets `--foreground` to white, per brand.md).

**Auth / focused-page recipe** — pair it with the `cover` vertical-centering composition (the named
rule in [layout-primitives.md](layout-primitives.md)):
```erb
<%# a single-focus full-page screen (sign-in, splash): VERTICALLY centered, mark at the top %>
<div class="cover"><div class="cover-centered center" style="--measure: 24rem">
  <div class="box bg-card text-card-foreground rounded-lg border border-border stack">
    <%= render(Ui::LogoComponent.new(variant: :lockup, size: :lg)) %>
    <%= content %>  <%# the form / message %>
  </div>
</div></div>
```

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

### Field anatomy — `config/initializers/simple_form.rb`

**There is no bespoke field-wrapper component, deliberately.** simple_form owns every form and
every form element in this stack, and that includes fields rendered from inside a ViewComponent —
a component that hand-rolls `<label>` + input + error markup *is* a form element built without
simple_form, which is the thing the mandate exists to prevent. Hand-rolled anatomy drifts from the
other hundred fields the moment anyone touches it, and drift is exactly what one wrapper
definition eliminates.

So the design system styles simple_form's **wrappers**, once, in the initializer. Author fields with
`f.input`; the wrapper supplies the `stack`, the label, the control classes and the hint/error
slots, with `aria-describedby` wiring handled by simple_form:

```ruby
# config/initializers/simple_form.rb — the field anatomy of the whole app, defined once
SimpleForm.setup do |config|
  config.wrappers :default, class: "stack", wrapper_html: { style: "--space: var(--space-2xs)" } do |b|
    b.use :html5
    b.use :label, class: "text-step--1 font-medium text-foreground"
    b.use :input, class: "block w-full rounded-md border border-input bg-background " \
                         "text-step-0 text-foreground px-3 h-9 min-h-touch " \
                         "placeholder:text-muted-foreground transition-colors " \
                         "focus-visible:outline-none focus-visible:ring-2 " \
                         "focus-visible:ring-ring/30 focus-visible:border-ring " \
                         "disabled:opacity-50 disabled:cursor-not-allowed",
                  error_class: "border-destructive focus-visible:ring-destructive/30",
                  valid_class: "border-success"
    b.use :hint,  wrap_with: { tag: :p, class: "text-step--1 text-muted-foreground" }
    b.use :error, wrap_with: { tag: :p, class: "text-step--1 text-destructive" }
  end

  config.default_wrapper = :default
  config.button_class = ""            # buttons come from Ui::ButtonComponent, not simple_form
  config.boolean_style = :inline
  config.label_text = ->(label, _required, _explicit) { label }
end
```

**The contract, which is what actually matters.** simple_form's wrapper DSL has more options than
any one example shows, and versions differ in detail, so treat the block above as one correct
spelling rather than the only one. What a fidara wrapper MUST produce, and what a review checks:

1. Order is **label → control → hint → error**, inside a `stack` (spacing from `--space-*`, never
   child margins).
2. Every class is a **role token or a documented recipe** — no literal colours, no stock
   `gray-*`/`blue-*`, no inline `dark:` variants (dark mode is one re-point of the roles).
3. The control carries `min-h-touch` and a visible `focus-visible` ring.
4. The error state is driven by simple_form's own `error_class` / `aria-invalid`, so
   `aria-describedby` wiring comes from the library rather than being hand-maintained.
5. Label text is **always rendered** unless the field explicitly passes `label: false` **and**
   supplies an accessible name.

**Prove it on first install** rather than trusting the snippet — one field, one assertion:

```ruby
# spec/system/form_anatomy_spec.rb — the wrapper is doctrine, so it gets a spec
require "rails_helper"

RSpec.describe "simple_form wrapper", type: :system do
  it "renders label -> control -> error with role tokens and a touch target" do
    visit new_invoice_path
    within("form") do
      expect(page).to have_css("label.text-step--1")
      expect(page).to have_css("input.min-h-touch")
    end
    click_button "Save"                                    # trigger validation
    expect(page).to have_css("p.text-destructive")         # error via the wrapper
    expect(page).to have_css("input[aria-invalid='true']")  # not hand-maintained
  end
end
```

If that spec fails, the wrapper is wrong — not the doctrine. Getting it green once is cheaper than
discovering per-field drift across a hundred forms later.

```erb
<%# every field, everywhere — including inside a ViewComponent's template %>
<%= f.input :email, hint: "We'll never share it." %>
<%= f.input :status, collection: Invoice.statuses.keys %>
<%= f.association :category %>
```

**A ViewComponent that renders fields takes the form builder in and uses it**, rather than
re-implementing the anatomy:

```ruby
module Ui
  class AddressFieldsComponent < ViewComponent::Base
    def initialize(form:) = @form = form
    attr_reader :form
  end
end
```
```erb
<%# address_fields_component.html.erb — composition, not re-implementation %>
<div class="stack">
  <%= form.input :line1 %>
  <%= form.input :city %>
  <%= form.input :postcode %>
</div>
```

Sizes (`sm h-8 · md h-9 · lg h-10`, matching Button) come from additional named wrappers
(`config.wrappers :compact`) selected per form with `f.input :x, wrapper: :compact` — a second
wrapper definition, never a per-field class override, so the set of field shapes stays enumerable.

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
    renders_one :actions   # the BODY is the block content, not a slot — same shape as Alert
    SIZE = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl", full: "max-w-full mx-4" }.freeze
    # A DRAWER IS THIS COMPONENT AT AN EDGE (decision, no upstream): one dialog implementation, one
    # focus trap, one Esc handler. `placement:` is the whole difference, so a drawer never needs a
    # second component -- and never needs a caller passing raw positioning classes, which is what an
    # invented `class:` argument would have meant. NOTE: only the OVERLAY drawer is this component.
    # A persistent push sidebar is not a dialog at all and must not come through here.
    PLACEMENT = {
      center: "imposter",
      left:   "fixed inset-y-0 left-0 h-full rounded-none",
      right:  "fixed inset-y-0 right-0 h-full rounded-none",
      bottom: "fixed inset-x-0 bottom-0 w-full rounded-t-lg rounded-b-none",
    }.freeze
    def initialize(size: :md, labelledby: "modal-title", placement: :center)
      @size, @labelledby, @placement = size.to_sym, labelledby, placement.to_sym
    end
    # A modal is a card-class surface → `rounded-lg` (= --radius-lg = 12px via the token),
    # NOT an arbitrary `rounded-[12px]`. Stay in the radius vocabulary (SKILL non-negotiable).
    def panel = [PLACEMENT.fetch(@placement), "bg-popover text-popover-foreground rounded-lg shadow-lg w-full", SIZE.fetch(@size)].join(" ")
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

The class was missing from this section for as long as it has existed, so its call sites — the
`items:` keyword and the `trigger` slot — were **unverifiable**: `lint_self_consistency.py` skips a
component it cannot find a declaration for, by design (#168). Declared now, so both are checked (#238).

```ruby
# frozen_string_literal: true
module Ui
  class DropdownComponent < ViewComponent::Base
    renders_one :trigger

    # `items` is an Array of `{label:, href:}` — a plain collection rather than a slot, because a
    # menu's items are data, and `role="menuitem"` must be on the anchor itself.
    def initialize(items:, id: nil)
      @items = items
      @id = id || "dropdown-#{SecureRandom.hex(4)}"
    end

    attr_reader :items, :id
  end
end
```
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

## Combobox — `app/components/ui/combobox_component.rb`

APG-verified contract; read
[interaction-stimulus.md](interaction-stimulus.md#combobox--the-two-corrections-that-matter-and-a-version-trap-229)
for what is **required** versus ours. Two things this component gets right that are commonly got
wrong: `aria-selected` tracks the **active** option (selection follows focus), and `aria-controls` is
**required**, not optional.

```ruby
# frozen_string_literal: true
module Ui
  class ComboboxComponent < ViewComponent::Base
    renders_many :options, "OptionComponent"

    # `autocomplete:` -> aria-autocomplete. `:none` omits the attribute (the default per ARIA).
    # `select_only:` puts the role on a div instead of an input: there is no text to complete, so
    # it also forbids aria-autocomplete entirely.
    AUTOCOMPLETE = { none: nil, list: "list", both: "both" }.freeze

    def initialize(id:, name:, label:, autocomplete: :list, select_only: false,
                   invalid: false, popup: :listbox)
      @id, @name, @label = id, name, label
      @autocomplete, @select_only, @invalid, @popup = autocomplete.to_sym, select_only, invalid, popup.to_sym
    end

    def popup_id = "#{@id}-popup"
    def error_id = "#{@id}-error"

    # listbox is the IMPLICIT default for role=combobox, so declaring aria-haspopup for it is noise.
    # Anything else MUST declare it.
    def haspopup = @popup == :listbox ? nil : @popup.to_s

    def autocomplete_value = @select_only ? nil : AUTOCOMPLETE.fetch(@autocomplete)

    def described_by = @invalid ? error_id : nil

    def input_classes
      "w-full rounded-md border border-input bg-background px-3 min-h-touch " \
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 " \
        "aria-[invalid=true]:border-destructive"
    end

    def open_icon = helpers.lucide_icon("chevrons-up-down")

    # Each option carries its own id so aria-activedescendant has something to point at, and
    # aria-selected starts false — it tracks the ACTIVE option, set by the controller as focus moves.
    class OptionComponent < ViewComponent::Base
      def initialize(id:, value:)
        @id, @value = id, value
      end

      def call
        tag.li(content, id: @id, role: "option", class: "px-3 py-2 cursor-default " \
               "data-[active=true]:bg-accent", aria: { selected: false },
               data: { value: @value, active: false })
      end
    end
  end
end
```
```erb
<%# combobox_component.html.erb — role=combobox goes on the INPUT, never a wrapper div. %>
<%# A wrapper with aria-owns is the superseded ARIA 1.1 model and no longer conforms. %>
<div data-controller="combobox" class="stack" style="--space: var(--space-3xs)">
  <label for="<%= @id %>" class="text-sm font-medium"><%= @label %></label>

  <div class="relative">
    <%= tag.input id: @id, name: @name, type: "text", class: input_classes,
                  role: "combobox", autocomplete: "off",
                  aria: { expanded: false, controls: popup_id, haspopup: haspopup,
                          autocomplete: autocomplete_value, invalid: @invalid,
                          describedby: described_by },
                  data: { combobox_target: "input", action: "input->combobox#filter " \
                          "keydown->combobox#key click->combobox#open" } %>

    <%# Optional Open button: tabindex=-1 and OUT of the tab order — the input already reaches
        the popup, so a focusable second control just adds a stop that does nothing new. %>
    <button type="button" tabindex="-1" aria-label="Show options"
            class="with-icon absolute inset-y-0 right-0 px-2"
            data-action="combobox#toggle"><%= open_icon %></button>
  </div>

  <%# hidden AND aria-expanded=false: the ARIA state alone leaves options in the a11y tree. %>
  <ul id="<%= popup_id %>" role="<%= @popup %>" hidden
      data-combobox-target="popup"
      class="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border
             bg-popover text-popover-foreground shadow-md divide-y divide-border">
    <% options.each do |option| %><%= option %><% end %>
  </ul>

  <% if @invalid %>
    <p id="<%= error_id %>" class="text-sm text-destructive"><%= content %></p>
  <% end %>

  <%# OUR convention, not APG's: the pattern never prescribes a live-region count. %>
  <p class="sr-only" role="status" data-combobox-target="status"></p>
</div>
```

```js
// app/javascript/controllers/combobox_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["input", "popup", "status"]

  // Required: ArrowDown into the popup, ArrowUp/ArrowDown within it, Enter accepts, Esc dismisses.
  // Right/Left are deliberately NOT handled — they must move the text cursor. Space is not an
  // activation key: in an editable combobox it types a space.
  key(event) {
    switch (event.key) {
      case "ArrowDown": event.preventDefault(); this.#move(1); break
      case "ArrowUp":   event.preventDefault(); this.#move(-1); break
      case "Enter":     if (this.#active) { event.preventDefault(); this.#accept() } break
      case "Escape":    this.close(); break
    }
  }

  open()  { this.popupTarget.hidden = false; this.inputTarget.setAttribute("aria-expanded", "true") }
  close() { this.popupTarget.hidden = true;  this.inputTarget.setAttribute("aria-expanded", "false")
            this.inputTarget.removeAttribute("aria-activedescendant") }
  toggle() { this.popupTarget.hidden ? this.open() : this.close() }

  filter() {
    const q = this.inputTarget.value.toLowerCase()
    const shown = this.#options.filter((o) => {
      const hit = o.textContent.toLowerCase().includes(q)
      o.hidden = !hit
      return hit
    })
    this.open()
    // Our convention, announced politely rather than asserted as an APG requirement.
    this.statusTarget.textContent = `${shown.length} result${shown.length === 1 ? "" : "s"} available`
  }

  get #options() { return Array.from(this.popupTarget.querySelectorAll('[role="option"]')) }
  get #active()  { return this.popupTarget.querySelector('[data-active="true"]') }

  // aria-selected tracks the ACTIVE option, because selection follows focus in a combobox. Focus
  // itself never leaves the input — that is what aria-activedescendant is for, and it is why typing
  // keeps filtering.
  #move(delta) {
    const visible = this.#options.filter((o) => !o.hidden)
    if (!visible.length) return
    this.open()
    const index = visible.indexOf(this.#active)
    const next = visible[Math.max(0, Math.min(visible.length - 1, index + delta))] || visible[0]
    visible.forEach((o) => {
      const on = o === next
      o.dataset.active = String(on)
      o.setAttribute("aria-selected", String(on))
    })
    this.inputTarget.setAttribute("aria-activedescendant", next.id)
    next.scrollIntoView({ block: "nearest" })
  }

  #accept() {
    this.inputTarget.value = this.#active.dataset.value ?? this.#active.textContent.trim()
    this.close()
    this.inputTarget.focus()
  }
}
```

Call site — the options are a slot, so each carries its own `id` for `aria-activedescendant` to
point at:

```erb
<%= render Ui::ComboboxComponent.new(id: "assignee", name: "task[assignee]",
                                     label: "Assignee", autocomplete: :list) do |c| %>
  <% users.each do |user| %>
    <% c.with_option(id: "assignee-opt-#{user.id}", value: user.id) { user.name } %>
  <% end %>
<% end %>
```

**Select-only** (no text entry) is the same controller with the role on a `div`, no
`aria-autocomplete`, and printable characters jumping to matching options rather than filtering —
that is the one variant where `Space` legitimately opens and accepts, because there is no text field
for it to type into.

**Command palette** is this component inside the documented `Modal`: `Ui::Modal` for the shell,
`Ui::Combobox` for the filter and results. Keep `aria-activedescendant` — moving DOM focus into the
results would stop typing from filtering.

## Disclosure / Accordion — `app/components/ui/disclosure_component.rb`

The most frequent interactive pattern after plain links (732 instances in a 72-page corpus). Read
[interaction-stimulus.md](interaction-stimulus.md#disclosure--the-full-contract-142) for what is
APG-**required** here versus what is our own choice — the distinction is load-bearing, and the issue
that requested this component got it wrong.

```ruby
# frozen_string_literal: true
module Ui
  class DisclosureComponent < ViewComponent::Base
    renders_one :trigger_content
    renders_one :panel_content

    # `heading:` wraps the trigger button in a heading element. REQUIRED by APG for an accordion;
    # `nil` for a standalone collapse, which has no heading semantics to declare.
    #
    # `region:` adds role=region + aria-labelledby to the panel. Default nil = let the parent decide,
    # because APG discourages it past ~6 simultaneously-expandable panels (landmark proliferation) —
    # so this cannot be hardcoded true without being wrong for large accordions.
    def initialize(id:, open: false, heading: nil, region: nil, group: nil)
      @id, @open, @heading, @region, @group = id, open, heading, region, group
    end

    def panel_id = "#{@id}-panel"
    def trigger_id = "#{@id}-trigger"
    def state = @open ? "open" : "closed"

    def trigger_classes
      "flex w-full items-center justify-between gap-s py-4 text-left font-medium min-h-touch " \
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
    end

    # No px size on the icon — `with-icon` sizes it to 1em and currentColor inherits.
    def chevron = helpers.lucide_icon("chevron-down")
  end
end
```
```erb
<%# disclosure_component.html.erb %>
<%# The heading contains ONLY the button (APG). A badge or overflow menu goes outside it. %>
<div data-controller="disclosure" <%= "data-disclosure-group-value=#{@group}" if @group %>
     data-state="<%= state %>">
  <% if @heading %>
    <%= content_tag @heading, class: "m-0" do %>
      <button type="button" id="<%= trigger_id %>" class="<%= trigger_classes %> with-icon"
              aria-expanded="<%= @open %>" aria-controls="<%= panel_id %>"
              data-disclosure-target="trigger" data-action="disclosure#toggle">
        <%= trigger_content %>
        <span class="transition-transform data-[state=open]:rotate-180" data-state="<%= state %>"><%= chevron %></span>
      </button>
    <% end %>
  <% else %>
    <button type="button" id="<%= trigger_id %>" class="<%= trigger_classes %> with-icon"
            aria-expanded="<%= @open %>" aria-controls="<%= panel_id %>"
            data-disclosure-target="trigger" data-action="disclosure#toggle">
      <%= trigger_content %>
      <span class="transition-transform data-[state=open]:rotate-180" data-state="<%= state %>"><%= chevron %></span>
    </button>
  <% end %>

  <%# `hidden` AND aria-expanded — see the contract: aria-expanded alone leaves this in the %>
  <%# accessibility tree and the tab order. %>
  <div id="<%= panel_id %>" data-disclosure-target="panel" <%= "hidden" unless @open %>
       <%= "role=region aria-labelledby=#{trigger_id}".html_safe if @region %>
       class="border-t border-border">
    <div class="stack py-4" style="--space: var(--space-s)"><%= panel_content %></div>
  </div>
</div>
```

```js
// app/javascript/controllers/disclosure_controller.js
import { Controller } from "@hotwired/stimulus"

// Enter and Space both activate — a native <button> gives us that for free, which is why the
// trigger is a real button rather than a div with a keydown handler.
export default class extends Controller {
  static targets = ["trigger", "panel"]
  static values = { group: String }

  toggle() { this.expanded ? this.close() : this.open() }

  get expanded() { return this.triggerTarget.getAttribute("aria-expanded") === "true" }

  open() {
    // Single-open COLLAPSIBLE: siblings close, but all may be closed. We do not ship APG's
    // always-one-expanded variant, so nothing here sets aria-disabled.
    if (this.hasGroupValue) {
      this.#siblings().forEach((el) => el !== this.element && el.disclosure?.close())
    }
    this.#setState(true)
  }

  close() { this.#setState(false) }

  // State is set DIRECTLY, never gated on an animation event. If it waited for `animationend`,
  // prefers-reduced-motion (which suppresses the animation) would mean the event never fires and
  // the control would silently stop working.
  #setState(open) {
    this.triggerTarget.setAttribute("aria-expanded", String(open))
    this.panelTarget.hidden = !open              // hidden, not just ARIA state
    this.element.dataset.state = open ? "open" : "closed"
    this.element.querySelectorAll("[data-state]").forEach((el) => {
      el.dataset.state = open ? "open" : "closed"
    })
  }

  #siblings() {
    return Array.from(
      document.querySelectorAll(`[data-controller~="disclosure"][data-disclosure-group-value="${this.groupValue}"]`)
    )
  }

  // Deep link: open before the browser tries to scroll, or it scrolls to a hidden element.
  connect() {
    this.element.disclosure = this
    const hash = window.location.hash.slice(1)
    if (hash && (hash === this.panelTarget.id || this.panelTarget.querySelector(`#${CSS.escape(hash)}`))) {
      this.open()
    }
  }
}
```

```css
/* Height transition, suppressed under reduced motion. The panel is still revealed either way,
   because `hidden` is toggled in JS rather than at the end of an animation. */
@media (prefers-reduced-motion: no-preference) {
  [data-controller~="disclosure"] > [data-disclosure-target="panel"] {
    interpolate-size: allow-keywords;
    transition: height var(--duration-fast) var(--ease-out);
  }
}
```

**Accordion** is many of these sharing a `group:` and each given a `heading:`:

```erb
<div class="divide-y divide-border">
  <% faqs.each_with_index do |faq, i| %>
    <%= render Ui::DisclosureComponent.new(id: "faq-#{i}", group: "faq", heading: :h3,
                                           region: faqs.size <= 6, open: i.zero?) do |d| %>
      <% d.with_trigger_content { faq.question } %>
      <% d.with_panel_content { faq.answer } %>
    <% end %>
  <% end %>
</div>
```

`region:` is computed, not hardcoded — past ~6 simultaneously-expandable panels APG warns the
landmark noise outweighs the structure.

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
<%# Container in the layout — PERSISTENT and EMPTY, and it is the ONE place bare aria-live is right. %>
<%# aria-atomic defaults to false there, which is what you want for insertions: atomic=true would %>
<%# re-announce every toast already on screen. It matches page-anatomies.md's layout snippet; the two %>
<%# used to disagree about whether this element carried aria-live at all. %>
<div id="toasts" aria-live="polite" class="fixed top-4 right-4 z-[100] stack max-w-sm pointer-events-none" style="--space: var(--space-2xs)"></div>

<%# A toast (turbo_stream.prepend "toasts") — the ROLE carries the severity, and nothing beside it: %>
<%# `status` already implies aria-live="polite", `alert` already implies aria-live="assertive", so %>
<%# writing aria-live here restates the role at best and contradicts it at worst. %>
<div class="box bg-card text-card-foreground rounded-lg border border-l-4 border-<%= intent %> shadow-md pointer-events-auto"
     role="<%= intent == :error ? 'alert' : 'status' %>"
     data-controller="toast" data-toast-timeout-value="5000">
  <div class="cluster" style="--justify: space-between"><span><%= message %></span>
    <button data-action="toast#close" aria-label="Dismiss" class="min-h-touch"><span class="sr-only">Dismiss</span>×</button></div>
</div>
```

## Drawer, Carousel and Lightbox — markup, because the roles are what gets wrong

No new ViewComponent classes: the drawer **is** `Ui::Modal` positioned to an edge, and the lightbox is
that Modal containing the carousel markup below. What needs writing down is the role wiring.

```erb
<%# ---- DRAWER, overlay: the documented Modal, edge-positioned. Full dialog contract. ---- %>
<%= render Ui::ModalComponent.new(size: :sm, placement: :right) do |m| %>
  <% m.with_title { "Filters" } %>
  <%= render "products/filter_form" %><%# the body is BLOCK CONTENT — there is no `body` slot %>
<% end %>

<%# ---- DRAWER, persistent: NOT a dialog. No role="dialog", no aria-modal, no focus trap. ---- %>
<%# The `sidebar` controller collapses it; it never traps focus, never steals initial focus. %>
<nav data-controller="sidebar" aria-label="Main" class="hidden lg:block w-64 shrink-0">
  <%= render Layout::SidebarComponent.new %>
</nav>

<%# Responsive: render BOTH and let the breakpoint choose. Do not toggle aria-modal by media query — %>
<%# that changes which contract applies to the same element while the user is inside it. %>

<%# ---- CAROUSEL, Basic variant. region OR group on the container; group + slide on each slide. ---- %>
<%# No auto-rotation here, so NO play/pause button and no stop-on-hover/focus is required. %>
<section role="region" aria-roledescription="carousel" aria-label="Featured products"
         data-controller="carousel" class="relative">
  <div class="cluster" style="--justify: space-between">
    <button data-action="carousel#prev" aria-label="Previous slide" class="min-h-touch">
      <span class="with-icon"><%= lucide_icon("chevron-left") %></span>
    </button>
    <button data-action="carousel#next" aria-label="Next slide" class="min-h-touch">
      <span class="with-icon"><%= lucide_icon("chevron-right") %></span>
    </button>
  </div>

  <%# Inactive slides leave the a11y tree via `hidden` — NOT aria-hidden, and never by translating %>
  <%# them off-screen, which is the failure APG actually warns about. %>
  <% products.each_with_index do |product, i| %>
    <div role="group" aria-roledescription="slide"
         aria-label="<%= i + 1 %> of <%= products.size %>"
         data-carousel-target="slide" <%= "hidden" unless i.zero? %>>
      <%= render Ui::CardComponent.new do %><%= product.name %><% end %>
    </div>
  <% end %>
</section>

<%# Tabbed variant differs in ONE way that is easy to miss: a slide becomes role="tabpanel" and %>
<%# DROPS aria-roledescription entirely. Do not carry "slide" over. %>
<div role="tabpanel" aria-label="1 of 3" data-carousel-target="slide">…</div>

<%# ---- LIGHTBOX: the Modal containing the carousel. Thumbnails are BUTTONS, not links. ---- %>
<%# Closing returns focus to the thumbnail that was clicked — the invoking element, not the grid. %>
<%# The dialog's name is the image's own caption, so it names the picture rather than repeating %>
<%# "Image viewer" on every open. Using a dialog at all is OUR decision (it keeps scroll position), %>
<%# not a spec requirement — no APG pattern covers lightboxes. %>
<div class="grid-auto">
  <% images.each do |image| %>
    <button data-action="lightbox#open" data-lightbox-id-param="<%= image.id %>" class="frame">
      <%= image_tag image.thumb_url, alt: image.caption %>
    </button>
  <% end %>
</div>
```

## Progress — `app/components/ui/progress_component.rb`

`role="progressbar"` is *Children Presentational*, so nothing inside the bar is exposed — the name has
to come from the author. That is the whole reason this is a component and not a `div`: it is the one
place the name/`aria-valuetext` wiring can be got right once.

```ruby
# frozen_string_literal: true
module Ui
  class ProgressComponent < ViewComponent::Base
    SIZE = { sm: "h-1", md: "h-2", lg: "h-3" }.freeze

    # value: nil == INDETERMINATE. `aria-valuenow` is then OMITTED, never 0 or -1 -- 0 reads as
    # "no progress made", which is a different claim from "unknown".
    # label: is REQUIRED. The role's name comes From: author only, and the fill div's text is not
    # exposed, so without it the bar is anonymous. Raise rather than ship a nameless progressbar.
    def initialize(label:, value: nil, min: 0, max: 100, value_text: nil, size: :md, **attrs)
      raise ArgumentError, "progressbar needs an author-supplied label" if label.blank?
      @label, @value, @min, @max = label, value, min, max
      @value_text, @size, @attrs = value_text, size.to_sym, attrs
    end

    def call
      tag.div(**aria, **@attrs, class: track_classes) do
        tag.div(class: "h-full rounded-full bg-primary transition-[width] duration-300",
                style: "width: #{fill_percent}%")
      end
    end

    private

    def aria
      base = { role: "progressbar", "aria-label": @label }
      # min/max default to 0/100 in the spec -- emit them only when they differ, so the markup does
      # not assert values it is merely restating.
      base["aria-valuemin"] = @min unless @min.zero?
      base["aria-valuemax"] = @max unless @max == 100
      base["aria-valuenow"] = @value if determinate?          # OMITTED when indeterminate
      base["aria-valuetext"] = @value_text if @value_text     # e.g. "Step 2 of 5"
      base
    end

    def determinate? = !@value.nil?

    def track_classes
      ["w-full overflow-hidden rounded-full bg-muted", SIZE.fetch(@size),
       ("animate-pulse" unless determinate?), @attrs.delete(:class)].compact.join(" ")
    end

    def fill_percent
      return 100 unless determinate?   # indeterminate: a full pulsing track, no value claimed
      span = (@max - @min).to_f
      span.zero? ? 0 : (((@value - @min) / span) * 100).clamp(0, 100).round(2)
    end
  end
end
```

## Skeleton and Spinner — recipes, not components

Neither has state, slots, or behavior, so a ViewComponent would wrap a `div` in ceremony. They are
recipes, like the Divider. **Which one to reach for is decided by one question: is the content's size
known?** Known → skeleton (it reserves the space, so nothing shifts). Unknown → spinner.

```erb
<%# SKELETON -- shapes are aria-hidden; ONE status message for the whole block. %>
<%# aria-busy is correct but advisory (AT *may* wait) and poorly supported, so aria-hidden on the %>
<%# shapes is what actually stops forty rectangles being announced. %>
<div id="invoices" aria-busy="true">
  <p role="status" class="sr-only">Loading invoices…</p>
  <div aria-hidden="true" class="stack">
    <% 5.times do %>
      <div class="flex items-center gap-4">
        <div class="size-10 shrink-0 animate-pulse rounded-full bg-muted"></div>
        <div class="w-full stack" style="--stack-space: 0.5rem">
          <div class="h-4 w-1/3 animate-pulse rounded-md bg-muted"></div>
          <div class="h-3 w-2/3 animate-pulse rounded-md bg-muted"></div>
        </div>
      </div>
    <% end %>
  </div>
</div>

<%# The natural home for it: a lazy Turbo frame's placeholder content. %>
<%= turbo_frame_tag "invoices", src: invoices_path, loading: :lazy do %>
  <%= render "invoices/skeleton" %>
<% end %>

<%# SPINNER -- the icon is DECORATION (aria-hidden), the words live in the status region. %>
<%# Never aria-label the spinning icon: that names the graphic, not the state. %>
<%# The WRAPPER carries animate-spin and aria-hidden, per the one call-site shape above: %>
<%# lucide_icon takes no size:/class:, `with-icon` makes the svg 1em/currentColor, and here that %>
<%# is what you want -- the spinner sizes to the words beside it. Add `size-4` to the wrapper %>
<%# (never to lucide_icon) only for a standalone spinner with no adjacent text to size against. %>
<div role="status" class="flex items-center gap-2 text-muted-foreground">
  <span class="with-icon animate-spin" aria-hidden="true"><%= lucide_icon("loader-circle") %></span>
  <span>Processing payment…</span>
</div>

<%# NOT this: role="progressbar" with no aria-valuenow claims a value it cannot supply. If the %>
<%# proportion IS known, use Ui::ProgressComponent; if it is not, use the status region above. %>
```

Suppress both animations under reduced motion. Worth doing — but the SC is **2.2.2 Pause/Stop/Hide**
(conditional: over five seconds *and* parallel content), not 2.3.3, which covers motion from
*interaction*. Do not cite 2.3.3 for a loading animation.

```css
@media (prefers-reduced-motion: reduce) {
  .animate-pulse, .animate-spin { animation: none; }
}
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

## Call sites — the invocation for every documented component

A class definition shows what a component *accepts*; it does not show how to *call* it, and inferring
the invocation is exactly how `FieldComponent.new(form:, name:)` and `field_classes` **shipped and
raised** in a user's project (#168, #182). So every component above has its invocation here, in one
place a reader can scan.

These are checked mechanically: `lint_self_consistency.py` verifies each call site's initializer
keywords and slot setters against that component's own declaration, so a signature change that misses
this section fails the gate rather than misleading someone (#238).

Note the slot-setter names — `renders_many :items` gives the **singular** `with_item`.

```erb
<%# Badge — variant/size are vocabularies, not free strings %>
<%= render Ui::BadgeComponent.new(variant: :success, size: :sm, dot: true) do %>Active<% end %>

<%# Alert — one title slot; body is the block content %>
<%= render Ui::AlertComponent.new(intent: :warning, dismissible: true) do |a| %>
  <% a.with_title { "Payment method expires soon" } %>
  Update it before the next billing run.
<% end %>

<%# Heading block — four optional slots, all `renders_one` %>
<%= render Ui::HeadingComponent.new(title: "Invoices", level: 1, id: "page-title") do |h| %>
  <% h.with_eyebrow { "Billing" } %>
  <% h.with_description { "Every invoice raised against this account." } %>
  <% h.with_actions { render Ui::ButtonComponent.new(variant: :primary) { "New invoice" } } %>
  <% h.with_meta { "Updated #{l invoice.updated_at, format: :short}" } %>
<% end %>

<%# Progress — label: is REQUIRED (name From: author). value: nil == indeterminate %>
<%= render Ui::ProgressComponent.new(label: "Import progress", value: 40, value_text: "Step 2 of 5") %>
<%= render Ui::ProgressComponent.new(label: "Uploading", size: :sm) %><%# no value: indeterminate %>

<%# Media object — media / body / trailing %>
<%= render Ui::MediaObjectComponent.new(size: :md) do |m| %>
  <% m.with_media { render Ui::AvatarComponent.new(src: user.avatar_url, initials: "FA", size: :md) } %>
  <% m.with_body { tag.p(user.name, class: "font-medium") } %>
  <% m.with_trailing { render Ui::BadgeComponent.new(variant: :secondary) { user.role } } %>
<% end %>

<%# Avatar standalone — `initials` is the fallback when src is nil, never decoration %>
<%= render Ui::AvatarComponent.new(src: nil, initials: "FA", size: :lg) %>

<%# Card — no initializer args; three optional slots %>
<%= render Ui::CardComponent.new do |c| %>
  <% c.with_media { image_tag invoice.preview_url, alt: "" } %>
  <% c.with_header { "Invoice #{invoice.number}" } %>
  <% c.with_footer { link_to "Download", invoice_path(invoice) } %>
  <%= invoice.summary %>
<% end %>

<%# Description list — `values` is an Array so one label can carry several <dd>s %>
<%= render Ui::DescriptionListComponent.new(layout: :inline) do |l| %>
  <% l.with_row(label: "Billing email", value: account.billing_email) %>
  <% l.with_row(label: "Tax IDs", values: account.tax_ids, mono: true) %>
<% end %>

<%# Button group — `kind:` picks the ELEMENT (group vs radiogroup), not a style %>
<%= render Ui::ButtonGroupComponent.new(label: "Invoice view", kind: :select) do |g| %>
  <% g.with_button { render Ui::ButtonComponent.new(variant: :ghost) { "List" } } %>
  <% g.with_button { render Ui::ButtonComponent.new(variant: :ghost) { "Board" } } %>
<% end %>

<%# Breadcrumbs — items are passed in, not slotted %>
<%= render Ui::BreadcrumbsComponent.new(
      items: [["Home", root_path], ["Invoices", invoices_path], [invoice.number, nil]],
      collapse_after: 3) %>

<%# Switcher — a layout primitive: one-dimension flip at a threshold %>
<%= render Ui::SwitcherComponent.new(threshold: "30rem", space: :s) do |s| %>
  <% s.with_item { render Ui::CardComponent.new { "Left" } } %>
  <% s.with_item { render Ui::CardComponent.new { "Right" } } %>
<% end %>

<%# Address fields — takes the form builder, so it composes inside simple_form %>
<%= simple_form_for @account do |f| %>
  <%= render Ui::AddressFieldsComponent.new(form: f) %>
<% end %>

<%# Stat tile — `spark` takes a bare inline <svg>, not a component: data-viz.md declares the slot
    as "optional inline sparkline (<svg>)" and ships no Sparkline component. %>
<%= render Ui::StatComponent.new(label: "MRR", value: "£48,200", delta: 4.2, intent: :success) do |s| %>
  <% s.with_spark { tag.svg(role: "img", "aria-label": "MRR trend, 12 months") { sparkline_path(mrr_series) } } %>
<% end %>
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

## Structure & elements

The pieces `page-anatomies.md` composes screens from. Small, high-reuse, and deliberately dull —
a stacked list is a `MediaObject` in a `divide-y` container, a page header is a `Heading` with a
`ButtonGroup` in its actions slot.

### Heading — `app/components/ui/heading_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class HeadingComponent < ViewComponent::Base
    renders_one :eyebrow          # breadcrumbs, or a kicker label
    renders_one :description
    renders_one :actions
    renders_one :meta             # status badge + timestamps

    # Scale is the ONLY axis: same anatomy, three sizes. Tag and step move together so a
    # card heading can never be an <h2> styled small (which breaks document outline).
    LEVEL = {
      page:    { tag: :h1, size: "text-step-3" },
      section: { tag: :h2, size: "text-step-2" },
      card:    { tag: :h3, size: "text-step-1" },
    }.freeze

    def initialize(title:, level: :section, id: nil)
      raise ArgumentError, "unknown level #{level}" unless LEVEL.key?(level.to_sym)
      @title, @level, @id = title, level.to_sym, id
    end

    def tag = LEVEL.fetch(@level)[:tag]
    def size = LEVEL.fetch(@level)[:size]
    attr_reader :title, :id
  end
end
```
```erb
<%# heading_component.html.erb %>
<div class="stack" style="--space: var(--space-2xs)">
  <%= eyebrow %>
  <div class="cluster justify-between items-start">
    <div class="stack" style="--space: var(--space-3xs)">
      <%= content_tag tag, title, id: id, class: "#{size} font-semibold text-foreground" %>
      <% if description? %>
        <p class="text-step-0 text-muted-foreground prose-measure"><%= description %></p>
      <% end %>
    </div>
    <% if actions? %><div class="cluster"><%= actions %></div><% end %>
  </div>
  <% if meta? %>
    <div class="cluster text-step--2 text-muted-foreground"><%= meta %></div>
  <% end %>
</div>
```

### Breadcrumbs — `app/components/ui/breadcrumbs_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class BreadcrumbsComponent < ViewComponent::Base
    # [{ label:, href: }, ...] — the LAST entry is the current page and is never a link.
    def initialize(items:, collapse_after: 3)
      @items, @collapse_after = items, collapse_after
    end

    def crumbs = @items
    def collapsed? = @items.size > @collapse_after

    # first -> [collapsed middle] -> last two. Keeps "where am I" legible on a phone
    # without horizontal scrolling, which defeats the whole purpose.
    def head = collapsed? ? @items.first(1) : @items[0..-2]
    def hidden_middle = collapsed? ? @items[1..-3] : []
    def tail = collapsed? ? @items.last(2) : [@items.last]
  end
end
```
```ruby
# in the component — the separator is markup, and the icon carries NO size class:
# `with-icon` sizes it to 1em in currentColor (see Icons above).
def separator = tag.span(helpers.lucide_icon("chevron-right"), class: "with-icon",
                        aria: { hidden: true })
def crumb_link_class = "min-h-touch inline-flex items-center hover:text-foreground"
```
```erb
<%# breadcrumbs_component.html.erb — separators are markup + aria-hidden, never ::after %>
<nav aria-label="Breadcrumb">
  <ol class="cluster text-step--1 text-muted-foreground" style="--space: var(--space-3xs)">
    <% head.each do |c| %>
      <li class="cluster" style="--space: var(--space-3xs)">
        <%= link_to c[:label], c[:href], class: crumb_link_class %>
        <%= separator %>
      </li>
    <% end %>

    <% if collapsed? %>
      <%# hidden_middle is already [{ label:, href: }] — the shape Dropdown's `items:` expects %>
      <li class="cluster" style="--space: var(--space-3xs)">
        <%= render(Ui::DropdownComponent.new(items: hidden_middle)) do |d| %>
          <% d.with_trigger do %>
            <span aria-hidden="true">…</span>
            <span class="sr-only"><%= t(".show_more", count: hidden_middle.size) %></span>
          <% end %>
        <% end %>
        <%= separator %>
      </li>
    <% end %>

    <% tail.each_with_index do |c, i| %>
      <li class="cluster" style="--space: var(--space-3xs)">
        <% if i == tail.size - 1 %>
          <span class="text-foreground font-medium" aria-current="page"><%= c[:label] %></span>
        <% else %>
          <%= link_to c[:label], c[:href], class: crumb_link_class %>
          <%= separator %>
        <% end %>
      </li>
    <% end %>
  </ol>
</nav>
```

### Description list — `app/components/ui/description_list_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class DescriptionListComponent < ViewComponent::Base
    renders_many :rows, "RowComponent"

    LAYOUT = {
      stacked: "stack",                                              # dt above dd
      inline:  "stack divide-y divide-border",                       # label left, value right
      grid:    "grid-auto",                                          # wide summaries
    }.freeze

    def initialize(layout: :stacked)
      raise ArgumentError, "unknown layout #{layout}" unless LAYOUT.key?(layout.to_sym)
      @layout = layout.to_sym
    end

    def container_class = LAYOUT.fetch(@layout)
    def inline? = @layout == :inline

    class RowComponent < ViewComponent::Base
      # `values` is an Array so one label can carry several <dd>s — no list inside a <dd>.
      def initialize(label:, values: nil, value: nil, mono: false)
        @label = label
        @values = Array(values || value)
        @mono = mono
      end
      attr_reader :label, :values

      # A blank <dd> reads as a rendering bug, so absence is stated.
      def blank? = @values.compact_blank.empty?
      def value_class = "text-step-0 text-foreground#{' font-mono' if @mono}"
    end
  end
end
```
```erb
<%# description_list_component.html.erb — no wrapper may sit between <dt> and <dd> %>
<dl class="<%= container_class %>">
  <% rows.each do |row| %>
    <div class="<%= inline? ? 'cluster justify-between py-2' : 'stack' %>"
         style="--space: var(--space-3xs)">
      <dt class="text-step--1 text-muted-foreground"><%= row.label %></dt>
      <% if row.blank? %>
        <dd class="text-step-0 text-muted-foreground">
          <span aria-hidden="true">—</span><span class="sr-only"><%= t(".not_set") %></span>
        </dd>
      <% else %>
        <% row.values.each do |v| %>
          <dd class="<%= row.value_class %>"><%= v %></dd>
        <% end %>
      <% end %>
    </div>
  <% end %>
</dl>
```

### Button group — `app/components/ui/button_group_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class ButtonGroupComponent < ViewComponent::Base
    renders_many :buttons

    # Actions and single-select are different ELEMENTS, not a style variant:
    # a view switcher is a radiogroup, a toolbar is a group of buttons.
    ROLE = { actions: "group", select: "radiogroup" }.freeze

    def initialize(label:, kind: :actions)
      raise ArgumentError, "unknown kind #{kind}" unless ROLE.key?(kind.to_sym)
      @label, @kind = label, kind.to_sym
    end

    def role = ROLE.fetch(@kind)
    def controller = @kind == :select ? "list-navigation" : nil
    attr_reader :label
  end
end
```
```erb
<%# button_group_component.html.erb %>
<%# isolate + focus-visible:z-10 on children so the focus ring is not clipped by the overlap %>
<div class="cluster isolate" style="--space: 0"
     role="<%= role %>" aria-label="<%= label %>"
     <%= "data-controller=#{controller}" if controller %>>
  <%# each child: Ui::ButtonComponent(variant: :outline) with
      first:rounded-s-md last:rounded-e-md rounded-none [&:not(:first-child)]:-ms-px
      focus-visible:z-10 min-h-touch %>
  <%= buttons.each { |b| concat b.to_s } %>
</div>
```

### Media object — `app/components/ui/media_object_component.rb`

```ruby
# frozen_string_literal: true
module Ui
  class MediaObjectComponent < ViewComponent::Base
    renders_one :media          # avatar, icon chip or thumbnail (wrap in `frame`)
    renders_one :body
    renders_one :trailing       # timestamp, chevron, actions

    SIZE = { sm: "size-8", md: "size-10", lg: "size-12" }.freeze

    def initialize(size: :md)
      raise ArgumentError, "unknown size #{size}" unless SIZE.key?(size.to_sym)
      @size = size.to_sym
    end

    def media_class = "frame flex-none #{SIZE.fetch(@size)}"
  end
end
```
```erb
<%# media_object_component.html.erb — never stacks; the side-by-side relationship IS the pattern %>
<div class="cluster items-start">
  <% if media? %><div class="<%= media_class %>"><%= media %></div><% end %>
  <%# min-w-0 lets long words truncate instead of pushing the media off-screen %>
  <div class="stack min-w-0 flex-1" style="--space: var(--space-3xs)"><%= body %></div>
  <% if trailing? %><div class="flex-none"><%= trailing %></div><% end %>
</div>
```

### Divider — a recipe, not a component

No component: an `<hr>` is already `role="separator"`.

```erb
<hr class="border-border">                                  <%# plain rule %>
<div class="cluster">                                       <%# labelled: rule — label — rule %>
  <span aria-hidden="true" class="h-px flex-1 bg-border"></span>
  <span class="text-step--2 text-muted-foreground"><%= t(".or") %></span>
  <span aria-hidden="true" class="h-px flex-1 bg-border"></span>
</div>
<span aria-hidden="true" class="w-px self-stretch bg-border"></span>   <%# vertical, in a cluster %>
```

In lists and tables put `divide-y divide-border` on the **container** — one declaration instead of
n elements, and no stray rule after the last row.

**Coverage.** With Button + Card (reference-implementation.md) plus the above — including the
structure & elements group (Heading, Breadcrumbs, Description list, Button group, Media object,
and Divider as a recipe) — the full catalog
from [components.md](components.md) has worked code. Pagination stays the Pagy-based
`shared/_pagination` partial; CRUD tables stay the `shared/_crud_*` partials — both refactored
to role tokens (see components.md). Extend any new component by mirroring these exact shapes:
frozen `BASE`/`VARIANT`/`SIZE` map, role tokens, primitive composition, attribute-driven state,
a11y baked in.

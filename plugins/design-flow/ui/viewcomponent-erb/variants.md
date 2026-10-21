# `/design-flow:variants` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:variants` after `ui_adapter.py` resolves this adapter. The command owns the constraint, the phases and the
verdicts; this file carries what is true only for ERB and ViewComponents.

## Phase 2 — the switcher, scaffolded to be thrown away (Rails)

Three artefacts, and all three are temporary. Write them where the discard step can find them.

```
app/views/design_variants/<slug>/
  variants.json      the manifest — brief, brand, one entry per variant
  _a.html.erb        the variants themselves, partials so the winner can be moved unchanged
  _b.html.erb
  _c.html.erb
app/views/design_variants/show.html.erb          the switcher
app/controllers/design_variants_controller.rb    dev-only
config/routes.rb                                 one guarded block
```

`variants.json`:

```json
{
  "slug": "pricing",
  "brief": "pricing page for the fmworkflows marketing site",
  "brand": "fidara:fmworkflows",
  "variants": [
    { "id": "a", "file": "_a.html.erb", "rationale": "denser; leads with the comparison table" },
    { "id": "b", "file": "_b.html.erb", "rationale": "airier; leads with the claim, price below" },
    { "id": "c", "file": "_c.html.erb", "rationale": "single-column; one plan recommended by default" }
  ]
}
```

**The route is development-only.** A switcher route renders every *rejected* variant, so leaving
it reachable in production ships three landing pages nobody approved. Guard it, and constrain the
slug so a path segment cannot walk out of the directory:

```ruby
# config/routes.rb — REMOVE this block when a variant is chosen.
if Rails.env.development?
  get "design_variants/:slug", to: "design_variants#show", as: :design_variant,
      constraints: { slug: /[a-z0-9-]+/ }
end
```

```ruby
# app/controllers/design_variants_controller.rb — DELETE when a variant is chosen.
class DesignVariantsController < ApplicationController
  def show
    root = Rails.root.join("app/views/design_variants", params[:slug])
    @set = JSON.parse(root.join("variants.json").read)
    @chosen = @set["variants"].find { |v| v["id"] == params[:v] } || @set["variants"].first
    @partial = "design_variants/#{params[:slug]}/" \
               "#{@chosen['file'].delete_prefix('_').delete_suffix('.html.erb')}"
  end
end
```

The toggle is a `turbo-frame` and its links — the same mechanism as the shared CRUD modal
(`crud-modal-pattern.md`), so no new Stimulus controller and no new framework surface. Swapping a
frame leaves the page, the scroll position and the viewport alone, which is the whole point: the
comparison happens **at real viewports in the actual app**, not in a description of three options.

```erb
<%# app/views/design_variants/show.html.erb — DELETE when a variant is chosen. %>
<div class="stack">
  <nav class="cluster" aria-label="Variants">
    <% @set["variants"].each do |v| %>
      <%= link_to v["id"].upcase, design_variant_path(@set["slug"], v: v["id"]),
                  class: "min-h-touch",
                  data: { turbo_frame: "variant" },
                  aria: { current: (v["id"] == @chosen["id"] ? "true" : nil) } %>
    <% end %>
  </nav>
  <p class="text-muted-foreground"><%= @chosen["rationale"] %></p>
  <%= turbo_frame_tag "variant" do %>
    <%= render @partial %>
  <% end %>
</div>
```

Style the switcher chrome with role tokens like anything else, and keep it minimal — it is a
comparison harness, not a screen. `min-h-touch` still applies; you will be tapping it on a phone.

## Phase 3 — the conformance command

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ui/viewcomponent-erb/scripts/variant_conformance.py" .
```

## Phase 4 — verify the discard

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ui/viewcomponent-erb/scripts/variant_conformance.py" --verify-discard .
```

The winning partial moves to its real home under `app/views/...`; delete `app/views/design_variants/` entirely, the controller and the
routes block. The library row records `--built app/views/home/index.html.erb`-style paths.

# Views, Forms, Assets, and Hotwire

## Contents
1. Layouts, templates, partials
2. Helpers
3. Forms with `form_with`
4. Assets: Propshaft + importmap
5. Turbo Drive
6. Turbo Frames
7. Turbo Streams (request-driven and broadcast)
8. Page refreshes + morphing (calmer default for live UI)
9. Stimulus
10. Choosing the right Hotwire tool
11. Markdown templates (8.1)

---

## 1. Layouts, templates, partials

Layout `app/views/layouts/application.html.erb` wraps everything via
`<%= yield %>`; secondary regions via
`<%= yield :sidebar %>` + `<% content_for :sidebar do %>...<% end %>`.
Per-controller layouts by file name (`layouts/admin.html.erb` +
`layout "admin"`).

Partials start with `_`, and take **locals, not instance variables**:

```erb
<%# app/views/products/_product.html.erb %>
<%# locals: (product:, show_price: true) -%>   <%# strict locals: typo-proof, defaults allowed %>
<div id="<%= dom_id(product) %>">
  <%= link_to product.name, product %>
  <%= number_to_currency(product.price) if show_price %>
</div>
```

```erb
<%= render @products %>                     <%# collection render: one query-less loop, uses _product %>
<%= render "form", product: @product %>
<%= render partial: "product", collection: @products, cached: true %>  <%# fragment-caches each %>
```

`dom_id(record)` → `product_42` — the glue for Turbo Frame/Stream targeting.
ERB rules: `<%= %>` outputs (HTML-escaped), `<% %>` executes, `<%# %>`
comments. Everything is escaped by default; `raw`/`html_safe` only on
content you generated or sanitized (`sanitize(user_html)`).

## 2. Helpers

`app/helpers/*_helper.rb` modules are available in all views. Use them for
presentation logic (formatting, conditional classes); reach for POROs/models
when logic grows. Built-ins to prefer over hand-rolling: `link_to`,
`button_to` (non-GET links — renders a form, Turbo-safe), `number_to_currency`,
`number_with_delimiter`, `time_ago_in_words`, `l(date, format: :long)`,
`truncate`, `pluralize`, `simple_format`, `content_tag`/`tag.div`,
`image_tag`, `token_list`/`class_names` (conditional CSS classes),
`turbo_frame_tag`, `cache`. Dates/times: render with `<%= l record.created_at %>`
respecting the app zone.

## 3. Forms with `form_with`

```erb
<%= form_with model: @product do |form| %>
  <% if form.object.errors.any? %>
    <div class="errors">
      <ul><% form.object.errors.each do |e| %><li><%= e.full_message %></li><% end %></ul>
    </div>
  <% end %>

  <%= form.label :name %>
  <%= form.text_field :name %>

  <%= form.label :status %>
  <%= form.select :status, Product.statuses.keys.map { |s| [s.humanize, s] } %>

  <%= form.collection_select :supplier_id, Supplier.order(:name), :id, :name, include_blank: true %>
  <%= form.collection_checkboxes :tag_ids, Tag.all, :id, :name %>

  <%= form.number_field :price, step: 0.01 %>
  <%= form.date_field :available_on %>
  <%= form.checkbox :featured %>          <%# modern aliases: checkbox, textarea, rich_textarea %>
  <%= form.file_field :photo %>            <%# multipart handled automatically %>
  <%= form.rich_textarea :description %>   <%# Action Text %>

  <%= form.submit %>
<% end %>
```

- `model: @product` infers URL + method (POST/PATCH), prefills values, and
  scopes params under `product:` — exactly what `params.expect(product: [...])`
  reads. `model: [:admin, @product]` for namespaced routes;
  `url:`/`scope:` for model-less forms (search forms:
  `form_with url: search_path, method: :get`).
- Nested attributes: model declares
  `accepts_nested_attributes_for :variants, allow_destroy: true,
  reject_if: :all_blank`; view uses `form.fields_for :variants`; params use
  the double-bracket `variants_attributes: [[:id, :name, :_destroy]]` shape
  in `expect`.
- Fields repopulate automatically on validation-failure re-render — which is
  why `render :new, status: :unprocessable_entity` matters.
- CSRF token is embedded automatically; never disable
  `protect_from_forgery` for browser forms.

## 4. Assets: Propshaft + importmap

**Propshaft** serves `app/assets` (and gem/plugin asset paths) with digest
fingerprints — no transpiling, no bundling, no Sass. Reference assets through
helpers so digests resolve: `image_tag "logo.svg"`,
`stylesheet_link_tag :app` (links the app stylesheets with
`data-turbo-track="reload"` in the default layout), and in CSS use relative
`url("bg.png")` which Propshaft rewrites.

**Importmap** maps bare JS module names to files without Node:

```bash
bin/importmap pin sortablejs          # downloads to vendor/javascript + pins in config/importmap.rb
bin/importmap unpin sortablejs
bin/importmap audit                   # CVE check (part of bin/ci)
bin/importmap outdated
```

`app/javascript/application.js` is the entrypoint
(`javascript_importmap_tags` in the layout); Stimulus controllers under
`app/javascript/controllers` are pinned via `pin_all_from` and
auto-registered. Write modern ES modules; no JSX/TS transpile step — if the
project truly needs npm build tooling, that's `jsbundling-rails`
(`--javascript=esbuild`), a different lane. Tailwind via `tailwindcss-rails`
runs its own standalone watcher through `bin/dev` — still no Node.

## 5. Turbo Drive

Ships on by default: intercepts links/forms, swaps `<body>`, merges `<head>`
— SPA feel with zero code. Interactions you'll actually write:

```erb
<%= link_to "Delete", product_path(@product),
      data: { turbo_method: :delete, turbo_confirm: "Really delete?" } %>
<%= button_to "Delete", @product, method: :delete,
      data: { turbo_confirm: "Really?" } %>   <%# button_to preferred: it's a real form %>
<div data-turbo="false">...</div>              <%# opt an area out %>
<%= link_to "Report", report_path, data: { turbo: false } %>
```

JS that must re-run after navigation: listen for `turbo:load` (fires on
first load and every visit), or better, put behavior in Stimulus
controllers whose `connect()` handles it naturally. Assets marked
`data-turbo-track="reload"` force a full reload when their digest changes
(deploys).

## 6. Turbo Frames

A frame scopes navigation to a fragment: links/forms **inside** a frame
replace only that frame, matched by id.

```erb
<%= turbo_frame_tag dom_id(@product) do %>
  <%= render "summary", product: @product %>
  <%= link_to "Edit", edit_product_path(@product) %>   <%# edit view must render the same frame id %>
<% end %>

<%= turbo_frame_tag "modal" %>                          <%# empty target frame %>
<%= link_to "New product", new_product_path, data: { turbo_frame: "modal" } %>

<%= turbo_frame_tag "activity", src: activity_feed_path, loading: :lazy do %>
  Loading…
<% end %>                                               <%# lazy-loaded fragment %>
```

Break out when needed: `target: "_top"` on the frame, or
`data: { turbo_frame: "_top" }` on a specific link (e.g. after successful
save inside a modal, the controller `redirect_to` with `status: :see_other`
+ a `turbo_frame: "_top"` submission, or respond with a stream). Frame
responses that don't contain a matching frame id render nothing — the #1
frame gotcha; keep frame ids identical across index/show/edit templates via
`dom_id`.

## 7. Turbo Streams

Streams mutate named DOM targets. Actions: `append, prepend, replace,
update, remove, before, after, refresh` (+ `morph` method variant).

Request-driven (form submissions get `text/vnd.turbo-stream.html`):

```ruby
# create action
respond_to do |format|
  if @comment.save
    format.turbo_stream   # renders create.turbo_stream.erb
    format.html { redirect_to @post, status: :see_other }
  else
    format.html { render :new, status: :unprocessable_entity }
  end
end
```

```erb
<%# app/views/comments/create.turbo_stream.erb %>
<%= turbo_stream.append "comments", @comment %>            <%# renders _comment partial %>
<%= turbo_stream.update "comments_count", @post.comments.count %>
<%= turbo_stream.replace dom_id(@comment), partial: "comments/comment", locals: { comment: @comment } %>
```

Or inline: `render turbo_stream: turbo_stream.remove(@comment)`.

Broadcast-driven (over Action Cable / Solid Cable) — model side:

```ruby
class Comment < ApplicationRecord
  belongs_to :post
  broadcasts_to ->(comment) { [comment.post, :comments] }, inserts_by: :append
  # granular: broadcast_replace_to / broadcast_append_later_to etc. — prefer *_later variants
end
```

View subscribes: `<%= turbo_stream_from @post, :comments %>`. Broadcasts
render the model's partial by convention. **Security:** stream names are
signed; still scope channels to what the viewer may see — never broadcast
per-user data on a shared stream.

## 8. Page refreshes + morphing

Often the simplest live UI: broadcast "something changed", let subscribed
pages refresh themselves, and morph the DOM so scroll/focus/form state
survive.

```ruby
class Post < ApplicationRecord
  broadcasts_refreshes            # or broadcasts_refreshes_to ->(post) { [post.board] }
end
```

```erb
<%# layout <head> %>
<%= turbo_refreshes_with method: :morph, scroll: :preserve %>
<%# page %>
<%= turbo_stream_from @post %>
```

Exclude client-managed islands from morphing with
`data-turbo-permanent`. Prefer refresh+morph over hand-managed stream
choreography when the whole page is cheap to re-render.

## 9. Stimulus

Small controllers that sprinkle behavior onto server-rendered HTML.

```js
// app/javascript/controllers/clipboard_controller.js
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["source"]
  static values  = { successMessage: { type: String, default: "Copied!" } }
  static classes = ["copied"]

  copy() {
    navigator.clipboard.writeText(this.sourceTarget.value)
    this.element.classList.add(this.copiedClass)
  }
}
```

```erb
<div data-controller="clipboard" data-clipboard-success-message-value="Done"
     data-clipboard-copied-class="flash">
  <input data-clipboard-target="source" value="<%= @invite_url %>" readonly>
  <button data-action="clipboard#copy">Copy</button>   <%# click is the implicit event for buttons %>
</div>
```

Conventions: filename `*_controller.js` → identifier (`clipboard`,
`nested--name` for subfolders); state lives in `values` (reactive:
`urlValueChanged()` callbacks) and the DOM, not JS objects; lifecycle
`initialize/connect/disconnect` (clean up listeners/observers in
`disconnect` — Turbo re-connects controllers on every visit); talk between
controllers via `outlets` or dispatched events
(`this.dispatch("copied", { detail: {...} })`). Keep controllers generic and
reusable (`toggle`, `autosubmit`, `dropdown`) rather than page-specific.
`data-action="input->search#submit keydown.esc->modal#close"` for explicit
events/filters.

## 10. Choosing the right Hotwire tool

1. Whole-page navigation is fine → **nothing** (Turbo Drive already has it).
2. One self-contained region navigates independently (inline edit, modal,
   tabs, lazy panel) → **Frame**.
3. One user action must change several places at once (add to list + bump
   counter) → **Stream response**.
4. Other users/processes cause the change (live feed, presence, job
   completion) → **broadcast**: `broadcasts_refreshes` + morphing first,
   granular stream broadcasts when re-rendering the page is too heavy.
5. Pure client behavior (toggle, clipboard, drag) → **Stimulus**.

## 11. Markdown templates (8.1)

`show.md.erb` renders for `format.md`; controllers may
`render markdown: @page` (calls `#to_markdown`). Useful for `llms.txt`-style
endpoints, docs, and agent-readable mirrors of HTML pages — same
controller, extra `format` line.

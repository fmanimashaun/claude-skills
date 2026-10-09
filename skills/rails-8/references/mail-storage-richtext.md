# Action Mailer, Active Storage, Action Text, Action Mailbox

## Contents
1. Action Mailer
2. Active Storage
3. Action Text
4. Action Mailbox (brief)

---

## 1. Action Mailer

```bash
bin/rails g mailer Order receipt   # mailer class + views + spec + preview (specs and preview under spec/)
```

```ruby
class OrderMailer < ApplicationMailer
  def receipt
    @order = params[:order]                       # parameterized style — preferred
    attachments["receipt.pdf"] = ReceiptPdf.new(@order).render if @order.pdf?
    mail to: @order.customer.email, subject: "Your receipt for order ##{@order.number}"
  end
end

OrderMailer.with(order: order).receipt.deliver_later   # ALWAYS deliver_later in app code
```

- Views mirror actions: `app/views/order_mailer/receipt.html.erb` +
  `receipt.text.erb` (ship both; multipart is automatic). Mailer layouts in
  `app/views/layouts/mailer.*`.
- Defaults in `ApplicationMailer` (`default from: "Shop <no-reply@…>"`).
  `headers`, `cc:`, `bcc:`, `reply_to:` as kwargs to `mail`.
- URLs in mail need full hosts: set
  `config.action_mailer.default_url_options = { host: "example.com" }` per
  environment, and use `*_url` helpers (never `*_path`) in mailer views.
- Inline images: `attachments.inline["logo.png"] = File.read(...)` then
  `image_tag attachments["logo.png"].url`.
- **Previews live in `spec/mailers/previews/`, not `test/mailers/previews/`.**
  `spec/mailers/previews/order_mailer_preview.rb` classes render at
  `http://localhost:3000/rails/mailers` (development only —
  `show_previews` defaults to `Rails.env.development?`). Keep every mailer
  action previewable (build or fetch representative data inside the preview).
  `bin/rails g mailer` writes the file there for you; it is where rspec-rails
  looks, and this skill's apps have no `test/` directory at all
  (`project-setup.md` §2). Do not hand-create one for a preview.

  **Why, and the one thing that breaks it.** Rails' own default is
  `#{Rails.root}/test/mailers/previews`, added by the Action Mailer railtie as a
  **union** — `options.preview_paths |= [...]` — so it is always in the search
  path whether or not the directory exists
  ([`railtie.rb`](https://github.com/rails/rails/blob/8-1-stable/actionmailer/lib/action_mailer/railtie.rb)).
  rspec-rails adds `spec/mailers/previews` ahead of it from its own
  `rspec_rails.action_mailer` initializer, which runs `before:
  "action_mailer.set_configs"` — **but only while `preview_paths` is still
  empty** ([`rspec-rails.rb`](https://github.com/rspec/rspec-rails/blob/v8.0.4/lib/rspec-rails.rb),
  `config_default_preview_path`). So *any* app-level touch of the setting —
  append included, because the guard is `.empty?` and not "already contains" —
  silently drops the `spec/` default. If you need an extra location, name both:

  ```ruby
  # config/application.rb — only if you need a location beyond the default
  config.action_mailer.preview_paths << Rails.root.join("spec/mailers/previews").to_s
  config.action_mailer.preview_paths << Rails.root.join("lib/mailer_previews").to_s
  ```

  Append, never assign: assignment cannot remove Rails' `test/` entry anyway (the
  railtie unions it back in afterwards). `preview_path` **singular** is not a
  Rails 8 setting — deprecated in 7.1, removed in 7.2.
- Delivery config: development doesn't send
  (`perform_deliveries`/preview instead); test collects into
  `ActionMailer::Base.deliveries`; production sets
  `delivery_method = :smtp` + `smtp_settings` (credentials from
  `Rails.application.credentials`). `deliver_later` runs through Active Job
  (`ActionMailer::MailDeliveryJob`) — deliveries survive request failures
  and honor after-commit enqueueing.

## 2. Active Storage

Setup (new apps already migrated): `bin/rails active_storage:install
&& bin/rails db:migrate`. Service per environment in `config/storage.yml`;
`config.active_storage.service = :local` (Disk) in dev/test, `:amazon`
(S3), `:google` (GCS), S3-compatible endpoints, or `:mirror` during
migrations. **The `:azure` service was removed in 8.1** — use an
S3-compatible gateway or another provider. Credentials come from the
encrypted credential store.

```ruby
class User < ApplicationRecord
  has_one_attached :avatar do |attachable|
    attachable.variant :thumb, resize_to_limit: [100, 100], preprocessed: true
  end
end

class Post < ApplicationRecord
  has_many_attached :images
  validates :images, content_type: %w[image/png image/jpeg]  # via active_storage_validations gem,
  # or hand-roll: validate { errors.add(:images, "wrong type") unless images.all? { _1.content_type.in?(...) } }
end
```

Forms: `form.file_field :avatar` / `:images, multiple: true` — attach on
save via `params.expect(user: [:avatar])` / `images: []`. Purge with
`user.avatar.purge_later`.

Rendering:

```erb
<%= image_tag user.avatar.variant(:thumb), alt: user.name if user.avatar.attached? %>
<%= image_tag post.hero.variant(resize_to_limit: [800, nil], format: :webp), alt: "" %>
<%= link_to "Download", rails_blob_path(post.report, disposition: "attachment") %>
```

- **`image_tag` never invents an `alt`** — Rails stopped deriving one from the
  filename, so an omitted `alt:` ships an `<img>` with no alt attribute at all.
  Name the image when it carries information the surrounding text does not
  (`alt: user.name` for a lone avatar); pass `alt: ""` when an adjacent heading
  or label already says it, as a post hero next to its `<h1>` does.
- Variants need the `image_processing` gem (uncomment in Gemfile) and
  libvips (the generated Dockerfile installs it). `preprocessed: true`
  generates eagerly in a job instead of first-request. (Rails 8.2, **unreleased**,
  deprecates `preprocessed: true` in favour of `process: :later`:
  `references/rails-8-2-readiness.md`.)
- URL modes: default redirect controller (short-lived signed redirect to
  the service) — fine generally; **proxying**
  (`rails_storage_proxy_path`, or `config.active_storage.resolve_model_to_route
  = :rails_storage_proxy`) lets Thruster/CDN cache files through your app.
  Public buckets: `public: true` in storage.yml for permanent URLs.
- **Direct uploads** (browser → service, bypassing the app):
  `form.file_field :images, multiple: true, direct_upload: true` + pin/import
  `@rails/activestorage` and `ActiveStorage.start()` in `application.js`.
  Progress events (`direct-upload:progress`) hook into a Stimulus controller.
- Previews for video/PDF (`file.preview(resize_to_limit: [300, 300])`)
  require ffmpeg/poppler — installed in the default Dockerfile? No: add the
  packages if you need previews. Check representability with
  `file.representable?` and render via `file.representation(...)`.
- Files are served/streamed by the app or service — never store user uploads
  in `public/`. Downloads for processing: `blob.download` (memory) or
  `blob.open { |tmpfile| ... }`.

## 3. Action Text

Rich text stored in dedicated tables, attachable-aware. On Rails 8.1 the built-in editor is **Trix**;
**Lexxy** is an opt-in gem that replaces it (see *Lexxy* below).

```bash
bin/rails action_text:install && bin/rails db:migrate   # requires image_processing for embeds
```

```ruby
class Article < ApplicationRecord
  has_rich_text :content            # ActionText::RichText record, no column on articles
end
```

```erb
<%# simple_form, as every form here. `as: :rich_text_area` is the ONLY name simple_form maps (5.0.2+),  %>
<%# and it is required: a has_rich_text attribute has no column, so simple_form cannot infer the type. %>
<%# It renders through the builder's rich_text_area, which Rails 8 keeps as an alias of rich_textarea. %>
<%= f.input :content, as: :rich_text_area %>   <%# permit :content as a plain scalar in expect %>
<%= @article.content %>                  <%# renders sanitized HTML + attachments %>
<%= @article.content.to_plain_text %>
```

Embedded uploads go through Active Storage direct upload automatically.
Style via `app/assets/stylesheets/actiontext.css`. Custom attachables
(mention a user in rich text) implement `ActionText::Attachable` and render
via their `to_attachable_partial_path`. Avoid raw HTML injection into rich
text; content is sanitized on render.

### Lexxy (the Lexical-based editor), on Rails 8.1

Verified 2026-10-01 against `lexxy` 1.0.0 (2026-09-28) and Rails 8.1.4 (#1438). Rails 8.1 has **no editor
setting**: `config.action_text.editor` and `ActionText::Editor` exist only on Rails `main` (8.2.0.alpha,
rails/rails#51238), and no 8.2 has been released. Do not set that option on 8.1: nothing in 8.1.4 reads it.

On 8.0 and 8.1, the `lexxy` gem (`railties >= 8.0.2`) takes over Action Text's form helpers itself. Once it
is installed, `form.rich_text_area`, and therefore the `f.input :content, as: :rich_text_area` above, renders
a Lexxy editor instead of Trix. No form changes.

```ruby
# Gemfile. Pin 1.0: Lexxy's own install doc still shows "~> 0.9.21", which cannot resolve 1.0.
gem "lexxy", "~> 1.0"
```

```ruby
# config/importmap.rb (importmap apps)
pin "lexxy", to: "lexxy.js"
pin "@rails/activestorage", to: "activestorage.esm.js"   # attachments need it
```

```javascript
// app/javascript/application.js. In a jsbundling app, run `yarn add @37signals/lexxy @rails/activestorage`
// and import "@37signals/lexxy" instead.
import "lexxy"
```

```erb
<%# app/views/layouts/application.html.erb: Lexxy's own stylesheet. actiontext.css styles trix-editor and %>
<%# trix-toolbar, which never match Lexxy's <lexxy-editor>; it still styles rendered .trix-content. %>
<%= stylesheet_link_tag "lexxy" %>
```

- **Existing content.** Lexxy emits Action Text's canonical markup, and its docs and the 1.0 post state that
  Trix-authored content and attachments keep working. That is the vendor's statement; neither Rails nor this
  skill tests it, so open a few real records before switching a production app.
- **Sanitizing, app-wide.** Lexxy widens Action Text's sanitizer allowlist (tables, `video`, `audio`, and attributes
  such as `style`), which changes every rich-text render, not only the editor. It also appends `"var"` to Loofah's
  global `ALLOWED_CSS_FUNCTIONS`, which reaches every `sanitize` call in the app. Both run unconditionally at boot,
  with the opt-out below too (`lib/lexxy/engine.rb` L52–60, v1.0.0). Review them against your content policy.
  Rendered content keeps Rails' default wrapper, `<div class="trix-content">`
  (`app/views/layouts/action_text/contents/_content.html.erb`), so actiontext.css still styles it. Override that
  file with `<div class="lexxy-content">` to give it Lexxy's styles.
- **Custom attachables** keep rendering through their `to_attachable_partial_path` partials.
- **Not under enforced Trusted Types.** Lexxy's configuration doc: "Lexxy does not yet work under enforced
  Trusted Types". An app whose CSP sends `require-trusted-types-for 'script'` stays on Trix.
- **Opting out of the takeover** while keeping the gem: set `config.lexxy.override_action_text_defaults = false`
  in `config/application.rb`. Lexxy's prefixed helpers (`form.lexxy_rich_text_area`) are then explicit, and
  simple_form's `as: :rich_text_area` renders Trix again.

## 4. Action Mailbox (brief)

Inbound email routed to mailbox classes: `bin/rails action_mailbox:install`,
configure an ingress (SES/Mailgun/Postmark/SendGrid/relay) in
`config/environments/production.rb` + credentials. The outcome: mail sent to a
`reply-<signed id>@` address reaches `RepliesMailbox`, which finds the thread from the signed id and
records the reply as its sender:

```ruby
# app/mailboxes/application_mailbox.rb
class ApplicationMailbox < ActionMailbox::Base
  routing(/^reply-(.+)@/i => :replies)
end

class RepliesMailbox < ApplicationMailbox
  def process
    thread = MessageThread.find_signed!(mail.to.first[/reply-(.+)@/, 1])
    thread.comments.create!(body: mail.decoded, author: author_from(mail.from))
  end

  private
    def author_from(addresses)
      # `email_address` is the authentication generator's column. An unknown sender finds nil:
      # decide what happens to their mail before `create!` runs, rather than letting it raise.
      User.find_by(email_address: addresses.first)
    end
end
```

Test with `ActionMailbox::TestHelper#receive_inbound_email_from_mail` and the
dev conductor UI at `/rails/conductor/action_mailbox/inbound_emails`.

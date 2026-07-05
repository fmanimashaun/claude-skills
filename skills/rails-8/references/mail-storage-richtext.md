# Action Mailer, Active Storage, Action Text, Action Mailbox

## Contents
1. Action Mailer
2. Active Storage
3. Action Text
4. Action Mailbox (brief)

---

## 1. Action Mailer

```bash
bin/rails g mailer Order receipt   # mailer class + views + preview + test
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
- **Previews** — `test/mailers/previews/order_mailer_preview.rb` classes
  render at `http://localhost:3000/rails/mailers`; keep every mailer action
  previewable (build or fetch representative data inside the preview).
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
<%= image_tag user.avatar.variant(:thumb) if user.avatar.attached? %>
<%= image_tag post.hero.variant(resize_to_limit: [800, nil], format: :webp) %>
<%= link_to "Download", rails_blob_path(post.report, disposition: "attachment") %>
```

- Variants need the `image_processing` gem (uncomment in Gemfile) and
  libvips (the generated Dockerfile installs it). `preprocessed: true`
  generates eagerly in a job instead of first-request.
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

Rich text (Trix editor) stored in dedicated tables, attachable-aware.

```bash
bin/rails action_text:install && bin/rails db:migrate   # requires image_processing for embeds
```

```ruby
class Article < ApplicationRecord
  has_rich_text :content            # ActionText::RichText record, no column on articles
end
```

```erb
<%= form.rich_textarea :content %>       <%# permit :content as a plain scalar in expect %>
<%= @article.content %>                  <%# renders sanitized HTML + attachments %>
<%= @article.content.to_plain_text %>
```

Embedded uploads go through Active Storage direct upload automatically.
Style via `app/assets/stylesheets/actiontext.css`. Custom attachables
(mention a user in rich text) implement `ActionText::Attachable` and render
via their `to_attachable_partial_path`. Avoid raw HTML injection into rich
text; content is sanitized on render.

## 4. Action Mailbox (brief)

Inbound email routed to mailbox classes: `bin/rails action_mailbox:install`,
configure an ingress (SES/Mailgun/Postmark/SendGrid/relay) in
`config/environments/production.rb` + credentials, then:

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
end
```

Test with `ActionMailbox::TestHelper#receive_inbound_email_from_mail` and the
dev conductor UI at `/rails/conductor/action_mailbox/inbound_emails`.

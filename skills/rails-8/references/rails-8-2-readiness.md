# Rails 8.2 readiness — UNRELEASED, on `main` only

**Rails 8.2 is not released** (see the version bullet in `SKILL.md`: no gem, no tag). Everything below was read
on 2026-10-10 from `main`'s CHANGELOGs, the edge guide and merged pull requests, and is **not installable**: do
not put any of it in an app that runs a released Rails. It is here so an agent that meets an 8.2 `main` app, or
is asked what will change, answers from a checked record instead of a blog post, and so a later promotion to
doctrine has the citations to hand. **Verify each item against the 8.2 release notes when 8.2 ships**: items
marked *in flux* were still moving on `main`.

The edge guide's last commit when read was `54cce92c9a89445ea62b4df3e4cc327888e7339c` (2026-02-15); the page
shows no revision of its own. Statuses: **[On main, unreleased]** unless a row says *[Released in 8.1]*.

## CSRF: `Sec-Fetch-Site` header checking — [On main, unreleased]

- `protect_from_forgery using:` takes two strategies: `:header_only` (checks only the `Sec-Fetch-Site` request
  header) and `:header_or_legacy_token` (falls back to the token for older browsers). `:header_only` is the
  default for **new** 8.2 applications.
- Calling `protect_from_forgery` **without specifying a strategy is deprecated**. Its old default,
  `:null_session`, conflicts with `default_protect_from_forgery` (`:exception`); silencing it with an explicit
  `with: :null_session` is the documented route. The new config key is
  `config.action_controller.default_protect_from_forgery_with`. Whether `using:` alone silences the deprecation
  was not verified.
- `ActionController::InvalidAuthenticityToken` is deprecated in favour of `InvalidCrossOriginRequest`.
- Rails 8.1 (released) has none of this: there `protect_from_forgery with: :exception` is what
  `default_protect_from_forgery` calls (8-1-stable `railtie.rb`).
- Sources: `actionpack/CHANGELOG.md` on `main`; <https://edgeguides.rubyonrails.org/8_2_release_notes.html>.

## Active Job — [On main, unreleased], with the 8.1 side marked

- **8.1 [Released in 8.1.0]:** `ActiveJob::Base.enqueue_after_transaction_commit` no longer accepts `:never`,
  `:always` or `:default` (removed, not deprecated), and the global
  `config.active_job.enqueue_after_transaction_commit` was removed too. The built-in `sidekiq` Active Job
  adapter is **deprecated**: use the adapter in the sidekiq gem (sidekiq 7.3.3 or newer).
  Sources: the 8.1 release notes (Removals) and `activejob/CHANGELOG.md` on `8-1-stable`.
- **8.2 [On main, unreleased]:** `enqueue_after_transaction_commit` is a boolean again, and
  `config.active_job.enqueue_after_transaction_commit = true` is the default for new apps and for
  `config.load_defaults "8.2"`; the global config works as a boolean. The deprecated built-in `sidekiq`
  adapter is **removed**. The built-in `queue_classic`, `resque`, `delayed_job`, `backburner` and `sneakers`
  adapters are **deprecated** (upgrade targets named in the changelog: resque 3.0 and delayed_job 4.2.0 or
  newer). Sources: `activejob/CHANGELOG.md` on `main`; the 8.2 release notes.
- What an 8.1 app gets by default for `enqueue_after_transaction_commit` is **not stated** by the official
  sources read; do not assert it.

## `has_secure_password algorithm: :argon2` — [On main, unreleased]

Built-in Argon2 support for `has_secure_password` (add `gem "argon2", "~> 2.3"`); the changelog states Argon2
has no password length limit, unlike BCrypt's 72-byte restriction. The edge guide also describes a
`SecurePassword.register_algorithm` API. 8-1-stable's `activemodel/CHANGELOG.md` has no mention.
Source: `activemodel/CHANGELOG.md` on `main`.

## `Rails.app` — [On main, unreleased]

`Rails.app` is an alias for `Rails.application`. `Rails.app.creds` gives combined access to credentials stored
in either `ENV` or the encrypted credentials file (the edge guide lists `require` and `option` methods).
`Rails.app.revision` returns a version identifier for error reporting, monitoring and cache keys, taken from
`ENV["REVISION"]`, then a `REVISION` file, then git, with app config as the last resort. Source:
`railties/CHANGELOG.md` on `main`.

## Active Storage, Action Text, JSON attributes — [On main, unreleased]

- **Active Storage `analyze:`**: attachments can be analysed **before validation** so metadata such as width
  and height is available to model validations; the timing is `analyze: :immediately` (the default), `:later`
  or `:lazily`. `activestorage/CHANGELOG.md` and the edge guide.
- **Active Storage `process:`**: `process: :immediately` processes a variant at once (values `:lazily`,
  `:later`, `:immediately`); `preprocessed: true` is **deprecated in favour of `process: :later`**.
- **Action Text**: the Trix-specific API is deprecated, including `ActionText::Content#to_trix_html` and
  `ActionText::RichText#to_trix_html`, `Attachable#to_trix_content_attachment_partial_path` (replaced by
  `#to_editor_content_attachment_partial_path`), `Attachments::TrixConversion` and `ActionText::TrixAttachment`.
  The guide gives no replacement for `to_trix_html`. `actiontext/CHANGELOG.md`.
- **`has_json` and `has_delegated_json`** are **Active Model**, not Active Record: schema-enforced access to JSON
  attributes. By the changelog, `has_json` gives typed accessors and defaults for declared keys and casts
  assigned values (`"100"` is stored as the integer `100`); `has_delegated_json` does the same but exposes the
  keys directly on the model. `activemodel/CHANGELOG.md`.

## Herb compiles HTML ERB — [On main, unreleased], in flux

- Under the 8.2 defaults, Action View compiles **HTML-format** templates with Herb:
  `config.action_view.erb_implementation` accepts `:herb` or `:erubi`, the 8.2 defaults set `:herb`, and
  `Rails.application.config.action_view.erb_implementation = :erubi` is the opt-out. Other formats stay on
  Erubi, and an app that sets its own implementation keeps it for all formats (rails/rails#58721, merge
  commit `9fb66ed2dc239e9f78d51c8e36b43f287f548d52`; the Herb handler itself is #58552, `60eb5cb72dbf06ef9de39c6786df2f20e838884f`).
  The first proposal's option name (`html_aware_erb`) was replaced in review: use `erb_implementation`.
- `herb` becomes a runtime dependency of `actionview`, declared the way `erubi` is (#58552). The version
  constraint was **not verified** (the doctrine in `ecosystem-gems.md` §13b pins `~> 0.10` for the dev gem).
- `bin/rails herb:check` and `ActionView::HerbChecker` (rails/rails#58770, `5f1654d584d256a5f16eb364db29de2d60913b11`)
  check templates; #58874 (`6122999ff4cccb706dc6d6ed1a0d3676a16cf173`) makes the checker name Herb's security
  validator explicitly because Herb 0.11 dropped it from the defaults, and was still discussing a bump to
  `~> 0.11` on 2026-10-01: treat the checker's exact behaviour as **in flux**.
- A structural error such as an unclosed tag **fails compilation** (#58721). ViewComponent#2717 (open when
  read, a report not a Rails statement) says `herb:check` **does not reach sidecar templates** and that they
  follow the new default.
- The 8.2 release notes page names none of the above; the evidence is the pull requests and `main`'s
  `actionview/CHANGELOG.md`. Do not cite the Herb site's "ships with Rails 8.2" line as a release claim.

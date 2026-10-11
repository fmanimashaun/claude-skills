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
- Rails 8.1 (released): `protect_from_forgery with: :exception` is what `default_protect_from_forgery` calls
  (8-1-stable `railtie.rb`), the 8-1-stable `actionpack/CHANGELOG.md` has no `Sec-Fetch-Site`, `header_only` or
  deprecation entry, and the 8.1 release notes mention no CSRF change.
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
- **`has_json` and `has_delegated_json`** are **Active Model**, not Active Record: "schema-enforced access to JSON
  attributes" (`activemodel/CHANGELOG.md`; the edge guide gives the same one line and no more). Their semantics
  beyond that line were not verified, so none are recorded here.

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

# Round 2 (#1756) — read on 2026-10-12 from `main` at `d05a45b41edf679d2dfba4e40366af80628626ff`

Everything below is **[On main, unreleased]** unless a row says *[Released in 8.1]*, and each item was checked against
`v8.1.4` and `8-1-stable` for its absence there. The verdict tables are in
`docs/evidence/audits/2026-10-12-rails-8-2-readiness-round-2.md`. The 8.2 release notes page names almost none of
these: the evidence is the pull requests, `main`'s CHANGELOGs and `guides/source`. Do not put any of it in an app that
runs a released Rails.

## Floors and removals

- **Ruby >= 3.3.5** (`rails.gemspec`; 8.1 requires >= 3.2.0; rails/rails#58908). **PostgreSQL 10.0** is the adapter's
  documented minimum (8.1: 9.5; #55282).
- **A dynamic `:controller` or `:action` route segment raises `ArgumentError` at draw time** (deprecated since Rails 5.0;
  #58893). A Regexp for either also raises, `get "show", to: PhotosController` now needs `action: "show"`, and
  `Request#controller_class` raises `ActionDispatch::MissingController` with no `:controller` param. 8.1 still draws
  such routes. With `config.eager_load` on, boot **logs a warning** (not an error) for each route that references a
  missing controller.
- **The Rails 6.1 Active Record Marshal format is removed** (#57382): `ActiveRecord::Marshalling.format_version` is
  `7.1`, the only value accepted; 6.1 raises `ArgumentError`. 8.1.4 still defaults to 6.1 and accepts both. Main's
  `activerecord/CHANGELOG.md` has no entry for it.
- **An enum's `not_<value>` scope includes rows where the column is NULL** (`IS DISTINCT FROM`; #55912, #55954); in 8.1
  it is `where.not` and excludes them. Read an upgraded `Product.not_active` as "everything but active, NULLs too".

## HTTP `QUERY` and `bin/rails query`

- **`QUERY` verb** (#57973): `query "search", to: "search#index"` (or `via: :query`), `request.query?`, an
  integration-test `query` helper. QUERY requests are **exempt from CSRF forgery protection** only when the method
  really is QUERY (a `_method=query` override through a form POST is still verified), and the database selector sends
  them to the **replica** like GET and HEAD. `via: :all` routes now receive QUERY. The app server must accept the
  method (Puma needs `supported_http_methods`).
- **`bin/rails query`** (#57156) runs read-only queries (Active Record expressions or `--sql`), prints JSON, connects
  to the reading role by default and prevents writes; subcommands `schema <table>`, `models`, `explain`. The JSON
  output comes from the changelog text; the command was not run.

## `load_defaults "8.2"` (and two options that are not defaults)

Set by the 8.2 defaults (`railties/lib/rails/application/configuration.rb`, `when "8.2"`; `configuring.md`):

| setting | what it does | default before 8.2 | 8.2 default |
|---|---|---|---|
| `ActiveSupport.raise_on_invalid_time_zone_parse` (a module setting, not under `config.`; #57211) | `TimeZone#parse` raises `ArgumentError` for a string with no recognisable date (`"foobar"` was `nil`) | `false` | `true` |
| `config.action_dispatch.strict_accept_header` (#57579) | an `Accept` that also holds `*/*` keeps its specific types (`application/json, */*` returns JSON) instead of forcing HTML | `false` | `true` |
| `config.active_record.postgresql_adapter_decode_bytea` / `..._decode_money` | manual queries (`select_value`) return bytea as a binary String and money as `BigDecimal` instead of a UTF-8 String | `false` | `true` |
| `config.active_storage.analyze` | `:immediately` analyses before validation (metadata such as width is available to validations); `:later`, `:lazily` | not set | `:immediately` |
| `config.active_storage.s3_public_uploads_via_acl` | S3 sets `public-read` on `public: true` uploads | `true` | `false`: declare `upload: { acl: "public-read" }` on the service where you rely on it |
| `config.action_dispatch.default_headers` (#56564) | `X-XSS-Protection` is no longer in the defaults | sent as `"0"` since 7.0 | absent |

- **Not `load_defaults` items:** `config.active_record.shuffle_unordered_selects` (#58548) is opt-in and `false`; when on
  (meant for test and development) it shuffles the rows of generated `SELECT`s that have no `ORDER BY`, best effort:
  raw SQL, `find`, `find_by`, association loads and `LIMIT 1` are unaffected. `config.active_storage.draw_direct_upload_route`
  (#58377, default `true`) turns off only the direct-upload route; with it `false`, `rich_textarea` omits
  `data-direct-upload-url` unless given and Trix hides its attach button and ignores dropped files.
- **`ActiveJob::Attributes`** adds `ActiveModel::Attributes`-style typed `attribute` declarations to jobs: values are
  serialised into the job data and restored on deserialisation, so they survive retries and `ActiveJob::Continuation`
  steps. Included by `ActiveJob::Continuable`, usable alone; custom types must serialise as job arguments. Not a config
  default.

## Secrets and hardening

- **Rotating `secret_key_base`** (the Security guide on `main`, ~lines 331-386; the guide section is new, **the API is not**):
  `app.message_verifiers.rotate(secret_key_base: old)` in a `config.before_initialize` block is *[Released in 8.1]*
  (the `Application#message_verifiers` API comment in 8.1.4). The recipe puts the new value in `secret_key_base`, keeps
  the old one in credentials (`old_secret_key_base`), rotates before any verifier is built, and removes the rotation
  once old messages have expired. Cookies rotate **separately**: derive the old signed and encrypted cookie secrets from
  the old key with `app.key_generator(old)` and the `action_dispatch.signed_cookie_salt` /
  `encrypted_cookie_salt` salts, then `config.action_dispatch.cookies_rotations.rotate :signed, secret` and
  `.rotate :encrypted, secret` in an `after_initialize` block. `cookies_rotations` itself is in 8.1 (its 8.1 guide
  example is the SHA1 to SHA256 digest change); the old-secret recipe is main's. The guide warns against keeping an
  exposed secret as a fallback.
- **ffmpeg and ffprobe input arguments** (Active Storage): `config.active_storage.video_preview_input_arguments`
  (passed to ffmpeg before `-i`) and `config.active_storage.ffprobe_arguments` (passed to ffprobe before the path),
  both default `""`; neither exists in 8.1. Main's Security guide ("Media Processing of File Uploads") says to name the
  allowed codecs, for example `"-codec_whitelist h264,aac"` for both, to force one demuxer with `-f` and to restrict
  input protocols with `-protocol_whitelist`. Every codec in a stored file, audio included, must be listed or analysis
  raises `JSON::ParserError`; check names with `ffmpeg -decoders`. Rails does not ship ffmpeg.
- **Active Record encryption keys from ENV** (#57311): `ACTIVE_RECORD_ENCRYPTION__PRIMARY_KEY`,
  `ACTIVE_RECORD_ENCRYPTION__DETERMINISTIC_KEY` and `ACTIVE_RECORD_ENCRYPTION__KEY_DERIVATION_SALT` (double
  underscore). ENV is read first (in development `.env` next), then the encrypted credentials; values set under
  `config.active_record.encryption` are applied last and override. In 8.1: credentials or explicit config only.

## `Rails.app` and other CHANGELOG-only additions

- **`Rails.app.credentials`** is the ordinary `Rails.application.credentials` (long-standing, *[Released in 8.1]*)
  reached through the new `Rails.app` alias; **`Rails.app.creds`** is a different, new object (ENV, then in development
  `.env`, then the encrypted credentials, with `require` and `option`). Main's own comment says credentials are best used
  via `creds` so ENV can override. **`Rails.app.envs`** reads ENV by symbol path (`envs.require(:aws, :access_key_id)`
  reads `AWS__ACCESS_KEY_ID`) with `require` / `option(default:)`; **`Rails.app.dotenvs`** reads a `.env` file (default
  `Rails.root.join(".env")`) the same way and supports `${VAR}` and `$(command)` interpolation (#56455).
- **`frozen_string_literal` on by default** (#57252) has a narrow scope: **newly generated apps** get a
  `config/bootsnap.rb` with `Bootsnap.enable_frozen_string_literal(app_only: true)`, which freezes literals in
  **application code, not dependencies**, and `.rubocop.yml` is set to match. It is not framework-wide, not an existing-app
  change, and needs bootsnap (the generator skips it with `--skip-bootsnap`, `--dev` or on JRuby).
- `ActionDispatch::Request#bearer_token` (#56474) returns the token of an `Authorization: Bearer ...` header, `nil` when
  absent or not Bearer.
- **`default_order`** (#57632, #57936) is a query method and a `has_many` option (`has_many :comments, default_order:
  :likes`) that orders only when no other order is given; an explicit `.order` replaces it.
- `rate_limit`'s `to:` and `within:` accept a lambda or a method-name symbol: `rate_limit to: :max_requests, within:
  :time_window, by: -> { current_user.id }`.
- `f.datalist` renders a `<datalist>` whose id is `f.field_id(:country, :datalist)`, wired to an input with `list:`.
  Active Storage `attach!` raises if the attachment is not saved. `ActiveSupport::TestCase.around do |test_case,
  block| ... end` runs between setup and teardown.
- **`RedisCacheStore` is rewritten on `redis-client >= 0.28.0`**: configure with `:url`, put advanced options in a custom
  `RedisClient::Config` passed as `:client`; the `:redis` argument still works but warns and `DEFAULT_REDIS_OPTIONS` is
  deprecated.
- **`validates` conditions now combine** (`activemodel/CHANGELOG.md`, fixes #55761): `validates :title, presence: { if:
  :local? }, if: :global?` needs both; the per-validator option used to replace the top-level one silently, for `:if`,
  `:unless` and `:on`. **A behaviour change on upgrade**: validations that ignored the top-level condition now respect it.
- Pull request numbers for `rate_limit`, `f.datalist`, `attach!`, `TestCase.around`, the Redis cache store and the
  `validates` change were not looked up: the CHANGELOG entries on `main` are the source. `f.datalist` also lists a
  `datalist_tag` helper whose release status was not checked.

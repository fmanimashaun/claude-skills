---
name: rails-8
description: >-
  Playbook for building full-stack Ruby on Rails 8.1 applications "the Rails
  way" — vanilla Rails, Hotwire (Turbo + Stimulus), the Solid stack, Propshaft
  + importmap, RSpec testing, ecosystem gems, OpenAPI docs, AI features,
  observability, and Kamal 2 deployment. Use this skill whenever the user is
  creating, extending, debugging, refactoring, testing, upgrading,
  documenting, or deploying a Rails app — or mentions Ruby on Rails, a Gemfile
  containing rails, ERB templates, Active Record, migrations, Hotwire, Turbo,
  Stimulus, Action Mailer, Active Storage, Action Text, Action Cable, Solid
  Queue, Solid Cache, Kamal, Thruster, RSpec, FactoryBot, simple_form,
  Tailwind, OpenAPI, Swagger, rswag, ruby_llm, or `bin/rails` commands. Trigger it for indirect phrasings like "my Ruby web
  app", "add a background job", "make this page update live", "add login to
  my app", "document my API", or "add AI to my app" when the project is
  Rails. Also for "how should I structure this in Rails?" questions.
---

# Rails 8 Full-Stack Development — The Rails Way

This skill encodes the officially recommended way to build Rails 8.1.x
applications, distilled from the Rails Guides (v8.1.3.1) and the framework's own
generated defaults. Follow it to produce code a Rails core contributor would
recognize as idiomatic: the *omakase* menu, the one-person-framework, the
majestic monolith.

## Operating principles

1. **Convention over configuration.** Before writing configuration, glue code,
   or a new abstraction, check whether Rails already has a convention for it.
   It almost always does. Naming alone (singular model `Order`, table
   `orders`, controller `OrdersController`, partial `_order.html.erb`) wires
   most things together.
2. **Vanilla Rails first.** Rails 8 deliberately eliminated whole gem
   categories — use the framework's answer, never a substitute: the built-in
   authentication generator (not an auth engine), Solid Queue (not an
   external job backend), Solid Cache/Cable (not Redis), Hotwire (not a JS
   SPA), importmap (not a JS bundler), Kamal (not a PaaS). **Deliberate
   exception — testing:** this skill standardizes on the industry RSpec stack
   (rspec-rails, FactoryBot, Faker, Capybara, SimpleCov, WebMock/VCR, pure
   RSpec matchers — see `references/testing.md`); apps are scaffolded with
   `--skip-test` so the framework's default suite never exists in the repo.
   **Project exception:** dropped into an existing app that made different
   choices (another test framework, job backend, auth solution, a JS
   bundler, PostgreSQL…), follow the project, not this skill. Never mix two
   conventions for the same concern in one codebase.
3. **Fat models are fine; skinny everything is a myth.** Rails-way domain
   logic lives in Active Record models, POROs under `app/models`, and
   concerns. Do not introduce service-object layers, repositories, or
   hexagonal architecture unless the project already uses them. Controllers
   stay thin: translate HTTP to model calls, pick a response.
4. **Server-rendered HTML is the default UI.** Reach for Turbo Frames/Streams
   and small Stimulus controllers before any client-side framework. JSON APIs
   only when there is a genuine non-browser consumer.
5. **Compression of complexity.** One command should do the setup work:
   `bin/setup`, `bin/dev`, `bin/ci`, `bin/rails db:prepare`, `kamal deploy`.
   Keep those commands working.

## Version facts (verified 2026-08-01)

- Current stable: **Rails 8.1.3.1** (2026-07-29) — a **security** release, not
  a routine one. It fixes **CVE-2026-66066** (GHSA-xr9x-r78c-5hrm, *critical*,
  CVSS v4 9.5): possible arbitrary file read and remote code execution in
  Active Storage variant processing, via libvips loaders Rails did not block.
  **Every 8.1 below 8.1.3.1 is affected**, so pin `>= 8.1.3.1` and never leave
  an app on 8.1.3. Backports: **8.0.5.1** and **7.2.3.2**. The fix also needs
  **libvips >= 8.13** at runtime, and an app that may already have been
  exploited must rotate `secret_key_base` and its other secrets.
  ([release post](https://rubyonrails.org/2026/7/29/Rails-Versions-7-2-3-2-8-0-5-1-and-8-1-3-1-have-been-released),
  [advisory](https://github.com/rails/rails/security/advisories/GHSA-xr9x-r78c-5hrm))
- The 8.1 series gets bug fixes until **2026-10-10**, security fixes until
  **2027-10-10**. Rails **8.0 left bug-fix support on 2026-05-07** and is
  security-only until 2026-11-07; 7.2 security support ends 2026-08-09.
  ([support dates](https://rubyonrails.org/2025/10/29/new-rails-releases-and-end-of-support-announcement)
  — the maintenance policy page states only the relative rule, never these dates.)
- **Rails 8.1 requires Ruby >= 3.2.0** (`required_ruby_version` in the 8.1.3.1
  gemspecs). That is a compatibility minimum, not a support statement — **this
  skill's floor is Ruby 3.4**, because 3.4 and 4.0 are the only branches still
  in normal maintenance: **Ruby 3.2 is end-of-life since 2026-04-01** and
  **3.3 has been security-fixes-only since the same date**
  ([branches](https://www.ruby-lang.org/en/downloads/branches/)). Prefer the
  current stable **4.0.x** (4.0.6 on 2026-08-01; check, don't assume). 3.4.x is
  the supported alternative. Keep YJIT for production; ZJIT is still
  experimental. Dropped into an app already on 3.2/3.3, follow the project —
  Rails permits it — but say the interpreter is unsupported, and note that the
  parser hazard in `references/controllers-routing.md` §7 applies there.
- **There is no Rails 8.2 or 9.0** as of 2026-08-29 — no gem, no tag, no
  announcement. Third-party posts claiming an 8.2 release have circulated and
  are wrong; check rubygems.org or the Rails blog before believing a number.
  **The most convincing false signal is an OFFICIAL page, not a blog post.**
  `edgeguides.rubyonrails.org/8_2_release_notes.html` returns **200**, is titled
  *"Ruby on Rails 8.2 Release Notes"*, sits in the guides nav beside 8.1 and 8.0,
  and carries **no banner saying it documents an unreleased version** (all four
  re-verified 2026-08-29). Edge guides are built from `main`, where
  `RAILS_VERSION` is `8.2.0.alpha`, so the page for the *next* version always
  exists months ahead of it. **An `edgeguides.rubyonrails.org/<N>_<M>_release_notes.html`
  page is not evidence of release.** Released guides live at
  `guides.rubyonrails.org`; the tell is that an unreleased page is a **stub**,
  with its "Highlights" and "Major Features" headings empty.
- **Settle it mechanically rather than by reading a page** — two commands, both
  authoritative, neither a judgement call:

  ```bash
  curl -s https://rubygems.org/api/v1/gems/rails.json | jq -r .version   # 8.1.3.1
  git ls-remote --tags https://github.com/rails/rails 'refs/tags/v8.2*'  # empty
  ```

  A released version has **both** a gem and a tag. Absent either, it is not out,
  whatever any page is titled.
- New apps get `config.load_defaults 8.1` in `config/application.rb`.
- If the user's app is on an older Rails, upgrade one minor version at a time
  (7.2 → 8.0 → 8.1) with `bin/rails app:update` and the framework-defaults
  file. Verify current versions with a web search if the date is well past
  **August 2026** — and look for a newer *security* patch specifically, since
  those ship as a fourth version segment (8.1.3 → 8.1.3.1) that a `~> 8.1.3`
  pin will pick up but a `= 8.1.3` pin will not.

## What `rails new` gives you (the default stack)

| Concern | Default | Notes |
|---|---|---|
| Database | SQLite3 (production-ready) | `--database=postgresql` (or mysql/trilogy) for client-server DBs |
| Assets | **Propshaft** | No transpiling; digest-stamping only |
| JavaScript | **importmap-rails** + Hotwire (Turbo + Stimulus) | `--javascript=bun/esbuild/webpack/rollup` if bundling needed |
| CSS | Plain CSS | `--css=tailwind|bootstrap|bulma|postcss|sass` |
| Jobs / Cache / WebSockets | **Solid Queue / Solid Cache / Solid Cable** | Database-backed; no Redis |
| Web server | **Puma**, fronted by **Thruster** in Docker | Thruster: HTTP/2, TLS, compression, asset caching |
| Deployment | **Kamal 2** + generated `Dockerfile` | `config/deploy.yml`, `.kamal/secrets` |
| Testing | **RSpec** + FactoryBot + Capybara (pure RSpec, no matcher add-ons) | Scaffold with `--skip-test`; doctrine in `references/testing.md` |
| Lint / security | rubocop-rails-omakase, Brakeman, bundler-audit | Wired into CI |
| CI | `config/ci.rb` + `bin/ci` (local CI, new in 8.1) and a GitHub Actions workflow | `--skip-ci` omits only the GitHub workflow files; `config/ci.rb` + `bin/ci` are always generated. `--skip-test` strips their test steps — add one back (`testing.md` §11) |
| Extras | PWA stubs (`app/views/pwa/`), `script/` for one-offs, `/up` health endpoint, Docker entrypoint running `db:prepare` | |

## The golden-path feature workflow

For "add X to my app" tasks, work in this order — it matches how Rails wants
to be driven and keeps every step verifiable:

1. **Model + migration.** `bin/rails g model Product name:string:index
   price_cents:integer` (or `g migration AddStatusToOrders status:integer`).
   Put constraints in the migration (`null: false`, defaults, FKs, unique
   indexes), validations + associations in the model. Run
   `bin/rails db:migrate`.
2. **Routes.** Add a `resources :products` line (nest at most one level;
   use `module:`/`namespace` for admin areas).
3. **Controller.** Seven RESTful actions max; more verbs mean a new resource,
   not a custom action. Use `params.expect(product: [:name, :price_cents])`
   for strong parameters (8.x idiom).
4. **Views.** ERB with partials; **every form via simple_form** (`simple_form_for` —
   mandatory, never raw `form_with`); render collections with
   `render @products`. Add Turbo Frames/Streams only where the UX needs
   partial updates.
5. **Background work / mail / files** as needed (job, mailer, attachment) —
   always through Active Job / Action Mailer / Active Storage, never raw
   threads or manual file paths.
6. **Tests.** Model spec + request spec at minimum; a system spec for any
   nontrivial user flow. FactoryBot factories for data (`testing.md`).
7. **Verify.** `bundle exec rspec` (or the project's suite), then
   `bin/rubocop -a`, or the whole gate: `bin/ci` — which is only a whole gate
   once `config/ci.rb` carries the RSpec step, because the mandated
   `--skip-test` scaffold writes none (`testing.md` §11). Fix everything it
   flags before declaring done.

Scaffolding (`bin/rails g scaffold ...`) is legitimate for standard CRUD —
generate, then trim what isn't needed.

## Conventions cheat sheet (apply everywhere)

- **Strong params:** `params.expect(user: [:email, :name])` — not
  `require/permit` in new 8.x code, never `permit!`.
- **Turbo-compatible responses:** redirect after mutation with
  `status: :see_other` (303); re-render invalid forms with
  `status: :unprocessable_entity` (422). Turbo silently breaks without these.
- **Partials take locals, not ivars.** Declare them:
  `<%# locals: (product:, show_price: true) %>` (strict locals).
- **Time:** `Time.current`, `2.days.ago`, `travel_to` in tests. Never
  `Time.now`/`Date.today` in app code (they ignore the app time zone).
- **Queries:** scopes on the model; `includes` to kill N+1s; `find_each` for
  batches; no SQL string interpolation — ever (`where("name = ?", n)` or
  hash conditions).
- **Callbacks:** fine for the object's own lifecycle (normalize, cache a
  column, enqueue its own follow-up job); avoid reaching into *other* models
  from callbacks — do that in the controller/job that orchestrates.
- **I18n-ready copy** in views (`t(".title")`) when the app declares more than
  one locale in `config.x.locales` — see `references/i18n.md` for the setup that
  declaration implies. Hardcode English only in a project that declared a single
  locale, which is a choice on record rather than an omission.
- **Credentials, not ENV, for app secrets:** `Rails.application.credentials.dig(:stripe, :secret_key)`;
  edit via `bin/rails credentials:edit`.
- Run `bin/rubocop` mentally: 2-space indent, `frozen_string_literal` not
  required (omakase), double quotes, no `and/or` for control flow.

## New in 8.1 — reach for these when relevant

- **Active Job Continuations** — long jobs resume from the last completed
  `step` after a deploy/restart instead of starting over. (`jobs-and-realtime.md`)
- **Structured Event Reporting** — `Rails.event.notify("user.signup",
  user_id: 123)` with `tagged`/`set_context` and pluggable subscribers, for
  machine-readable telemetry alongside the human log. (`observability.md`)
- **Local CI** — `config/ci.rb` DSL run by `bin/ci`: setup, RuboCop,
  bundler-audit, `bin/importmap audit`, Brakeman, optional `gh signoff` — plus
  the test step **you** write, which Rails omits under the `--skip-test`
  scaffold this skill mandates. (`testing.md` §11)
- **Markdown rendering** — `render markdown: @page` / `format.md` /
  `.md.erb` templates; useful for docs pages and AI-facing endpoints.
  (`views-hotwire.md`)
- **`bin/rails credentials:fetch some.key`** — shell-friendly credential
  reads, e.g. in `.kamal/secrets`. (`deployment-kamal.md`)
- **Deprecated associations** — `has_many :posts, deprecated: true` reports
  every usage (`:warn`/`:raise`/`:notify`) to help retire schema.
  (`models.md`)
- **Local-registry Kamal deploys** — Kamal 2.8 added an **opt-in** local
  registry (`registry: server: localhost:5555`, which 8.1 generates for
  you); Kamal's own default is still Docker Hub, so a config written
  without that line needs credentials. (`deployment-kamal.md`)
- **Alphabetized `schema.rb` columns** — expect reordered-but-equivalent
  schema diffs after the first 8.1 migration; don't "fix" them.
- **Verbose redirect logs** in development
  (`config.action_dispatch.verbose_redirect_logs = true` in new apps).

**`load_defaults 8.1` also flips seven framework defaults** — the complete list, with
what each one changes, is `project-setup.md` §7. Three change behaviour you can trip
over in a *new* app, not just an upgraded one:

- `render json:` **no longer HTML-escapes** `<`, `>`, `&`, U+2028/9
  (`escape_json_responses = false`) — Rails' changelog names the risk as
  *"vulnerabilities when the resulting JSON is embedded in HTML"*. (`auth-security.md` §4)
- A path-relative `redirect_to "orders/new"` **raises**
  (`action_on_path_relative_redirect = :raise`). (`auth-security.md` §4)
- `.first`/`.last` on an unordered relation **raises**
  `ActiveRecord::MissingRequiredOrderError` rather than warning.

Deprecations to avoid in new code: order-dependent finders (`.first`/`.last`)
on relations with no inferable order — add an explicit `.order` (this one *raises*
under 8.1 defaults, see above); `signed_id_verifier_secret` (use
`Rails.application.message_verifiers`); `String#mb_chars`; `update_all` with
`WITH`/`DISTINCT`.

## Reference files — read before working in an area

Read the relevant file(s) **before** writing code in that area; they contain
the exact APIs, generated-file layouts, and the traps.

| Read | When the task involves |
|---|---|
| `references/style.md` | **How code should read** — conditional returns, method + invocation order, bang methods, visibility modifiers, CRUD controllers, controller↔model boundary, `_later`/`_now` job naming. Sourced to 37signals' `STYLE.md` (fizzy), with each adopt/adapt decision and its reason recorded |
| `references/project-setup.md` | `rails new`, app structure, generators, config/environments, credentials, dev workflow (`bin/setup`, `bin/dev`), upgrading |
| `references/models.md` | Migrations, Active Record models, validations, associations, callbacks, scopes/queries, enums, `normalizes`, tokens, encryption, multi-DB |
| `references/controllers-routing.md` | Routes, **URL design (human vanity paths for user-facing pages vs REST for records + JSON API; the reconciliation)**, controllers, `params.expect`, filters, rate limiting, sessions/cookies/flash, redirects & status codes, API-only apps |
| `references/views-hotwire.md` | ERB, layouts, partials, helpers, forms (simple_form; Turbo contract), Turbo Drive/Frames/Streams, morphing, Stimulus, importmap/Propshaft, markdown rendering |
| `references/jobs-and-realtime.md` | Active Job, Solid Queue, recurring jobs, 8.1 continuations, concurrency limits, Action Cable / Solid Cable |
| `references/mail-storage-richtext.md` | Action Mailer, Action Mailbox, Active Storage (uploads/variants/direct upload), Action Text |
| `references/auth-security.md` | `bin/rails g authentication`, sessions, password reset, authorization patterns, CSRF/XSS/SQLi, CSP, the security checklist |
| `references/multi-tenancy.md` | **Isolation vs identification** (the two axes) — row-level isolation via association traversal, session-selected tenant (never in the URL), subdomain per *plane*, why not `default_scope`, the GlobalID/job-boundary hole, PostgreSQL RLS and its owner-bypass trap, opaque public ids vs UUID PKs |
| `references/sso.md` | Enterprise SSO: multi-tenant OIDC (default) + SAML hatch, identities keyed [provider, issuer, uid], JIT roles, enabled-vs-enforced, tenant dashboard, cert rotation, SLO, audit, RSpec proving set |
| `references/testing.md` | RSpec (pure — no matcher add-ons), FactoryBot/Faker, request/system specs, Capybara, WebMock/VCR, SimpleCov, `bin/ci`, `--skip-test` scaffolding |
| `references/i18n.md` | **Internationalisation** — declared once (`config.x.locales`), `around_action` + `I18n.with_locale` (a `before_action` leaks across threads), lazy lookup, `lang`/`dir`, what must NOT be translated. **Situational**: `/rails-flow:setup-flow` asks. |
| `references/performance-caching.md` | Solid Cache, fragment/russian-doll caching, HTTP caching/ETags, N+1s, `load_async`, counter caches, YJIT/jemalloc/Puma/Thruster, profiling |
| `references/observability.md` | Active Support Instrumentation (hook catalog, subscribers, custom events), 8.1 `Rails.event`, `Rails.error`, log tagging, APM/OpenTelemetry wiring |
| `references/advanced-active-record.md` | Composite primary keys, multiple databases (replicas, role switching, sharding), Active Record encryption + key rotation |
| `references/ecosystem-gems.md` | simple_form, tailwindcss-rails, OmniAuth, Pundit/CanCanCan, Pagy, Ransack/pg_search, mission_control-jobs, friendly_id, paper_trail, bullet, ViewComponent, strong_migrations, and when to prefer the defaults |
| `references/api-documentation.md` | OpenAPI/Swagger for JSON APIs — rswag (test-driven docs), rspec-openapi, apipie, Swagger UI/Redoc, CI drift gates |
| `references/ai-llm.md` | LLM features via ruby_llm — chat, `acts_as_chat` persistence, streaming with Hotwire, tools, structured output, embeddings + pgvector, testing AI |
| `references/extending-rails.md` | Application templates (`rails new -m`), custom generators, overriding built-in generator templates, engines/plugins, Rack middleware |
| `references/deployment-kamal.md` | Kamal 2 (`config/deploy.yml`, secrets, accessories, rollback), Dockerfile, Thruster, SQLite-in-production, production checklist |

Companion skill: **`hotwire`** goes deeper than `views-hotwire.md` on Turbo,
Stimulus, and adds **Hotwire Native** (iOS/Android apps, bridge components,
path configuration). Use both together for frontend-heavy or mobile work.

Multiple files often apply (a "notifications" feature touches models, jobs,
views-hotwire, and testing). Skim all that apply; don't guess APIs from
memory when the file is one `view` away.

## Deviations and existing codebases

When dropped into an existing app, first read: `Gemfile`, `config/routes.rb`,
`config/application.rb` + the current environment file, `db/schema.rb`, and
one representative model/controller/view. Match the app's established
patterns (RSpec? service objects? ViewComponent? Tailwind?) even where this
skill prefers otherwise — consistency beats purity. Flag, don't silently
"fix", conventions you'd change.

## Definition of done

A change is done when: migrations run cleanly both ways where practical,
`bundle exec rspec` (or the project's suite) passes, `bin/rubocop` is clean,
Brakeman raises no new warnings, and — for full-gate confidence — `bin/ci`
passes. `bin/ci` does **not** stand in for the first of those unless
`config/ci.rb` carries the RSpec step (`testing.md` §11): under the mandated
`--skip-test` scaffold it runs no specs at all, so a green `bin/ci` on its own
proves lint and audits only. For UI work, state which Turbo behavior was used
and why. Never hand back code you haven't at least boot-checked (`bin/rails runner`, a test, or
`bin/rails zeitwerk:check` for autoloading-sensitive changes) when a runtime
is available.

# The Rails Gem Ecosystem — When to Reach Beyond the Defaults

Vanilla Rails covers more than most people think; every gem is a dependency
you maintain forever. This file maps the popular ecosystem to the rule:
**Rails default first, gem when the default demonstrably runs out.** If a
project already uses one of these, follow the project (and this file tells
you how each one is idiomatically used).

## Contents
1. Decision table
2. Forms: simple_form
3. CSS: tailwindcss-rails
4. Authentication: the built-in generator (+ omniauth)
5. Authorization: pundit / cancancan
6. Pagination: pagy
7. Search & filtering: ransack, pg_search
8. Background jobs: Solid Queue, full stop
9. Model utilities: friendly_id, paper_trail, discard, aasm
10. Dev & debug: bullet, letter_opener, annotaterb, rack-mini-profiler, dotenv
11. APIs, admin, charts, flags — quick hits
12. Testing stack (pointer)

---

## 1. Decision table

| Need | Rails default | Reach for a gem when |
|---|---|---|
| Forms | `form_with` + partials | Dozens of uniform CRUD forms → **simple_form** |
| CSS | Plain CSS + Propshaft | Utility-first design system → **tailwindcss-rails** |
| Authentication | `bin/rails g authentication` | Social login only → layer **omniauth** on top; never replace the generator |
| Authorization | Scoping + model predicates (`auth-security.md`) | Role matrix outgrows conditionals → **pundit** / **cancancan** |
| Pagination | — (none built in) | Any real list → **pagy** |
| Filtering/search UI | Scopes + params | Admin-style arbitrary filters → **ransack**; full-text on PG → **pg_search** |
| Jobs | **Solid Queue** | Ops dashboard → **mission_control-jobs**; the backend itself is settled |
| Cron | `config/recurring.yml` (Solid Queue) | (rarely) — whenever/cron only for non-Rails jobs |
| Slugs | `to_param` override | History/aliasing of slugs → **friendly_id** |
| Audit trail | 8.1 `Rails.event` + your own log table | Full model versioning/undo → **paper_trail** |
| Soft delete | An `archived_at` column + scopes | Uniform pattern across many models → **discard** |
| N+1 detection | `strict_loading` | Want dev-log warnings instead of raises → **bullet** |
| Uploads | Active Storage | (stick with Active Storage) |
| JSON APIs | `render json:` / jbuilder | Serializer objects preferred → **blueprinter**/**alba**; OpenAPI docs → **rswag** |
| HTTP client | `Net::HTTP` | Any nontrivial client code → **faraday** |
| Env vars | Credentials (prod) | Per-dev local overrides → **dotenv-rails** (dev/test only) |
| API documentation | — (none built in) | Any consumed JSON API → OpenAPI via **rswag** — `api-documentation.md` |
| View components | Partials + strict locals | Design-system scale, unit-tested views → **ViewComponent** |
| Migration safety | Plain migrations | Deploying against live tables at scale → **strong_migrations** |
| AI / LLM features | — (none built in) | **ruby_llm** — `ai-llm.md` |

## 2. Forms: simple_form

```ruby
gem "simple_form"
# bin/rails generate simple_form:install   (--bootstrap for Bootstrap)
```

```erb
<%= simple_form_for @product do |f| %>
  <%= f.input :name %>
  <%= f.input :price_cents, label: "Price (kobo)", hint: "Stored as integer" %>
  <%= f.association :category %>          <%# select from Category.all %>
  <%= f.input :status, collection: Product.statuses.keys %>
  <%= f.button :submit %>
<% end %>
```

`f.input` infers the control from the column type and renders
label + input + errors + hint in one call. With Tailwind there's no official
preset: teams generate the install then customize
`config/initializers/simple_form.rb` wrappers with Tailwind classes (do this
once, commit it, never fight it per-form). Keep `form_with` for one-off,
heavily custom forms — mixing is fine when each form is internally
consistent.

## 3. CSS: tailwindcss-rails

```bash
rails new myapp --css=tailwind    # or later:
bundle add tailwindcss-rails && bin/rails tailwindcss:install
```

- Uses the **standalone Tailwind CLI** — no Node required; pairs perfectly
  with importmap.
- `bin/dev` (Procfile.dev) runs the server plus `tailwindcss:watch`; source
  lives at `app/assets/tailwind/application.css`, output is compiled and
  digested by Propshaft.
- Tailwind v4: CSS-first configuration (`@theme` in the CSS file) — recent
  installs have no `tailwind.config.js`; older apps still carry one.
- Deploys/CI: `assets:precompile` builds Tailwind automatically; nothing
  extra in the Dockerfile.
- Component libraries on top: daisyUI et al. — with the no-Node setup, vendor
  via the CLI's plugin support or CSS import per that library's docs.

## 4. Authentication: the built-in generator (nothing else)

Rails 8 eliminated the third-party-auth-engine category: `bin/rails g
authentication` generates readable, auditable session-based auth *inside your
codebase* — Session model, `has_secure_password`, reset flow — that you
extend like any other app code (full walkthrough in `auth-security.md`). Need
email confirmation, lockouts, or 2FA? Add a column, a mailer, a `rotp` check —
it's your code, not a DSL to configure. The one legitimate add-on is social
login:

```ruby
gem "omniauth"                          # + a provider gem, e.g. omniauth-google-oauth2
gem "omniauth-rails_csrf_protection"    # required — POST-only request phase
```

Wire the callback to find-or-create the `User` and create the same `Session`
record the generator uses. OmniAuth layers *onto* built-in auth; it never
replaces it.

## 5. Authorization: pundit / cancancan

Graduate from inline checks when rules multiply (see the ladder in
`auth-security.md`).

**Pundit** — one plain-Ruby policy class per model; explicit, scales well:

```ruby
class ProductPolicy < ApplicationPolicy
  def update? = user.admin? || record.store.members.include?(user)
  class Scope < Scope
    def resolve = user.admin? ? scope.all : scope.where(store: user.stores)
  end
end

# controller
def update
  @product = authorize Product.find(params[:id])
  ...
end
def index
  @products = policy_scope(Product)
end
```

Add `rescue_from Pundit::NotAuthorizedError` → redirect with alert, and
`after_action :verify_authorized` in ApplicationController to catch forgotten
checks.

**CanCanCan** — one central `Ability` class of `can :update, Product,
store: { id: user.store_ids }` rules; quicker for simple role matrices,
harder to keep tidy at scale. `authorize! :update, @product`,
`Product.accessible_by(current_ability)`, `load_and_authorize_resource`.
Pick one; both check on the server, views only *hide* (`policy(...).update?`
/ `can? :update, product`).

## 6. Pagination: pagy

Fastest and lightest of the pagination gems; the modern default choice.

```ruby
# Gemfile: gem "pagy"
# ApplicationController: include Pagy::Backend
# ApplicationHelper:    include Pagy::Frontend

def index
  @pagy, @products = pagy(Product.order(:name), limit: 25)
end
```

```erb
<%= render @products %>
<%== pagy_nav(@pagy) %>   <%# note the raw-output %%== %>
```

(kaminari/will_paginate: same job in older codebases — `Product.page(params[:page]).per(25)`; don't migrate working code, just don't start new apps on them.)

## 7. Search & filtering: ransack, pg_search

**ransack** — arbitrary user-driven filters/sorting (admin tables):

```ruby
@q = Product.ransack(params[:q])
@products = @q.result(distinct: true)
```

```erb
<%= search_form_for @q do |f| %>
  <%= f.search_field :name_cont %>          <%# name LIKE %term% %>
  <%= f.search_field :price_cents_gteq %>
<% end %>
<%= sort_link(@q, :name) %>
```

Security-critical: allowlist what's searchable —
`def self.ransackable_attributes(_ = nil) = %w[name price_cents status]` (and
`ransackable_associations`) — required since Ransack 4 precisely so users
can't filter on arbitrary columns.

**pg_search** — real full-text search on PostgreSQL without external infra:
`include PgSearch::Model; pg_search_scope :search_all, against: [:name,
:description], using: { tsearch: { prefix: true } }`. Beyond that (typo
tolerance, facets, huge scale): Meilisearch/Elasticsearch client gems.

## 8. Background jobs: Solid Queue, full stop

Rails 8 eliminated the external-job-backend category: **Solid Queue** is
database-backed (no Redis to operate), runs recurring jobs via
`config/recurring.yml`, has concurrency controls, and gains resumable
Continuations in 8.1 — all covered in `jobs-and-realtime.md`. Keep writing
`ApplicationJob` subclasses and let the adapter stay boring. The one
worthwhile add-on is the first-party ops dashboard:

```ruby
# Gemfile: gem "mission_control-jobs"
# config/routes.rb:
mount MissionControl::Jobs::Engine, at: "/jobs"   # behind an admin constraint
```

Queues, in-flight and failed jobs with backtraces, retry/discard buttons —
mount it behind admin auth like any ops surface.

## 9. Model utilities

- **friendly_id** — slugs with history: `extend FriendlyId; friendly_id
  :title, use: %i[slugged history]`; find with `Product.friendly.find(params[:id])`;
  old slugs 301 to new.
- **paper_trail** — `has_paper_trail` records every change to a `versions`
  table; `product.versions`, `version.reify` to restore. Heavy tables — scope
  to models that truly need audit/undo. (**audited** is the lighter
  append-only alternative: who/what/when per change, no reify. For "who did
  what" telemetry alone, 8.1 `Rails.event` + your own table is lighter
  still.)
- **discard** — soft delete: `include Discard::Model`, `product.discard`,
  default queries via `Product.kept`. Remember `dependent:` callbacks don't
  fire on discard; handle cascades explicitly.
- **aasm** / **state_machines-activerecord** — declared state machines with
  guards/callbacks/events when a plain `enum` + methods stops being enough
  (i.e., transitions have rules). Enum first; state machine when you catch
  yourself writing `can_transition_to?` logic by hand.

## 10. Dev & debug quality-of-life

- **bullet** — flags N+1s and unused eager loads in development
  (`Bullet.enable = true; Bullet.add_footer = true` in an initializer's
  dev block). Complements, not replaces, `strict_loading`.
- **letter_opener** — opens sent mail in a browser tab:
  `config.action_mailer.delivery_method = :letter_opener` (development). The
  built-in alternative is mailer previews at `/rails/mailers`.
- **annotaterb** — writes the schema as comments atop each model/spec/factory
  (`bundle exec annotaterb models`); the maintained successor to the old
  `annotate` gem.
- **rack-mini-profiler** — per-page speed badge with SQL breakdown; add
  `stackprof` for flamegraphs (`?pp=flamegraph`).
- **dotenv-rails** — loads `.env` in dev/test for machine-local settings
  (group it accordingly). Production secrets stay in credentials — see
  `project-setup.md`.
- **debug** gem is already the default debugger (`binding.break`); no pry
  needed unless the team prefers it.

## 11. Quick hits

- **APIs**: `jbuilder` ships in the Gemfile for view-style JSON;
  **blueprinter**/**alba** for serializer objects; **rack-cors** for CORS (see
  `controllers-routing.md`). Documenting the API is its own discipline —
  OpenAPI via **rswag**, covered in `api-documentation.md`.
- **ViewComponent** (GitHub) — Ruby objects for view fragments: isolated,
  unit-testable (`render_inline`), typed initializers, previews. Reach for it
  when a design system outgrows partials-with-strict-locals or views need
  real unit tests; for most apps, disciplined partials are enough — don't run
  both patterns for the same components.
- **strong_migrations** — lints migrations in development and raises on
  operations that lock live tables (bad column type changes, non-concurrent
  indexes on Postgres, backfills in the same transaction), with the safe
  recipe in the error message. Cheap insurance for any team deploying against
  real traffic; add early — retrofitting is noisy.
- **Litestream** — if running SQLite in production (the Rails 8 happy path),
  stream continuous WAL backups to S3-compatible storage for
  point-in-time recovery; run it as a Kamal accessory alongside the app
  (`deployment-kamal.md`).
- **Admin**: **administrate** (Thoughtbot, plain Rails-ish) or **avo**
  (commercial, polished) before hand-rolling; **activeadmin** in many legacy
  apps (brings ransack + its own DSL).
- **Charts**: **chartkick** (`<%= line_chart Order.group_by_day(:created_at).count %>`)
  with **groupdate** — pairs with importmap via its JS.
- **Feature flags**: **flipper** — `Flipper.enabled?(:new_checkout, current_user)`,
  actors/percentage rollouts, `flipper-ui` dashboard.
- **Money**: store integer minor units (`price_cents`) always; **money-rails**
  adds `monetize :price_cents` with currency handling when multi-currency is
  real.
- **HTTP**: **faraday** for API clients (middleware, retries, instrumentation
  hooks) — wrap third-party APIs in one class per service so WebMock/VCR
  target a seam (`testing.md` §9).
- **AI/LLM**: **ruby_llm** is the standard — chat, tools, structured output,
  embeddings, `acts_as_chat` persistence; full treatment in `ai-llm.md`.

## 12. Testing stack

rspec-rails, factory_bot_rails, faker, capybara,
selenium-webdriver, simplecov, webmock, vcr, rubocop-rspec — the full setup,
configuration, and idioms live in `references/testing.md`. That file is this
skill's testing doctrine; don't duplicate it here.

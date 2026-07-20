# Project Setup, Configuration, and the Development Workflow

## Contents
1. Creating apps (`rails new` recipes)
2. Generated layout — what lives where
3. Configuration layers and environment defaults
4. Credentials and secrets
5. Databases and `database.yml` (multi-database Solid setup)
6. Daily workflow: bin scripts, generators, console, runner
7. Upgrading and 8.0 → 8.1 gotchas

---

## 1. Creating apps

```bash
rails new shop --skip-test                        # SQLite, importmap, Hotwire, Solid stack, Kamal — RSpec added next
rails new shop --database=postgresql              # client-server DB (also: mysql, trilogy, mariadb-mysql)
rails new shop --css=tailwind                     # tailwindcss-rails (standalone binary, no Node)
rails new shop --javascript=esbuild               # only when npm packages that need bundling are required
rails new api --api                               # API-only (no views/assets/Hotwire)
rails new shop --devcontainer                     # VS Code / Codespaces dev container
```

Useful skips: `--skip-kamal`, `--skip-docker`, `--skip-solid`, `--skip-ci`,
`--skip-hotwire`, `--minimal` (barebones). Don't skip things speculatively —
the defaults are the point, with one deliberate exception below. Check
`rails new --help` before inventing flags.

**Always pass `--skip-test`.** This skill's suite is RSpec (`testing.md`), so
the framework's default test scaffolding must never be generated — no
redundant `test/` directory and no dual-suite confusion when `rspec:install`
runs. Immediately after creation, wire generators so every scaffold emits
specs and factories instead:

```ruby
# config/application.rb
config.generators do |g|
  g.test_framework :rspec, fixture: false
  g.fixture_replacement :factory_bot, dir: "spec/factories"
  g.system_tests nil
end
```

After generation: `bin/setup` (installs gems, prepares DB, starts server —
`bin/setup --skip-server` to prep only). Day-to-day server: `bin/dev` (runs
`Procfile.dev` when there are watchers, e.g. Tailwind; otherwise just the
Rails server).

## 2. Generated layout — what lives where

```
app/
  assets/stylesheets/      # CSS, served by Propshaft (digest-stamped, no build)
  controllers/             #   + concerns/
  helpers/                 # view helpers (modules, auto-included in all views)
  javascript/
    application.js         # entrypoint pinned by importmap
    controllers/           # Stimulus controllers (auto-registered)
  jobs/  mailers/  models/ #   models/ also holds POROs and concerns/
  views/
    layouts/application.html.erb
    pwa/                   # manifest.json.erb, service-worker.js (routes commented out)
bin/       # setup, dev, rails, rubocop, brakeman, importmap, jobs, ci (8.1), thrust, kamal, docker-entrypoint
config/
  application.rb           # config.load_defaults 8.1; app-wide settings
  environments/{development,test,production}.rb
  initializers/            # runs at boot; one concern per file
  routes.rb  database.yml  puma.rb
  cache.yml  queue.yml  recurring.yml  cable.yml   # Solid stack
  deploy.yml               # Kamal
  ci.rb                    # local CI pipeline (8.1)
  importmap.rb
  credentials.yml.enc  master.key (gitignored)
db/         # migrate/, schema.rb, seeds.rb (+ cache_schema.rb, queue_schema.rb, cable_schema.rb)
lib/tasks/  # rake tasks; lib/ is NOT autoloaded by default
public/     # static files served as-is; error pages; robots.txt
script/     # one-off/throwaway scripts (bin/rails runner script/foo.rb)
storage/    # Active Storage disk service + SQLite databases (gitignored)
test/       # models/, controllers/, system/, integration/, fixtures/, mailers/, jobs/, helpers/
vendor/javascript/         # importmap-downloaded packages
Dockerfile  .dockerignore  .kamal/secrets  .github/workflows/ci.yml
```

Autoloading (Zeitwerk): everything under `app/*` is autoloaded and
eager-loaded in production; file path must match constant
(`app/models/order_item.rb` → `OrderItem`). Code in `lib/` needs
`config.autoload_lib(ignore: %w[assets tasks])` (present by default in new
apps). Verify with `bin/rails zeitwerk:check`.

## 3. Configuration layers

Precedence: `config/application.rb` → `config/environments/*.rb` (override) →
initializers. App-specific settings go in `config.x`
(`config.x.payment.retries = 3`) or better, `config_for`:

```ruby
# config/application.rb
config.payment = config_for(:payment)   # reads config/payment.yml, env-keyed
```

Key defaults worth knowing (new 8.1 app):

- **development**: eager_load off; caching toggled by `bin/rails dev:cache`
  (`:memory_store` when on); Active Job uses the `:async` adapter unless you
  run Solid Queue; `config.hosts` guards against DNS rebinding — append
  allowed hostnames when using tunnels/containers; verbose query logs +
  verbose redirect logs (8.1) on; mailer deliveries not sent
  (`:test`-like — check `letter` via mailer previews, §mail reference).
- **test**: eager_load off, cache `:null_store`, deliveries collected in
  `ActionMailer::Base.deliveries`.
- **production**: `config.force_ssl = true` + `config.assume_ssl = true`
  (Thruster/kamal-proxy terminates TLS); log to STDOUT, tagged with
  `request_id`; `/up` health checks silenced; cache store
  `:solid_cache_store`; `active_job.queue_adapter = :solid_queue` connecting
  to the `queue` database; `dump_schema_after_migration = false`;
  `attributes_for_inspect = [:id]` (don't leak records in logs). SMTP left
  for you to configure. Set `config.action_mailer.default_url_options` and
  (optionally) `config.hosts`/`host_authorization`.

Boot-time env vars still matter for infrastructure: `RAILS_ENV`,
`RAILS_MASTER_KEY`, `WEB_CONCURRENCY` (Puma workers), `RAILS_MAX_THREADS`,
`JOB_CONCURRENCY`, `SOLID_QUEUE_IN_PUMA`, `PORT`.

## 4. Credentials and secrets

Encrypted credentials are the Rails-way secret store — commit
`credentials.yml.enc`, never `master.key`.

```bash
bin/rails credentials:edit                       # uses $EDITOR; VISUAL="code --wait" works
bin/rails credentials:edit --environment production   # per-env file + key (optional pattern)
bin/rails credentials:fetch aws.secret_access_key     # 8.1: plain-text to stdout, shell-friendly
bin/rails credentials:diff --enroll                    # readable git diffs
```

```ruby
Rails.application.credentials.secret_key_base
Rails.application.credentials.dig(:aws, :access_key_id)
```

Production needs the key via `RAILS_MASTER_KEY` (Kamal wires this from
`.kamal/secrets`). Use ENV directly only for infrastructure-level values
(`DATABASE_URL`, concurrency knobs), not application secrets.

## 5. Databases and `database.yml`

Rails 8 splits production persistence into four logical databases so cache
churn and job queues never bloat your primary. SQLite default:

```yaml
production:
  primary:
    <<: *default
    database: storage/production.sqlite3
  cache:
    <<: *default
    database: storage/production_cache.sqlite3
    migrations_paths: db/cache_migrate
  queue:
    <<: *default
    database: storage/production_queue.sqlite3
    migrations_paths: db/queue_migrate
  cable:
    <<: *default
    database: storage/production_cable.sqlite3
    migrations_paths: db/cable_migrate
```

PostgreSQL apps get the same shape with `database: shop_production_cache`
etc. — keep it; `bin/rails db:prepare` creates/migrates/loads all of them
(including the `*_schema.rb` files for the Solid databases) and is what the
Docker entrypoint runs on boot. SQLite in production is a first-class,
supported choice in Rails 8 (WAL mode, IMMEDIATE transactions tuned by
default) for single-server apps; choose PostgreSQL when you need multiple app
servers, horizontal scaling, or advanced SQL.

Multi-primary/replica setups: see the models reference (§multi-DB) —
`connects_to`, `migrations_paths`, automatic role switching.

## 6. Daily workflow

```bash
bin/rails g model Product name:string 'price:decimal{10,2}' supplier:references
bin/rails g migration AddStatusToOrders status:integer
bin/rails g controller Products index show      # or: g scaffold Product name:string
bin/rails g job ProcessPayment
bin/rails g mailer Order receipt
bin/rails g authentication                       # full session auth (see auth-security.md)
bin/rails destroy model Product                  # undo a generator
bin/rails db:migrate | db:rollback | db:prepare | db:seed | db:seed:replant
bin/rails console        # sandbox: bin/rails console --sandbox (rolls back on exit)
bin/rails runner 'Order.stuck.find_each(&:release!)'
bin/rails routes -g product                      # grep routes
bin/rails stats | notes | about | dbconsole
bin/rails dev:cache                              # toggle caching in development
```

Console niceties: `app.products_path`, `helper.number_to_currency(10)`,
`reload!`. Generators respect `config.generators` (e.g.
`g.helper false; g.jbuilder false` to slim scaffold output).

Debugging: the `debug` gem is bundled — drop `debugger` in code; server must
run in the foreground. `Rails.logger.debug`, `rails console`, and
`config.log_level` round it out. Better Errors-style middleware is not
default; the built-in error page + web-console is.

## 7. Upgrading and 8.0 → 8.1 gotchas

Process: bump the gem one minor at a time → `bundle update rails` →
`bin/rails app:update` (interactively merge config) → keep
`config.load_defaults <old>` plus the generated
`new_framework_defaults_8_1.rb`, flipping flags one by one with green tests →
finally set `load_defaults 8.1` and delete the file.

8.1-specific watch items:

- `schema.rb` columns are now **alphabetized** — the first post-upgrade
  migration rewrites column order. Commit it; don't hand-edit back.
- Order-dependent finders (`.first`, `.last`, `#second`…) on relations with
  no inferable order are deprecated → add explicit `.order(:id)` (or rely on
  the primary key where Rails can).
- `signed_id_verifier_secret` deprecated → `Rails.application.message_verifiers`.
- `String#mb_chars`, `ActiveSupport::Configurable` deprecated;
  `Benchmark.ms` removed (use the `benchmark` gem).
- Active Storage `:azure` service **removed** — migrate to S3-compatible or
  another service.
- `update_all` with `WITH` / `DISTINCT` deprecated; `insert_all`/`upsert_all`
  through associations with unpersisted records deprecated.
- New apps log redirect sources verbosely in development; add
  `config.action_dispatch.verbose_redirect_logs = true` to older apps if
  wanted.

When asked to upgrade a real app, read
`https://guides.rubyonrails.org/upgrading_ruby_on_rails.html` for the exact
pair of versions involved rather than relying on memory.

# Observability: Instrumentation, Events, Errors, Logs (Rails 8.1)

Four channels, four jobs. Pick the right one before writing telemetry code:

| Channel | Shape | Use for |
|---|---|---|
| `ActiveSupport::Notifications` | Timed spans with payloads | Durations, APM-style tracing, framework internals |
| `Rails.event` (new in 8.1) | Discrete structured facts | Business events: `order.placed`, `import.completed` |
| `Rails.error` | Exceptions + context | Rescued-but-reportable failures |
| `Rails.logger` | Human text lines | Narrative debugging |

## Contents
1. Active Support Instrumentation — subscribing
2. Framework hook catalog (the ones that matter)
3. Instrumenting your own code
4. Structured Event Reporting — `Rails.event` (8.1)
5. Error reporting — `Rails.error`
6. Logging: tags, levels, health-check silence
7. Wiring up APMs / OpenTelemetry (self-hosted: Rails Pulse)

---

## 1. Active Support Instrumentation — subscribing

Everything significant the framework does fires a named event. Subscribe with
a one-argument block to get an `Event` object:

```ruby
# config/initializers/instrumentation.rb
ActiveSupport::Notifications.subscribe("process_action.action_controller") do |event|
  event.name         # "process_action.action_controller"
  event.duration     # ms (computed from monotonic clocks)
  event.allocations  # object allocations during the span
  event.payload      # hash — see catalog below
end
```

Variants: the 5-arg block form `(name, started, finished, id, payload)`
(prefer `monotonic_subscribe` if you compute durations from those
timestamps); regex subscription for whole namespaces
(`subscribe(/action_controller/)`); and temporary subscription around a block:

```ruby
ActiveSupport::Notifications.subscribed(callback, "sql.active_record") do
  # only instrumented inside this block — great in tests
end
```

Subscribers run inline on the hot path — keep them O(1): increment a counter,
push to a buffer/queue; never do IO-heavy work synchronously.

## 2. Framework hook catalog (the ones that matter)

Payload keys shown are the ones you'll actually use.

| Event | Key payload | Typical use |
|---|---|---|
| `process_action.action_controller` | `:controller, :action, :params, :format, :method, :path, :status, :view_runtime, :db_runtime` | Request timing/error-rate metrics |
| `start_processing.action_controller` | `:controller, :action, :params, :path` | Set per-request context early |
| `redirect_to.action_controller` | `:status, :location, :request` | Redirect auditing |
| `halted_callback.action_controller` | `:filter` | Debug "why did my before_action stop this?" |
| `unpermitted_parameters.action_controller` | `:keys, :context` | Catch params.expect drift in production |
| `rate_limit.action_controller` | `:count, :to, :within, :by, :name` | Alert on abuse |
| `send_file/send_stream.action_controller` | `:path` / `:filename, :type` | Download tracking |
| `read_fragment/write_fragment.action_controller` | `:key` | Fragment-cache behavior |
| `redirect.action_dispatch` | `:status, :location, :source_location` | Route-level redirects (8.1 verbose dev logs use this) |
| `sql.active_record` | `:sql, :name, :binds, :cached, :connection` | Query counting, slow-query log (skip `SCHEMA`/`TRANSACTION` names) |
| `instantiation.active_record` | `:record_count, :class_name` | "This action built 5,000 AR objects" |
| `strict_loading_violation.active_record` | `:owner, :reflection` | N+1 telemetry when strict_loading is `:log` |
| `transaction.active_record` | `:connection, :outcome` (commit/rollback) | Rollback-rate monitoring |
| `render_template/render_partial.action_view` | `:identifier, :layout` / `:identifier, :cache_hit` | View timing, cache hit ratios |
| `render_collection.action_view` | `:identifier, :count, :cache_hits` | Collection-cache effectiveness |
| `deliver.action_mailer` | `:mailer, :message_id, :subject, :to` | Mail volume/failures |
| `enqueue.active_job` / `perform.active_job` | `:job, :adapter` (+ `:db_runtime` on perform) | Queue latency = perform start − enqueue |
| `cache_read/cache_write/cache_fetch_hit.active_support` | `:key, :store, :hit, :super_operation` | Hit-rate dashboards |
| `perform_action.action_cable` / `broadcast.action_cable` | `:channel_class, :action` / `:broadcasting` | Realtime volume |
| `process.action_mailbox` | `:mailbox, :inbound_email` | Inbound mail pipeline |
| `service_upload.active_storage` (and download/delete) | `:key, :service, :checksum` | Storage ops |
| `deprecation.rails` | `:message, :callstack, :gem_name` | Fail CI on new deprecations |

Exception convention: any hook's payload gains `:exception` (`[class_name,
message]`) and `:exception_object` when the instrumented block raised —
check for it in generic subscribers.

Worked example — a slow-query logger:

```ruby
ActiveSupport::Notifications.subscribe("sql.active_record") do |event|
  next if event.payload[:name].in?(["SCHEMA", "TRANSACTION"]) || event.payload[:cached]
  if event.duration > 100
    Rails.logger.warn("[slow-sql] #{event.duration.round(1)}ms #{event.payload[:sql].truncate(200)}")
  end
end
```

For log-oriented subscribers, subclass `ActiveSupport::LogSubscriber` and
`attach_to :active_record` — it gives you level helpers and color, and it's
how Rails' own log lines are produced.

## 3. Instrumenting your own code

```ruby
def import!
  ActiveSupport::Notifications.instrument("import.pricing", feed: name, rows: rows.size) do |payload|
    result = do_import
    payload[:imported] = result.count   # enrich payload from inside
    result
  end
end
```

Name format is `event.library` (dot-namespaced, your app/domain as suffix).
The block's exceptions propagate *and* land in the payload. Instrument spans
you'll want on a dashboard; for one-off timing in dev use
`Rails.benchmark("expensive thing") { ... }`.

## 4. Structured Event Reporting — `Rails.event` (8.1)

`Rails.logger` is for humans; `Rails.event` produces machine-consumable
events for pipelines, metrics, and audit trails.

```ruby
Rails.event.notify("user.signup", user_id: 123, email: "user@example.com")

Rails.event.tagged("graphql") do          # tags: { graphql: true } on inner events
  Rails.event.notify("user.signup", user_id: 123)
end

# e.g. in a before_action — attached to all subsequent events this request:
Rails.event.set_context(request_id: request.request_id, shop_id: Current.shop&.id)
```

Events flow to subscribers you register; each implements `#emit(event)`
receiving a hash with `:name`, `:payload`, `:tags`, `:context`, and
`:source_location`:

```ruby
# config/initializers/events.rb
class JsonLogSubscriber
  def emit(event)
    Rails.logger.info({
      event: event[:name], **event[:payload], tags: event[:tags],
      at: "#{event[:source_location][:filepath]}:#{event[:source_location][:lineno]}"
    }.to_json)
  end
end

Rails.application.config.after_initialize do
  Rails.event.subscribe(JsonLogSubscriber.new)
end
```

Use events for **domain facts** you'd count, chart, or audit
(`order.placed`, `payment.failed`, `import.completed`); keep payloads to IDs
and scalars, not records. Rule of thumb vs §1: **Notifications** for
durations/spans, **Rails.event** for discrete business facts.

## 5. Error reporting — `Rails.error`

The unified interface error-tracking services (Sentry, Honeybadger,
AppSignal) subscribe to — report through it, never a vendor API directly.

```ruby
# Swallow after reporting (returns fallback) — non-critical paths:
trending = Rails.error.handle(fallback: -> { [] }) { TrendingService.fetch }

# Report and re-raise — caller must still see the failure:
Rails.error.record(context: { import_id: import.id }) { import.process! }

# Report an already-rescued exception — inside a rescue you already have:
begin
  order.sync_with_third_party!
rescue ThirdParty::Error => e
  Rails.error.report(e, severity: :warning, context: { order_id: order.id })
end

# Global context (e.g. in a before_action):
Rails.error.set_context(user_id: Current.user&.id, section: "checkout")
```

Unhandled exceptions in requests and jobs are reported automatically — these
APIs exist for errors *you* rescue but still want visibility on. A custom
subscriber is a class with `report(error, handled:, severity:, context:,
source: nil)` registered via `Rails.error.subscribe` — handy in test to
assert reports, or to fan out to a Teams/Slack webhook.

## 6. Logging: tags, levels, health-check silence

- Production logs go to STDOUT tagged with `:request_id` (generated default:
  `config.log_tags = [:request_id]`) — correlate all lines of one request;
  add your own lambda tags (`->(req) { req.subdomain }`).
- Ad-hoc scoping: `Rails.logger.tagged("Imports") { logger.info "..." }`.
- Level via `RAILS_LOG_LEVEL` env (`config.log_level = ENV.fetch("RAILS_LOG_LEVEL", "info")` is generated).
- `config.silence_healthcheck_path = "/up"` (generated) keeps kamal-proxy's
  probes out of the logs — set the same for any other probe path.
- One-format-per-app: if you adopt JSON logs (via a `Rails.event` subscriber
  or a formatter), convert everything; mixed text/JSON streams are the worst
  of both.

## 7. Wiring up APMs / OpenTelemetry

Sentry (`sentry-ruby` + `sentry-rails`), AppSignal, Skylight, Datadog, New
Relic, Honeybadger all auto-subscribe to the §2 hooks and the `Rails.error`
reporter — installation is gem + credentials + initializer; **don't**
hand-roll subscribers that duplicate what the agent already collects (double
overhead). Self-hosted, Solid-style alternatives exist when data must stay
in-house: **solid_errors** (database-backed error tracker riding
`Rails.error`, with its own dashboard — no SaaS) and the community
**solid_telemetry** (OpenTelemetry traces stored in your own database). For
vendor-neutral tracing, `opentelemetry-sdk` +
`opentelemetry-instrumentation-rails` maps the same hooks to OTel spans
exportable anywhere. Your custom `instrument`/`Rails.event` calls then ride
along as first-class spans/events in whichever backend the app uses.

### Self-hosted performance monitoring — Rails Pulse

When the app needs request, query and job performance (P95 per route, SQL
grouped by normalised shape, N+1 detection in production, deploy markers)
and the data must stay in your own database, **rails_pulse** (MIT, 0.4.x;
tested on Rails 7.2, 8.0 and 8.1) is the self-hosted APM. It captures through
a Rack middleware and §2 subscribers, and writes off the request thread
through a bounded queue that drops, rather than blocks, when full. It is not
a replacement for **mission_control-jobs** (`ecosystem-gems.md`): Pulse
observes job speed and failure rate; Mission Control operates the queue
(retry, discard, pause). Run both. Do **not** run Pulse beside a hosted APM
from the list above — two collectors on the same hooks is the double
overhead this section warns against.

**When to adopt:** the app serves real users in production and has no APM.
Before launch there is no traffic to measure — Bullet and the log cover
development.

Install into its own database so the host's primary never carries the
tables. The generator writes `db/rails_pulse_schema.rb` and the initializer.
It only *prints* the database wiring and does none of it, so those three
commands alone create nothing:

```bash
bundle add rails_pulse
bin/rails generate rails_pulse:install --database=separate
```

Add a `rails_pulse:` database to **every** environment in
`config/database.yml`. Rails treats an environment as multi-database only when
every key under it is a database entry, so a flat block (the usual
`development:` and `test:`) must move under `primary:` first. Skip that and the
install fails one of two ways. With `connects_to` set, `db:prepare` aborts with
`ActiveRecord::AdapterNotSpecified`. Without it, `db:prepare` prints
*"Successfully created tables"* and writes all ten Pulse tables into the
**primary**. Production is already nested in Rails 8 (`primary`, `cache`,
`queue`, `cable`), so it only needs the sibling. For PostgreSQL or MySQL,
`database:` is a database name, not a file path:

```yaml
development:
  primary:
    <<: *default
    database: storage/development.sqlite3
  rails_pulse:
    <<: *default
    database: storage/development_rails_pulse.sqlite3
    migrations_paths: db/rails_pulse_migrate
    schema_dump: false
```

Then connect it by uncommenting `connects_to` in the initializer the generator
wrote (below). The first install runs in this order. The upgrade generator
only copies this version's migrations once the Pulse tables exist, and
`rails_pulse:status` stays at 1 until they are copied and run:

```bash
bin/rails db:prepare
RAILS_ENV=test bin/rails db:prepare
bin/rails generate rails_pulse:upgrade
bin/rails db:migrate:rails_pulse
RAILS_ENV=test bin/rails db:migrate:rails_pulse
bin/rails runner 'p RailsPulse::ApplicationRecord.connection_db_config.name'   # must print "rails_pulse", not "primary"
```

Restart the server afterwards. **After the first install, an empty Pulse
database needs its schema loaded before `db:prepare`, and a populated one must
never have it loaded.** The two cases fail in different ways:

- **An empty database.** With the migrations copied, `db:prepare` runs them
  before the gem's schema-load hook and aborts with *"Could not find table
  'rails_pulse_operations'"*. That is every fresh clone's `bin/setup`, every CI
  run, and the first deploy, whose `bin/docker-entrypoint` runs `db:prepare` on
  boot.
- **A populated database.** `db:schema:load_rails_pulse` marks *every* copied
  migration as applied without running it, so a pending one is silently skipped
  while `rails_pulse:status` still exits 0.

So guard the load on the database being empty, and do it for **every**
environment before any `db:prepare` runs. In development that means test too,
because `db:prepare` in development also prepares test and aborts on its empty
Pulse database. `bin/setup` loads development and test, CI loads test, and the
entrypoint loads production:

```bash
for env in development test; do   # CI: test only. bin/docker-entrypoint: production only.
  RAILS_ENV=$env bin/rails runner 'exit(RailsPulse::ApplicationRecord.connection.table_exists?(:rails_pulse_routes) ? 0 : 1)' ||
    RAILS_ENV=$env bin/rails db:schema:load_rails_pulse
done
bin/rails db:prepare
```

On a populated database the guard skips the load, and `db:prepare` applies a
pending Pulse migration normally. Measured on SQLite. On PostgreSQL or MySQL
the database must exist before the load (`bin/rails db:create`), which was not
run here. With an empty test Pulse database, `/rails_pulse` answers 503 in
tests and tracking pauses without a word.

(A single-database install omits `--database=separate`, the `database.yml`
entry and `connects_to`, and runs `bin/rails db:migrate`.) Mount it and gate it
on the app's own admin check:

```ruby
# config/routes.rb
mount RailsPulse::Engine => "/rails_pulse"

# config/initializers/rails_pulse.rb
RailsPulse.configure do |config|
  config.connects_to = { database: { writing: :rails_pulse, reading: :rails_pulse } } # separate database only
  config.authorize = ->(controller) { controller.current_user&.admin? }
end
```

A falsy result is a 403. With no `authorize` configured, outside development
and test it falls back to HTTP Basic against `RAILS_PULSE_USERNAME` /
`RAILS_PULSE_PASSWORD`, and refuses everyone when the password is unset.
The host schedules the rollup and the retention jobs; with Solid Queue:

```yaml
# config/recurring.yml
production:
  rails_pulse_summary:
    class: RailsPulse::SummaryJob
    schedule: "5 * * * *"
  rails_pulse_cleanup:
    class: RailsPulse::CleanupJob
    schedule: "0 1 * * *"
```

**The outcome is verified, not assumed:** `bin/rails rails_pulse:status`
exits 0 (it exits 1 while a migration, backfill or initializer still needs
action), and a signed-out request to `/rails_pulse` in production is refused.

It is pre-1.0 and upgrades can carry data steps: 0.3 → 0.4 required a backup
first, then `bin/rails generate rails_pulse:upgrade`, the migration
(`bin/rails db:migrate:rails_pulse` for the separate database), and
`bin/rails rails_pulse:migrate_routes`. For that upgrade upstream warns
(`CHANGELOG.md`, 0.4.0) to **restart every process together, not as a rolling
deploy**: *"A 0.3.x process left running against the migrated schema stops
tracking and 500s on the routes page."* On a separate database it adds: *"Do
not run `db:setup` / `db:prepare` as a substitute for `db:migrate:rails_pulse`."*
Both warnings are stated for 0.4.0, not as general rules. On 0.4.1 the
entrypoint's `db:prepare` applies a pending Pulse migration on boot. An upgrade
whose CHANGELOG says otherwise, as 0.3 → 0.4 did, runs
`bin/rails db:migrate:rails_pulse` as a step of the release itself, before the
new version boots. Read its CHANGELOG
before every `bundle update rails_pulse`, and finish with `rails_pulse:status`.

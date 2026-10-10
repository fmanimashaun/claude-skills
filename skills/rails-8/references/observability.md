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
7. Wiring up APMs / OpenTelemetry (self-hosted: Rails Pulse, or an in-house OpenTelemetry store)

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

Some unhandled exceptions in requests and jobs are reported automatically, and
some are not (the next subsection) — these APIs exist for errors *you* rescue but
still want visibility on. A custom
subscriber is a class with `report(error, handled:, severity:, context:,
source: nil)` registered via `Rails.error.subscribe` — handy in test to
assert reports, or to fan out to a Teams/Slack webhook.

### What is reported automatically, and what a subscriber receives (Rails 8.1.4)

Read from the installed `actionpack`, `activejob` and `activesupport` 8.1.4;
earlier Rails versions were not checked.

- **A request exception is reported only in some cases.** `ActionDispatch::Executor`
  reports it (`handled: false`, `source: "application.action_dispatch"`) *after*
  `ShowExceptions` has rendered the error page, and only when the exception has no
  `rescue_responses` entry (`ShowExceptions` sets `action_dispatch.report_exception`
  to `!wrapper.rescue_response?`). So a 404 (`RecordNotFound`) or 422
  (`InvalidAuthenticityToken`) is never reported, and a generic 500 is reported only
  when `show_detailed_exceptions` is false: in development and test `DebugExceptions`
  renders its own page first and nothing is reported. A request spec of a subscriber
  must set `env_config["action_dispatch.show_detailed_exceptions"] = false`.
- **The failing request's path and verb are in the env.** `ShowExceptions` stores
  them as `action_dispatch.original_path` and `action_dispatch.original_request_method`
  before it rewrites the request to `GET /500`. When the exceptions app is a routed
  controller, `ActiveSupport::ExecutionContext[:controller]` is that controller, not
  the one that failed.
- **Job retries and discards are not reported by default.** `retry_on` reports each
  retried attempt only with `report: true`; when attempts run out, with no block the
  error is re-raised (and the job execution wrapper reports it), with a block it is
  swallowed and only `retry_stopped.active_job` fires. `discard_on` reports only with
  `report: true`. The `enqueue_retry`, `retry_stopped` and `discard` events
  (`.active_job`) carry the job and `error:` in the payload; a tracker that must see
  retries subscribes to them as well and de-duplicates on the exception object.
- **The `context:` a subscriber receives holds live objects.** `Rails.error.report`
  merges `ActiveSupport::ExecutionContext.to_h` (the `:controller` and `:job`
  instances), and `ParameterFilter` cannot see inside an object. A subscriber that
  stores `context` as it comes can store a job's arguments: copy named fields only.
- **`error.message` can carry personal data.** A wrapped driver error such as
  `ActiveRecord::RecordNotUnique` passes through the database's detail text
  (PostgreSQL adds the failing key or row). `RecordInvalid` messages name the
  attribute and normally not the value, unless a custom message uses `%{value}`.
  Scrub or drop the message before an error store keeps it, and test the scrubber
  with fixtures.

Rails 8.1+ also has `Rails.error.add_middleware(callable)`, which can modify
the error context before any subscriber sees it (`ActiveSupport::ErrorReporter`,
new in 8.1.0, so absent on 8.0 and earlier): the callable receives the report's
parameters and returns the context hash to use, e.g. to merge in a tenant id.
Check the middleware's exact signature in the Rails source for your version;
the 8.1 guide does not document it.

## 6. Logging: tags, levels, health-check silence

- Production logs go to STDOUT tagged with `:request_id` (generated default:
  `config.log_tags = [:request_id]`) — correlate all lines of one request;
  add your own lambda tags (`->(req) { req.subdomain }`).
- Ad-hoc scoping: `Rails.logger.tagged("Imports") { logger.info "..." }`.
- Level via `RAILS_LOG_LEVEL` env (`config.log_level = ENV.fetch("RAILS_LOG_LEVEL", "info")` is generated).
- `config.silence_healthcheck_path = "/up"` (generated) keeps kamal-proxy's
  probes out of the logs — set the same for any other probe path.
- `config.active_record.query_log_tags_enabled = true` (SQL comment tags for
  slow-query attribution) also **turns prepared statements off app-wide** in
  Rails 8.0 and 8.1 (the Rails debugging guide says so, and `ActiveRecord.disable_prepared_statements`
  is set in the railtie): every query is planned each time. Turn it on knowing
  that cost, not as a free log tag.
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
Pulse database. None of the generated scripts do this. Add the loop before
their `db:prepare`: to `bin/setup` (development and test), to CI (test), and
to `bin/docker-entrypoint` (production):

```bash
for env in development test; do   # CI: test only. bin/docker-entrypoint: production only.
  rc=0
  RAILS_ENV=$env bin/rails runner '
    exit(RailsPulse::ApplicationRecord.connection.tables.grep(/\Arails_pulse_/).empty? ? 3 : 0)' || rc=$?
  if [ "$rc" -eq 3 ]; then
    RAILS_ENV=$env bin/rails db:schema:load_rails_pulse   # no Pulse table at all: load the schema
  elif [ "$rc" -ne 0 ]; then
    echo "rails_pulse ($env): the emptiness check itself failed (exit $rc). Not loading." >&2
    exit "$rc"
  fi
done
bin/rails db:prepare
```

**The load runs only on a Pulse database that has no `rails_pulse_` table at
all.** The load does two things: it creates the tables, and it records every
copied migration as applied. On a database that already has Pulse tables, the
second half is the silent skip above.

On every other database the guard skips the load, and `db:prepare` applies
pending Pulse migrations normally. That includes a populated one whose upgrade
adds a table. The gem's own `db:prepare` hook calls the load as well, and it
is a no-op there. The check does not depend on the table names.

The cases that fail do so loudly:

- **An interrupted first load** leaves some tables and no migration records. It
  passes the check. `db:prepare` then either finishes the schema (when the load
  got as far as `rails_pulse_operations`), or aborts with *"Could not find table
  'rails_pulse_operations'"*. `rails_pulse:status` exits 0 only when the schema
  was finished. Repair the abort by deleting that environment's Pulse database
  and running again.
- **A non-gem table whose name starts with `rails_pulse_`** also passes the
  check, and `db:prepare` aborts the same way. The Pulse database should hold
  only the gem's tables; deleting it to repair would delete that table too.
- **If the check itself fails**, the loop stops before loading, and names the
  environment.

The check reads the Pulse database only because `connects_to` is set. Without
it, `RailsPulse::ApplicationRecord` uses the primary, and the check would test
the primary instead.

Measured on SQLite, on Rails 8.0.5.1 and 8.1.4, in development, test and
production. On PostgreSQL or MySQL the databases must exist before the load
(`bin/rails db:create`), which was not run here. With an empty test Pulse
database, `/rails_pulse` answers 503 in tests and tracking pauses without a word.

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


### An in-house OpenTelemetry store (when the data stays in your database and Pulse is not the choice)

One defensible design, built and measured in a production Rails 8.1.4 app (Ruby
4.0.6; opentelemetry-sdk 1.13.1, api 1.11.1; instrumentation: rails 0.42.0,
action_pack 0.18.1, rack 0.31.2, pg 0.37.0, net_http 0.29.2). Each fact below was
checked against those gem sources or the official docs; what is a design choice
rather than a fact says so. No exporter is installed and nothing leaves the server:
spans are folded in process into aggregates and written to the app's own database.

**Capture**

- **The Rack instrumentation records the query string, and cannot be told not to.**
  The server span carries it as `url.query` (stable semantic conventions), or as
  `http.target` including `?query` under the deprecated `http/dup` and `old` modes;
  `url_quantization` only affects the span *name*. If a query can hold personal data
  (`?q=…`), drop or redact it before spans leave the process. An attribute
  **allow-list** wrapper around the exporter or processor (an unlisted key is dropped,
  so a library upgrade that records something new records nothing until it is listed)
  is one safe design, not the only one.
- **Install the Action Pack instrumentation, and do not insert the middleware
  yourself.** `c.use "OpenTelemetry::Instrumentation::ActionPack"` installs the Rack
  instrumentation and its railtie inserts the middleware at position 0; inserting it
  again by hand gives a second entry. Guard it with a spec that asserts exactly one
  middleware entry carrying the OpenTelemetry handler.
- **`c.use "OpenTelemetry::Instrumentation::Rails"` installs nothing by itself**
  (`install { true }`). Use `c.use_all`, or `c.use` each of ActionPack, ActionView,
  ActiveSupport, ActiveRecord and ActiveJob. A request span needs ActionPack.
- **The PG instrumentation traces every query, and a prepared statement is two
  spans.** PREPARE and EXECUTE are separate spans carrying the obfuscated statement
  (with `db_statement: :obfuscate`, literals become `?` and `$1` becomes `$?`);
  there is no `SCHEMA` name to filter on, so filter on `db.operation`. Schema
  lookups on the `pg_` catalog tables appear in the stream too (observed, not
  read from source). Scrub the statement again before using it as a display name.
- **Span ids are drawn with `Random.bytes`,** the default generator that `srand`
  seeds, so every span moves a seeded sequence and a spec that fixes a seed and runs a
  query is no longer deterministic. Give the SDK its own id generator (any object
  responding to `generate_trace_id` and `generate_span_id`, built on
  `Random.urandom`) through `OpenTelemetry::SDK.configure`.
- **An exception inside an exporter or processor never fails anything.** The SDK
  catches it and calls `OpenTelemetry.handle_error`: `SimpleSpanProcessor` logs
  `unexpected error in span.on_finish`, `BatchSpanProcessor` returns FAILURE and
  counts `otel.bsp.error`. A custom exporter's bug looks like missing spans, so unit
  test the exporter by calling it directly.

**Specs for spans**

- WebMock replaces `Net::HTTP` with a subclass that never calls the patched
  `request` for a stubbed call, so a stubbed request has no client span; allow a real
  loopback connection to assert on one.
- `start_span(start_timestamp:)`, `finish(end_timestamp:)` and `add_event(timestamp:)`
  take a `Time` or a number of **seconds** (the SDK multiplies by 1e9), never
  nanoseconds.
- From Ruby 4.0 `benchmark` is a bundled gem, not a default gem: a script run under
  Bundler (`bin/rails runner`) needs it in the Gemfile.
- Code that an initializer needs must not sit in an autoloaded `lib/`: use
  `config.autoload_lib_once`, or `require` it and keep it out of autoloading with
  `autoload_lib(ignore:)` (Rails autoloading guide).

**Store and read side (design choices)**

- Put the store on a **separate database** with its own migrations
  (`migrations_paths: db/observability_migrate` and a `schema_dump` file on that
  database in `database.yml`); `db:prepare` creating it is measured on Rails 8.1.4,
  not documented. The §7 Pulse traps are written for Pulse's generated schema and do
  not apply to your own models; what still bites is a spec that the models really
  connect to the second database and that the primary has no copy of the tables.
- Keep **retention per table** and purge in bounded batches (for example errors 90
  days, performance 30; a recommendation), and make a missing table a loud error,
  not an empty page.

**`pg_stat_statements` for slow queries**

- **`CREATE EXTENSION pg_stat_statements` is not enough.** The library must be in
  `shared_preload_libraries` (a server restart; PostgreSQL 16 docs), and the extension
  is created per database. Retask measured on `postgres:16` (16.15) that reading the
  view then fails with *"pg_stat_statements must be loaded via
  shared_preload_libraries"* while `CREATE EXTENSION` succeeds; the error text is
  measured, not documented. Availability must therefore be decided by **trying the
  view**, not by checking `pg_extension`.
- **Utility statements keep their literals.** `pg_stat_statements.track_utility`
  defaults to on and tracks every command other than SELECT, INSERT, UPDATE, DELETE
  and MERGE; constants are replaced by `$n` only in the statements it normalises.
  Measured: `create role … password '…'` appeared verbatim. Set
  `pg_stat_statements.track_utility = off` and read data statements only before
  showing the text to anyone.
- **On Kamal 2.12.0 the preload flag is the accessory's `cmd:`** (for example
  `postgres -c shared_preload_libraries=pg_stat_statements`). It takes effect only
  when the container is recreated: `kamal accessory reboot NAME` (prepare, pull the
  image, stop, remove, boot) does that, restarting the database once and pulling the
  image; `kamal accessory restart` (stop, start) does not apply a changed `cmd`.

**Alerts from an error store (one defensible design)**

- A recurring **scan** of the error store, rather than work inside a `Rails.error`
  subscriber (which must never raise), with a lookback longer than the scan interval
  so the next scan recovers a missed one. A **unique claim per occurrence**, taken
  before anyone is told, makes a repeated scan harmless and gives at-most-once
  delivery: if sending raises after the claim, rescue it and call
  `Rails.error.report(error, handled: true)` so the failure is not silent
  (`deliver_later` only covers the enqueue; a later mail-job failure is recorded by
  the job's own error handling). A rate alert keyed by clock hour can fire twice
  across an hour boundary.
- An alert carries **a sentence, a count and a link**, never an error class, message,
  argument, backtrace line or id; keep the fingerprint for throttling only. Hold it
  with a spec that feeds forbidden strings through the source and fails if the alert
  path ever asks for a detail or any of them reaches a subject, body or inbox row.

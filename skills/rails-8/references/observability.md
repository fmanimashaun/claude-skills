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
| `strict_loading_violation.active_record` | `:owner, :reflection` | N+1 telemetry when strict_loading is `:log`; `:n_plus_one_only` misses the top-level loop (note below) |
| `transaction.active_record` | `:connection, :outcome` (commit/rollback) | Rollback-rate monitoring |
| `render_template/render_partial.action_view` | `:identifier, :layout` / `:identifier, :cache_hit` | View timing, cache hit ratios |
| `render_collection.action_view` | `:identifier, :count, :cache_hits` | Collection-cache effectiveness |
| `deliver.action_mailer` | `:mailer, :message_id, :subject, :to` | Mail volume/failures |
| `enqueue.active_job` / `perform_start.active_job` / `perform.active_job` | `:job, :adapter` (+ `:db_runtime, :aborted` on perform) | Queue latency, on `perform_start`: `event.time - payload[:job].enqueued_at.to_f` (note below) |
| `cache_read/cache_write/cache_fetch_hit/cache_generate.active_support` | `:key, :store, :hit, :super_operation` | Hit-rate dashboards, Solid Cache included (note below) |
| `perform_action.action_cable` / `broadcast.action_cable` | `:channel_class, :action` / `:broadcasting` | Realtime volume |
| `process.action_mailbox` | `:mailbox, :inbound_email` | Inbound mail pipeline |
| `service_upload.active_storage` (and download/delete) | `:key, :service, :checksum` | Storage ops |
| `deprecation.rails` | `:message, :callstack, :gem_name` | Fail CI on new deprecations |

**Three of these, measured and read from source** (verified at rails 8.1.4, solid_queue 1.7.0,
solid_cache 1.0.10; #2065):

- **Queue latency comes from Active Job, not Solid Queue.** `perform_start.active_job` carries
  `:job`, and `enqueued_at` is stamped in `serialize` and restored on deserialize
  (`active_job/core.rb:129`, `:170`), so latency is `event.time - payload[:job].enqueued_at.to_f` (`event.time` is a Float, and a Float
  minus a Time raises); a
  scheduled job counts from `scheduled_at`, since `enqueued_at` is the enqueue moment. Solid Queue
  instruments no per-job latency; its `SolidQueue::Queue#latency` is the age of the oldest ready
  execution for a whole queue (`app/models/solid_queue/queue.rb:41-47`), not instrumented.
- **Solid Cache reports hits through the standard events.** `SolidCache::Store <
  ActiveSupport::Cache::Store` (`solid_cache/store.rb:4`), so `cache_read` carries `hit: true/false`
  and `super_operation: :fetch` inside a `fetch` (`active_support/cache.rb:473-474`); a fetch hit
  also emits `cache_fetch_hit`, a miss `cache_generate` then `cache_write` (the write is skipped for
  a nil result under `skip_nil`). A transient database error (the six in `Failsafe::TRANSIENT_ACTIVE_RECORD_ERRORS`, `failsafe.rb:6-13`)
  is swallowed: the read returns nil, the payload says `hit: false` with no `exception`, and the error
  goes to `Rails.error` and the store's `error_handler`, so a hit-rate dashboard counts it as a miss.
  Only a non-transient error raises and carries `exception` in the `cache_read` payload (verified at
  solid_cache 1.0.10).
- **`strict_loading_mode = :n_plus_one_only` does not report the classic N+1.** The owner's own
  lazy loads pass (`associations/association.rb:240-244`); only records it loaded through a
  `has_many` are marked strict (`:123-128`), so `user.comments.first.ratings` is reported and
  `User.all.each { |u| u.comments.to_a }` is **not** (measured: 0 events for the loop, 1 for the
  second level). Mode `:all` is the default, and `:all` with
  `action_on_strict_loading_violation = :log` (the default action is `:raise`) reports EVERY lazy load
  on a strict record, which is noisy, not a sampled N+1 signal; a detector is the alternative. A
  reflection declared `strict_loading: true` reports in either mode.

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
earlier Rails versions were not checked. Each bullet says what was confirmed, what
was only partly confirmed (and how it is narrowed), and what is measured in one
app; the audit record `docs/evidence/audits/2026-10-11-observability-otel-1694.md`
has the row for each.

- **A request exception is reported on one of two paths, and sometimes on neither.**
  `ActionDispatch::Executor` (outermost, then `ShowExceptions`, then `DebugExceptions`)
  reports with `handled: false`, `source: "application.action_dispatch"`:
  1. *After the app returns normally*, when `ShowExceptions` rendered the error page and
     the exception class has no `rescue_responses` entry (`ShowExceptions` sets
     `action_dispatch.report_exception` to `!wrapper.rescue_response?`).
  2. *When an exception propagates out of the inner app*, whatever its class, because
     `Executor` rescues, reports and re-raises. `ShowExceptions` re-raises when
     `show_exceptions` is `:none`, or `:rescuable` and the class has no entry. With
     `show_detailed_exceptions` false, `DebugExceptions` re-raises to `ShowExceptions`,
     so a 500 under `:all` takes path 1.

  `DebugExceptions` renders its own page and returns normally when
  `show_detailed_exceptions` is true, so nothing reaches `ShowExceptions` and nothing is
  reported. By the generator defaults: development (`:all`, detailed) reports nothing;
  test (`:rescuable`, detailed) reports an exception with no `rescue_responses` entry (path 2,
  and it is raised into the spec) but not a 404 or 422; production (`:all`, not
  detailed) reports a 500 by path 1 and not a 404 or 422. A 404 (`RecordNotFound`) or
  422 (`InvalidAuthenticityToken`) is reported under `show_exceptions = :none`, or when it
  arrives wrapped (`ActionView::Template::Error` has no entry, and its cause is what is
  reported). To see which path a spec takes, assert on a subscriber under the
  environment's real `show_exceptions` and `show_detailed_exceptions` rather than
  assuming one.
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
  `ActiveRecord::RecordNotUnique` passes through the database's detail text, which
  for some constraint errors names the failing values (the exact PostgreSQL format is
  not verified here). `RecordInvalid` messages name the
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
  What the tags are: `config.active_record.query_log_tags` defaults to
  `[:application, :controller, :action, :job]`; `query_log_tags_format` is
  `:sqlcommenter` or `:legacy`, and `config.load_defaults 7.1` or later makes
  `:sqlcommenter` the default (Rails configuring guide, 8.1, read 2026-10-14).
  The guide warns that the `:source_location` tag "can be slow" to compute —
  weigh that before adding it in production. A tagged comment does **not** change
  the query identifier `pg_stat_statements` groups by (measured on PostgreSQL 18.6 as
  the core Query Identifier, `EXPLAIN (VERBOSE)`; see the `pg_stat_statements` section
  below). So a `pg_stat_statements` row cannot be read as one route: per-route
  attribution comes from the tags on a statement while it runs, in `pg_stat_activity`.
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
the OpenTelemetry instrumentation gems map the same hooks to OTel spans
exportable anywhere (`opentelemetry-instrumentation-rails` is a bundle, not the
instrumentation itself: see the in-house subsection below for what `c.use` of it
does and does not install). Your custom `instrument`/`Rails.event` calls then ride
along as first-class spans/events in whichever backend the app uses.

### Finding slow pages and N+1s on a live app (sampling, thresholds)

Source: each point below was read on the named official page on 2026-10-14; the fetch tool summarises pages, so quotes are not byte-checked.

- **Production N+1 comes from sampled spans, not from Prosopite.** Prosopite's README
  shows development and test setups and wraps its Rack/Sidekiq middleware and `around_action`
  examples in `unless Rails.env.production?`; it says nothing about production use, sampling or
  overhead (<https://github.com/charkost/prosopite>). Keep it as the **post-fix regression test**
  in the suite (`performance-caching.md`), and look for N+1 on a live app in the traces your
  APM or OpenTelemetry already collects.
- **A threshold template.** Sentry detects an N+1 as "a set of sequential, non-overlapping
  database spans with similar descriptions" whose total duration exceeds 50 ms and whose count
  exceeds a threshold ("usually five spans"); the thresholds are configurable under Project
  Settings > Performance (<https://docs.sentry.io/product/issues/issue-details/performance-issues/n-one-queries/>,
  "Detection Criteria"). Borrow the shape when you write your own rule: a count AND a combined
  duration, over similar statements, not either alone.
- **Sample, and say how.** Sentry: `traces_sample_rate` is a uniform rate between 0 and 1;
  `traces_sampler` decides per transaction from a `sampling_context` and returns a boolean or a
  float; the two are meant to be mutually exclusive and, if both are set, `traces_sampler` wins
  (<https://docs.sentry.io/platforms/ruby/guides/rails/tracing/>). OpenTelemetry Ruby:
  `OTEL_TRACES_SAMPLER="traceidratio"` with `OTEL_TRACES_SAMPLER_ARG="0.1"` exports 10% of
  traces; the page advises configuring it through the environment rather than in code
  (<https://opentelemetry.io/docs/languages/ruby/sampling/>). Neither page says a sampler
  can select only slow transactions, so do not design around that.
- **What Rails Pulse says and does not say** (README, read 2026-10-14): tracking is "queued off the
  request thread and dropped rather than blocked under load"; thresholds for slow, very slow and
  critical are configurable but **no default values are documented**; N+1 patterns are listed
  among its query views without a description of how they are detected; its words for the SQL it
  stores are "normalised and fingerprinted" (so execution counts and P95 show per statement
  shape), which is not a statement that literals are removed. The README does not say whether
  requests are sampled, nor whether SQL literals are removed before storage. Do not assume
  either; check the stored rows before putting Pulse in front of data that must not hold
  literals.

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

**Its defaults, read from source (0.4.2):** thresholds in ms — routes `slow 500 / very_slow
1500 / critical 3000`, requests `700 / 2000 / 4000`, queries `100 / 500 / 1000`, jobs `5000 / 30000
/ 60000`; exceptions are counts (`warning 10, critical 100`) (`lib/rails_pulse/configuration.rb:62-68`).
Regressions need a ratio **and** an absolute floor plus enough samples (`ratio 1.5`, `min_delta_ms
50`, `min_samples 100`, `min_baseline_periods 3`, `:158-167`). SQL is stored **normalised** (literals
become `?`, `app/services/rails_pulse/sql_query_normalizer.rb`); raw SQL is opt-in
(`capture_actual_sql`, default false, because unparameterised SQL would keep emails and passwords).
Requests are **not sampled**; under pressure the bounded queue drops instead. `track_jobs`,
`track_exceptions` and `track_assets` default to off.

**Noise control for a slow-page or N+1 finder — advice, not doctrine** (a design, not yet run
against real traffic): judge a route by p95 only above a minimum request count, against a
baseline of several prior periods, over consecutive windows; report one finding per route and
query, cap findings per run, and exclude health checks and deploy windows. Rails Pulse's regression
rules above (ratio plus absolute floor, minimum samples, baseline periods) are one shipped instance.

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
action_pack 0.18.1, rack 0.31.2, pg 0.37.0, net_http 0.29.2). Most framework
claims below were checked against those gem sources or the official docs (the audit
record `docs/evidence/audits/2026-10-11-observability-otel-1694.md` has each row and
verdict); a claim that is only partly confirmed is narrowed in the text, and anything
else is marked "measured in Retask" (one app, not read from source) or "design" (a
choice, not a fact). No exporter is installed and nothing leaves the server:
spans are folded in process into aggregates and written to the app's own database.

**Capture**

- **The Rack instrumentation records the query string, and has no option to drop it
  (rack 0.31.2).** The server span carries it as `url.query` (stable semantic conventions), or as
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
- **`c.use "OpenTelemetry::Instrumentation::Rails"` installs no instrumentation of
  its own** (its install block is `install { true }`; rails 0.42.0). Use `c.use_all`
  (the documented way), or `c.use` each of ActionPack, ActionView, ActiveSupport,
  ActiveRecord and ActiveJob. A request span needs ActionPack.
- **The PG instrumentation traces every query, and a prepared statement is two
  spans.** PREPARE and EXECUTE are separate spans carrying the obfuscated statement
  (with `db_statement: :obfuscate`, literals become `?` and `$1` becomes `$?`);
  there is no `SCHEMA` name to filter on, so filter on `db.operation`. Schema
  lookups on the `pg_` catalog tables appear in the stream too (measured in Retask,
  not read from source). Scrub the statement again before using it as a display name.
- **Span ids are drawn with `Random.bytes`,** the default generator that `srand`
  seeds, so every span moves a seeded sequence and a spec that fixes a seed and runs a
  query is no longer deterministic. Give the SDK its own id generator (any object
  responding to `generate_trace_id` and `generate_span_id`, built on
  `Random.urandom`) through `OpenTelemetry::SDK.configure`.
- **An exception inside an exporter or processor does not fail the request.** The
  two processors differ (sdk 1.13.1): `SimpleSpanProcessor` catches it and calls
  `OpenTelemetry.handle_error`, which logs `unexpected error in span.on_finish`;
  `BatchSpanProcessor` has its own failure handling on export (FAILURE result, counted
  as `otel.bsp.error`). A custom exporter's bug looks like missing spans, so unit
  test the exporter by calling it directly.

**Specs for spans**

- WebMock replaces `Net::HTTP` with a subclass that, read from the webmock and
  net_http instrumentation sources (not run here), never calls the patched `request`
  for a stubbed call, so a stubbed request has no client span; allow a real loopback
  connection to assert on one.
- `start_span(start_timestamp:)`, `finish(end_timestamp:)` and `add_event(timestamp:)`
  take a `Time` or a number of **seconds** (the SDK multiplies by 1e9), never
  nanoseconds.
- From Ruby 4.0 `benchmark` is a bundled gem: under Bundler, `require "benchmark"`
  raised `LoadError` when it was not in the Gemfile (checked on Ruby 4.0.6), so a
  script run with `bin/rails runner` needs it listed.
- Code that an initializer needs must not sit in an autoloaded `lib/`: use
  `config.autoload_lib_once`, or `require` it and keep it out of autoloading with
  `autoload_lib(ignore:)` (Rails autoloading guide).

**Store and read side (design choices, and facts measured in Retask)**

- Put the store on a **separate database** with its own migrations
  (`migrations_paths: db/observability_migrate` and a `schema_dump` file on that
  database in `database.yml`) (design); `db:prepare` creating it is measured in Retask
  on Rails 8.1.4, not documented. The §7 Pulse traps are written for Pulse's generated
  schema and do not apply to your own models; what still bites (measured in Retask) is
  a spec that the models really connect to the second database and that the primary has
  no copy of the tables.
- Keep **retention per table** and purge in bounded batches (for example errors 90
  days, performance 30; design, a recommendation), and make a missing table a loud error,
  not an empty page.

**`pg_stat_statements` for slow queries**

- **`CREATE EXTENSION pg_stat_statements` is not enough.** The library must be in
  `shared_preload_libraries` (a server restart; PostgreSQL 18 docs), and the extension
  is created per database. Retask measured on `postgres:16` (16.15; not re-measured on 18) that reading the
  view then fails with *"pg_stat_statements must be loaded via
  shared_preload_libraries"* while `CREATE EXTENSION` succeeds; the error text is
  measured, not documented. Availability must therefore be decided by **trying the
  view**, not by checking `pg_extension`.
- **Utility statements keep their literals.** `pg_stat_statements.track_utility`
  defaults to on and tracks every command other than SELECT, INSERT, UPDATE, DELETE
  and MERGE; constants are replaced by `$n` only in the statements it normalises.
  Measured on 16: `create role … password '…'` appeared verbatim (the set of utility commands it normalises grew in 17 and 18: re-check on your version). Set
  `pg_stat_statements.track_utility = off` and read data statements only before
  showing the text to anyone.
- **On Kamal 2.12.0 the preload flag is the accessory's `cmd:`** (for example
  `postgres -c shared_preload_libraries=pg_stat_statements`). It takes effect only
  when the container is recreated: `kamal accessory reboot NAME` (prepare, pull the
  image, stop, remove, boot) does that, restarting the database once and pulling the
  image; `kamal accessory restart` (stop, start) does not apply a changed `cmd`.
- **Know what the view cannot tell you (PostgreSQL 18 docs).** `queryid` is a function
  of internal object identifiers: two apparently identical queries are distinct if they
  reference a function that was dropped and recreated between them, while a table dropped
  and recreated can make two apparently identical queries count as the same. It is "not
  safe to assume" stable across major versions, and is not a useful identifier across
  logical replicas (physical replicas match). The stored
  text is that of the *first* query with that `queryid`. There are no percentiles, only
  `min`/`max`/`mean`/`stddev_exec_time`. A rising `pg_stat_statements_info.dealloc`
  means the least-executed statements were evicted (`pg_stat_statements.max` exceeded),
  so the tail is missing. `pg_stat_statements_info.stats_reset` is the time of the last full reset; each row
  also carries `stats_since` (when its statistics began) and `minmax_stats_since` (when its
  min/max last reset), both since 17. On 18 a list of constants that differs only in length
  is squashed to one entry shown as `IN ($1 /*, ... */)` (18.0 release notes). Rank by the delta between two
  snapshots rather than calling `pg_stat_statements_reset()` from a monitor (superuser
  only by default), and poll with `pg_stat_statements(showtext := false)` to skip
  reading the texts.
- **`query_log_tags` do not split a statement by route here (PostgreSQL 18 docs;
  measured on 18.6).** `queryid` "is computed on the post-parse-analysis
  representation of the queries", so a comment does not change it: the same `SELECT`
  with no comment, with a tag comment at either end, and with different
  `controller`/`action` values gave one Query Identifier (`SET compute_query_id = on`,
  `EXPLAIN (VERBOSE)`). Every route's executions fold into one row. The tags attribute
  a query to a route **per execution** only: in `pg_stat_activity.query` while it
  runs. That column is truncated at `track_activity_query_size` (1024 bytes by
  default), so a tag at the end of a long query can be cut off; raise the setting, or
  put the tags first with `config.active_record.query_log_tags_prepend_comment = true`.
- **Two switches cost on a busy server, and both default off.**
  `pg_stat_statements.track_planning` "may incur a noticeable performance penalty"
  under concurrent identical statements; `track_io_timing` repeatedly queries the OS
  clock, "significant overhead on some platforms". Turn them on deliberately.
- **`auto_explain` does nothing until `auto_explain.log_min_duration` is set** (default
  -1). `log_analyze` times every plan node of every statement ("an extremely negative
  impact on performance"): pair it with `auto_explain.sample_rate` below 1 and
  `log_timing = off`. `auto_explain.log_parameter_max_length` (since 16) defaults to -1, which logs
  bind values **in full**, which means personal data in the logs; set it to 0. Load it
  via `session_preload_libraries` or `shared_preload_libraries`.
- **Logging companions (PostgreSQL 18 docs):** `log_min_duration_sample` (default -1, off) with
  `log_statement_sample_rate` (default 1.0, every sampled statement),
  `log_lock_waits` (default off) and `log_temp_files` (default -1, off).
- **Least privilege for the reader.** Grant the monitoring role `pg_read_all_stats`
  (needed to see other users' text and `queryid`), **not** `pg_monitor`: `pg_monitor`
  includes `pg_stat_scan_tables`, whose functions "may take ACCESS SHARE locks on
  tables, potentially for a long time". That role is also what `pgstattuple` requires,
  so a `pg_read_all_stats` reader cannot run `pgstattuple` (it can still read
  `n_dead_tup`). Set `statement_timeout`,
  `lock_timeout` and `idle_in_transaction_session_timeout` per role
  (`ALTER ROLE … SET`); the docs call setting the first two in `postgresql.conf` "not
  recommended because it would affect all sessions".
- **Each standby keeps its own statistics.** Scans and index usage are recorded on the
  node that served them, but "WAL replay will not increment" `pg_stat_all_tables`
  counters such as `n_tup_ins`, and autovacuum is not active during recovery; recovery
  conflicts can cancel standby queries. Read statistics from every node that serves
  traffic.

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

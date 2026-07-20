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
7. Wiring up APMs / OpenTelemetry

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

# Report an already-rescued exception:
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

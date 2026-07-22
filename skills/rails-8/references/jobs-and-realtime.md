# Background Jobs and Realtime: Active Job, Solid Queue, Action Cable

## Contents
1. Active Job fundamentals
2. Solid Queue: configuration and operation
3. Recurring jobs
4. Continuations (8.1) — resumable long jobs
5. Concurrency controls and good job design
6. Action Cable with Solid Cable
7. Threading & the Rails executor

---

## 1. Active Job fundamentals

Anything slow, retryable, or third-party leaves the request cycle:

```bash
bin/rails g job ProcessPayment   # app/jobs/process_payment_job.rb + test
```

```ruby
class ProcessPaymentJob < ApplicationJob
  queue_as :default                       # or :critical / lambda per-job
  retry_on Stripe::RateLimitError, wait: :polynomially_longer, attempts: 5
  discard_on ActiveJob::DeserializationError   # record deleted before run — fine to drop

  def perform(order)                      # pass records, not ids: GlobalID (de)serializes them
    order.charge!
  end
end

ProcessPaymentJob.perform_later(order)
ProcessPaymentJob.set(wait: 1.hour, queue: :low).perform_later(order)
ProcessPaymentJob.set(wait_until: Date.tomorrow.noon).perform_later(order)
ProcessPaymentJob.perform_all_later(orders.map { ProcessPaymentJob.new(_1) })  # bulk enqueue
```

- Arguments must be serializable: records (GlobalID), primitives,
  Hash/Array, Time — not arbitrary objects (write an
  `ActiveJob::Serializer` if truly needed).
- **Enqueue-after-commit is the default** (`:default` behavior since 7.2/8):
  `perform_later` inside a transaction enqueues only after commit, so jobs
  never race an uncommitted record. Don't fight this.
- Unhandled exceptions after retries exhaust → job discarded to the failed
  set (Solid Queue keeps failed executions for inspection/retry). Report
  with `Rails.error` if you rescue manually.
- Callbacks (`before_perform`, `around_enqueue`) exist; keep them thin.
- Mailers ride the same rails: `OrderMailer.receipt(order).deliver_later`.

## 2. Solid Queue

Database-backed queue, default in Rails 8 production
(`config.active_job.queue_adapter = :solid_queue`, connected to the `queue`
database). No Redis. Supervise with:

```bash
bin/jobs                       # starts supervisor per config/queue.yml
```

`config/queue.yml`:

```yaml
default: &default
  dispatchers:
    - polling_interval: 1
      batch_size: 500
  workers:
    - queues: "*"
      threads: 3
      processes: <%= ENV.fetch("JOB_CONCURRENCY", 1) %>
      polling_interval: 0.1
development: *default
production:  *default
```

Deployment modes (see deployment reference for Kamal wiring):

- **Inside Puma** — the generated `deploy.yml` sets
  `SOLID_QUEUE_IN_PUMA: true`, activating the `solid_queue` Puma plugin
  (`plugin :solid_queue` guarded in `config/puma.rb`). One process runs web +
  jobs: right for small apps.
- **Dedicated job machines** — a `job:` server role running `bin/jobs`.
  Scale `JOB_CONCURRENCY`/threads there.

Development uses the `:async` adapter by default (in-process, lost on
restart); run `bin/jobs` locally when you need real queue behavior, and use
the `:test` adapter assertions in tests (see testing reference). Prioritize
by listing queues in order (`queues: [real_time, background]`) or use
per-job `queue_with_priority`. For a dashboard, add the
`mission_control-jobs`:

```ruby
# routes.rb — always behind auth
authenticate :user, ->(u) { u.admin? } do
  mount MissionControl::Jobs::Engine, at: "/jobs"
end
# or HTTP basic: MissionControl::Jobs.http_basic_auth_user / _password initializers
```

Features are adapter-dependent (full set on Solid Queue): inspect queues and
per-status jobs, filter by queue/class, retry or discard failed jobs, pause and
resume queues, see which worker runs what. It is the answer to "what is the
queue doing" — never poll SolidQueue tables by hand in app code.

## 3. Recurring jobs

`config/recurring.yml` — Solid Queue's built-in scheduler (no cron, no gem):

```yaml
production:
  refresh_search_index:
    class: RefreshSearchIndexJob
    queue: background
    schedule: every hour
  cleanup_carts:
    command: "Cart.abandoned.in_batches.destroy_all"
    schedule: every day at 4am
```

Schedules use Fugit natural syntax or cron strings. Entries run exactly-once
per tick across processes. Keep recurring jobs idempotent.

## 4. Continuations (8.1) — resumable long jobs

Deploys give job containers ~30 s to stop (Kamal default). Continuations let
interrupted jobs resume at the last completed step instead of restarting:

```ruby
class ProcessImportJob < ApplicationJob
  include ActiveJob::Continuable

  def perform(import_id)
    @import = Import.find(import_id)

    step :initialize do
      @import.prepare!
    end

    step :process do |step|                       # cursor persists on interruption
      @import.records.find_each(start: step.cursor) do |record|
        record.process
        step.advance! from: record.id             # checkpoint after each record
      end
    end

    step :finalize                                # method form → calls private #finalize
  end

  private
    def finalize = @import.complete!
end
```

Rules: steps execute in order and are skipped once completed; anything
between/around steps re-runs on resume, so keep setup idempotent
(`find`, memoization) and put all mutation inside steps. Use the cursor for
batch loops so progress inside a step survives too. Reach for continuations
whenever a job can exceed the shutdown window: imports, exports, backfills,
fan-out mailers.

## 5. Concurrency controls and good job design

```ruby
class SyncAccountJob < ApplicationJob
  limits_concurrency to: 1, key: ->(account) { account }, duration: 5.minutes
  def perform(account) ... end
end
```

(`limits_concurrency` is Solid Queue's per-key mutex — one sync per account
at a time; `group:` shares limits across job classes.)

Design rules that prevent 3 a.m. pages:

- **Idempotent always** — retries and continuations both re-run code. Guard
  with state checks (`return if order.paid?`) or unique constraints.
- **Small arguments, fresh reads** — pass the record, reload state inside
  `perform`; don't serialize computed data that can go stale.
- **One job, one responsibility**; fan out with `perform_all_later` rather
  than looping inside a mega-job (or use a continuation-stepped batch).
- Let `retry_on` handle transient failures; `discard_on` expected
  no-ops; anything else should fail loudly into the failed set.

## 6. Action Cable with Solid Cable

Solid Cable (DB-backed pub/sub, `config/cable.yml` → `adapter: solid_cable`
on the `cable` database in production) powers WebSockets without Redis.

**Prefer Turbo broadcasts** (`broadcasts_refreshes`, `broadcast_append_to`,
`turbo_stream_from`) — they cover 90 % of realtime UI with zero channel
code. Drop to raw channels for non-DOM payloads (presence, cursors, games):

```ruby
# app/channels/notifications_channel.rb
class NotificationsChannel < ApplicationCable::Channel
  def subscribed
    stream_for current_user
  end
end
# broadcast from anywhere (a job, ideally):
NotificationsChannel.broadcast_to(user, title: "Done", body: "...")
```

```js
// app/javascript/channels/... (pin @rails/actioncable)
consumer.subscriptions.create("NotificationsChannel", {
  received(data) { /* update DOM — or better, do this in a Stimulus controller */ }
})
```

Authenticate connections in `ApplicationCable::Connection#connect` by
reading the same signed session cookie the web app sets
(`identified_by :current_user`; reject unless found). Broadcast from
`after_commit`/jobs, never mid-transaction.

## 7. Threading & the Rails executor

Rails-managed threads — requests, jobs, Action Cable — already run inside the
framework Executor. Code that creates its OWN concurrency (`Thread.new`,
Concurrent promises, rack middleware doing work after the response, gem
listeners/pollers) must wrap itself, or you get leaked AR connections and
sporadic dev-mode `NameError`s from autoloading:

```ruby
Thread.new do
  Rails.application.executor.wrap do
    # framework-safe: autoloading, query cache, connection handling all correct
  end
end
```

- Never nest `executor.wrap` inside a request or job — those are already wrapped.
- Blocking on another thread FROM wrapped code can deadlock the dev autoloader;
  wrap the wait:
  `ActiveSupport::Dependencies.interlock.permit_concurrent_loads { thread.join }`.
- A manual thread that touches the database and can't use the executor must at
  least use `ActiveRecord::Base.connection_pool.with_connection { ... }`.
- Never cache references to reloadable constants across requests (class-level
  memoized models, middleware holding a service object): in development the
  reloader swaps those classes underneath you. Re-derive them in
  `Rails.application.config.to_prepare`.
- These bugs hide in development and surface under production concurrency. If a
  gem spawns threads, verify it wraps — or wrap the callback you hand it.

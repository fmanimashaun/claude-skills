section: rails-stack (skills plugin
- **`observability.md`: queue latency, Solid Cache hits, strict loading and Rails Pulse defaults, measured and verified — `skills/rails-8/references/observability.md`** (#2065, items 2-5 of #2046, split from #2038). Measured on rails 8.1.4, solid_queue 1.7.0 and solid_cache 1.0.10 (Retask's lock); `doctrine-verifier` CONFIRMED each against the installed gem source by file and line (recorded on #2065). Version boundary: verified at these versions.
  - **Queue latency** comes from Active Job: `perform_start.active_job` time minus `job.enqueued_at` (a scheduled job counts from `scheduled_at`). Solid Queue instruments no per-job latency; its `SolidQueue::Queue#latency` is queue-level and not instrumented.
  - **Solid Cache** reports `hit` and `super_operation` through the standard `cache_read` event, because it subclasses `ActiveSupport::Cache::Store`.
  - **`strict_loading_mode = :n_plus_one_only` does not report the top-level N+1 loop** (0 events measured), only a lazy load on records loaded through a `has_many`. A production signal needs mode `:all` with `:log`.
  - **Rails Pulse 0.4.2's defaults** come from its source: thresholds, regression rules, SQL normalised by default, raw SQL opt-in, no request sampling.
  - **Noise rules for a finder** are labelled advice, not doctrine.

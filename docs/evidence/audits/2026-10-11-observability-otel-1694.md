# doctrine-verifier verdicts for #1694 (rails-8 observability.md), 2026-10-11

Three read-only verifier runs (the `doctrine-verifier` protocol, run from a Retask session against that app's
installed gems, Rails 8.1.4, Ruby 4.0.6), one per claim cluster. Edits in `skills/rails-8/references/observability.md`
follow CONFIRMED rows only; PARTLY and INCONCLUSIVE rows were narrowed or labelled as measured / design, and the
last column says what the doctrine does. Gem paths are under the installed `ruby/4.0.0/gems/`.

## OpenTelemetry capture (opentelemetry-sdk 1.13.1, api 1.11.1; rack 0.31.2, action_pack 0.18.1, rails 0.42.0, pg 0.37.0, net_http 0.29.2)

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| O1 | Rack records the query string, no option drops it | CONFIRMED | rack `middlewares/stable/tracer_middleware.rb:134`, `stable/event_handler.rb:197` (`url.query`); `http.target` only under `http/dup`/`old`; `instrumentation.rb` options list; `url_quantization` only names spans | stated; the allow-list wrapper is "one safe design" |
| O2 | (retracted by the reporter) hand-inserting the middleware duplicates it | CONFIRMED for the railtie | action_pack `railtie.rb` `before_initialize` inserts at 0 once ActionPack is `use`d | "do not insert it yourself" + a one-entry spec; the retracted "insert it yourself" advice is NOT written |
| O3 | `c.use "…Rails"` installs nothing, ActionPack etc. must be listed | CONFIRMED (qualified: `use_all` is the documented alternative) | rails `instrumentation.rb` `install { true }`; README | stated with `use_all` |
| O4 | ids use `Random.bytes`, `srand` makes seeded specs non-deterministic | CONFIRMED | api `trace.rb:29-40`; `ruby -e` reproduction; sdk `Configurator#id_generator=` | stated; a custom `id_generator` (not a prepend) |
| O5 | PG: PREPARE/EXECUTE spans, catalog noise, no SCHEMA name | CONFIRMED for 3 of 4 | pg `patches/connection.rb:111-135`, `:224-230`; `obfuscator.rb:66` | stated; catalog noise labelled "observed, not read from source" |
| O6 | WebMock hides Net::HTTP instrumentation | CONFIRMED (read, not run) | net_http `instrumentation.rb:66-74`; webmock `http_lib_adapters/net_http.rb:20,85-116` | stated |
| O7 | timestamps are seconds, not nanoseconds | CONFIRMED (keyword lives on `start_span`, not `Span`) | sdk `span.rb:361-362`, `:462-463`; `tracer.rb:28,32` | stated with the right methods |
| O8 | Ruby 4.0 no longer ships `benchmark` as a default gem | CONFIRMED under Bundler | `bundle exec ruby -e 'require "benchmark"'` LoadError | stated (Bundler) |
| O9 | an initializer cannot load autoloaded `lib/` code | CONFIRMED | railties `application/configuration.rb:490-500`; Rails autoloading guide | stated with `autoload_lib_once` / `require` + `ignore:`; the namespace-collision tip left out (Retask-specific, unverified) |
| O10 | the SDK swallows exporter/processor exceptions | CONFIRMED for SimpleSpanProcessor; Batch differs | sdk `simple_span_processor.rb:58-63`; `batch_span_processor.rb:186-195` | stated for both, with each log/metric |

## Rails error reporting (actionpack, activejob, activesupport 8.1.4)

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| E1 | (first pass, WITHDRAWN) requests are reported only after ShowExceptions, only without a `rescue_responses` entry, only when `show_detailed_exceptions` is false | marked CONFIRMED on a partial read; REFUTED on review of PR #1814: it missed `executor.rb:32-37`, which also reports whatever propagates out of the inner app | see E1a-E1f below | the doctrine now describes both paths and drops the "must set show_detailed_exceptions = false" |
| E2 | path/verb are `action_dispatch.original_*`; the context controller is the error page's | PARTLY (the controller part only when the exceptions app is a routed controller) | `show_exceptions.rb:48-55` | stated with the qualification |
| E3 | retries and discards are not reported by default | CONFIRMED, one refinement (the final raise is reported by the execution wrapper, not ActiveJob) | `activejob exceptions.rb:64-83,109-117,158-159`; `execution_wrapper.rb:86-94`; `railtie.rb:82-89` | stated |
| E4 | `context:` holds live objects, ParameterFilter cannot see inside | CONFIRMED | `error_reporter.rb:~245`; `execution.rb:66` | stated |
| E5 | messages carry values | PARTLY CONFIRMED / PARTLY REFUTED: driver detail passes through (`postgresql_adapter.rb:818-840`); `RecordInvalid` messages normally do NOT carry the value (`activemodel locale/en.yml`) | the exact PG `Key (…)=(…)` format is INCONCLUSIVE here | stated narrowly; PG formats not quoted |
| E6 | `perform_enqueued_jobs { }` fails under RSpec (`tagged_logger`) | INCONCLUSIVE (leaning refuted for rspec-rails 8.0.4, which includes the TaggedLogging adapter) | `rspec-rails adapters.rb:186-193` | NOT written |
| E7 | alert design: scan + unique claim, at-most-once with a non-silent failure; a sentence, a count and a link | DESIGN-OPINION, factual parts confirmed (`deliver_later` only covers the enqueue; `Rails.error.report(handled: true)`) | `error_reporter.rb` | written as "one defensible design" |

### E1 re-verification (batch 4, after review of #1814; raw output in `raw/…-verifier-4.md`; actionpack 8.1.4)

| id | claim | verdict | authority |
|---|---|---|---|
| E1a | Executor reports on two paths: after a normal return with `report_exception` (class has no `rescue_responses` entry), and in its `rescue Exception` branch whatever the class | CONFIRMED | `executor.rb:22-25`, `:32-37`; `show_exceptions.rb:38` |
| E1b | ShowExceptions re-raises under `:none`, and under `:rescuable` for a class with no entry; so `:none` reports even a 404 | CONFIRMED | `exception_wrapper.rb:185-198`; `show_exceptions.rb:40-44` |
| E1c | DebugExceptions renders and swallows when `show_detailed_exceptions` is true; re-raises to ShowExceptions when false | CONFIRMED | `debug_exceptions.rb:39-47`, `:58-78` |
| E1d | generator defaults: development `:all`+detailed (nothing reported), test `:rescuable`+detailed, production `:all`+not detailed; Retask test.rb:23,33 matches | CONFIRMED | railties templates `{development,test,production}.rb.tt`; `application.rb:320-321` |
| E1e | "a 404/422 is never reported" | REFUTED as a blanket claim | reported under `:none`, or when wrapped (`ActionView::Template::Error` has no entry, its cause is reported) |
| E1f | "a spec must set `show_detailed_exceptions = false`" | REFUTED as stated | path 2 needs no change; path 1 needs `:all` + detailed false |

## pg_stat_statements and Kamal (PostgreSQL 16 docs; Kamal 2.12.0)

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| P1 | the library must be preloaded; creating the extension is not enough; check by trying the view | The requirement CONFIRMED (PG16 docs `pgstatstatements.html`); the error text and "CREATE succeeds" INCONCLUSIVE from docs, measured on postgres:16.15 by the reporter | docs quote: "must be loaded by adding pg_stat_statements to shared_preload_libraries … a server restart is needed" | stated; the error text labelled measured, not documented |
| P2 | utility statements keep literals; `track_utility = off` | `track_utility` and normalisation scope CONFIRMED; the `create role` literal is measured | PG16 docs (track_utility default on) | stated with that split |
| P3 | the preload flag is the Kamal accessory `cmd:`, applied only on container recreation; `accessory reboot` yes, `restart` no | CONFIRMED | kamal-2.12.0 `configuration/accessory.rb:112-113`, `cli/accessory.rb:78-90`, `:126-131` | stated |

## Not in this edit (other files, other issues)

`ecosystem-gems.md` §8 (mission_control-jobs 1.3.1): M1 CONFIRMED, the current recipe (`base_controller_class` alone) admits nobody (`application_controller.rb:10`, `basic_authentication.rb`, `jobs.rb:34`: also set `http_basic_auth_enabled = false`); M2 CONFIRMED (`filter_arguments` matches hash keys only, `arguments_filter.rb`, `solid_queue_ext.rb:116-119`); M3 CONFIRMED (`adapters = [:solid_queue]`, `engine.rb:32-34,64-66`). The route-constraint / 404 pattern for hiding an area (`controllers-routing.md`, `auth-security.md`) and the Pundit redirect are separate gaps. These belong to their own issues (one issue, one PR).

## Review of #1814 (6d, at 109e41a3) and what changed

E1 above (blocker); S1 the intro no longer says each fact was checked, and marks "measured in Retask" and "design"; S2 the store and read-side facts are labelled; S3 the wording of O10 (the two processors differ), E5, O3 (installs no instrumentation of its own, `use_all` is the documented way), O5, O6 (read, not run) and O8 (checked under Bundler on 4.0.6) follows each row; S4 §7's opening no longer says `opentelemetry-instrumentation-rails` maps the hooks by itself; S5 the `SKILL.md` table row names the new content; S6 the raw verifier outputs are committed under `raw/`.

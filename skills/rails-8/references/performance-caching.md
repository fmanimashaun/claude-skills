# Performance & Caching (Rails 8.1)

## Contents
1. Solid Cache setup and low-level caching
2. Fragment and russian-doll caching
3. HTTP caching (ETags, freshness, expiry)
4. Query performance (recap + counter caches, select/pluck, load_async)
5. Runtime performance: YJIT, jemalloc, Puma, Thruster
6. Measuring: profiling and load testing
7. Performance workflow

Telemetry (structured events, Active Support Instrumentation, `Rails.error`,
logging) lives in `references/observability.md`.

---

## 1. Solid Cache setup and low-level caching

New apps ship with **Solid Cache** — a database-backed `Rails.cache` store.
Bigger-than-RAM caches, no Redis, survives restarts.

- Production: `config.cache_store = :solid_cache_store` (already set), backed
  by the `cache:` database in `database.yml` (`db/cache_schema.rb`,
  `storage/cache.sqlite3` on SQLite).
- Options in `config/cache.yml`:

```yaml
default: &default
  store_options:
    # Cap age and/or size; expiry runs async as records are written.
    max_age: <%= 60.days.to_i %>
    max_size: <%= 256.megabytes %>
    namespace: <%= Rails.env %>

production:
  database: cache      # which database.yml entry to use
  <<: *default
```

- Development defaults to `:memory_store` and caching is **off** until you
  run `bin/rails dev:cache` (toggles `tmp/caching-dev.txt`). Always toggle it
  on when working on caching behavior.
- Test uses `:null_store` — caching code runs but nothing persists.

### Low-level caching — `Rails.cache.fetch`

The workhorse for expensive computations and third-party API responses:

```ruby
class Product < ApplicationRecord
  def competing_price
    Rails.cache.fetch("#{cache_key_with_version}/competing_price", expires_in: 12.hours) do
      Competitor::API.find_price(id)
    end
  end
end
```

- `cache_key_with_version` = `products/23-20260705171500000000` — changes when
  the record is `touch`ed/updated, so stale entries are simply abandoned
  (recyclable keys) rather than needing explicit invalidation.
- Passing an AR record or array as the key calls `cache_key_with_version`
  automatically: `Rails.cache.fetch([:v2, product], expires_in: 1.hour) { ... }`.
- Other ops: `read`, `write`, `exist?`, `delete`, `increment`/`decrement`,
  and `fetch_multi(*keys) { |key| ... }` for batched lookups.
- Never cache Active Record objects for cross-request reuse if the schema may
  change mid-deploy; prefer caching primitives/hashes or rendered HTML.

## 2. Fragment and russian-doll caching

Cache rendered view fragments keyed on the records they render:

```erb
<% @products.each do |product| %>
  <% cache product do %>
    <%= render product %>
  <% end %>
<% end %>
```

Better — collection caching fetches all fragments in one read:

```erb
<%= render partial: "products/product", collection: @products, cached: true %>
```

Keys include the template tree digest, so editing the partial busts the cache
automatically. Deploys therefore invalidate cleanly with no manual sweeping.

### Russian-doll nesting

```erb
<% cache product do %>
  <%= render product.games %>   <%# each game partial also wraps itself in cache game %>
<% end %>
```

For the outer fragment to bust when an inner record changes, the child must
`touch` the parent:

```ruby
class Game < ApplicationRecord
  belongs_to :product, touch: true
end
```

Rules of thumb: cache the *innermost* pieces first; only add outer shells when
profiling shows they pay; never wrap fragments containing per-user content
(names, CSRF-less forms are fine — `form_authenticity_token` is injected per
request, but "Hello, Fisayo" is not) unless the user is part of the key:
`cache [current_user, product] do`.

## 3. HTTP caching

Let the browser (and Thruster/CDN) skip work entirely.

### Conditional GET — `fresh_when` / `stale?`

```ruby
def show
  @product = Product.find(params[:id])
  fresh_when etag: @product, last_modified: @product.updated_at
end
```

Rails computes the ETag; if the client's `If-None-Match` matches, it responds
`304 Not Modified` with an empty body — no view rendering. For actions with
more logic:

```ruby
def show
  @product = Product.find(params[:id])
  if stale?(@product)   # etag + last_modified inferred from the record
    respond_to do |format|
      format.html
      format.json { render json: @product }
    end
  end
end
```

Anything that affects the rendered result must be in the ETag —
`fresh_when etag: [@product, current_user&.admin?]`. A class-level
`etag { current_user&.id }` adds a component to every action's ETag. ETags are
weak by default (fine); `strong_etag:` exists for byte-exact needs (Range
requests).

### Time-based expiry

```ruby
def public_index
  expires_in 10.minutes, public: true   # Cache-Control: max-age=600, public
end
```

`public: true` lets shared caches (CDN, Thruster) store it — only for
responses identical for every user. Never on authenticated pages.

## 4. Query performance

Full query guidance lives in `models.md`; the performance-critical recap:

- **N+1s** — `includes`/`preload` at the query site; `strict_loading` to make
  lazy loads raise in development (the `bullet` gem adds dev warnings — see
  `ecosystem-gems.md`).
- **Counter caches** — replace `product.reviews.count` (a COUNT query per
  row) with a maintained column:

```ruby
class Review < ApplicationRecord
  belongs_to :product, counter_cache: true
end
# migration: add_column :products, :reviews_count, :integer, default: 0, null: false
# backfill:  Product.find_each { |p| Product.reset_counters(p.id, :reviews) }
```

  Then `product.reviews.size` uses the column (`.size` prefers the counter;
  `.count` always queries — prefer `.size`).
- **Fetch less**: `select(:id, :name)` for partial objects,
  `pluck(:email)` for raw values, `pick(:email)` for one row,
  `exists?` over `present?` on relations.
- **`load_async`** — run independent queries on background threads while the
  action continues; they join when first accessed:

```ruby
def dashboard
  @orders  = Order.recent.load_async
  @stats   = Stat.for_today.load_async
  @alerts  = Alert.open.load_async   # 3 queries in parallel, not serial
end
```

  Worth it only when the action runs 2+ slow independent queries; requires
  spare DB pool connections.
- **Indexes** — every foreign key, every column in a frequent WHERE/ORDER.
  Missing indexes dwarf every other optimization; check with `EXPLAIN`
  (`Product.where(...).explain(:analyze)`).

## 5. Runtime performance: YJIT, jemalloc, Puma, Thruster

The generated Dockerfile already does the right things — keep them:

- **YJIT** enabled by default under `load_defaults 8.1` on Ruby 3.3+ (and via
  the Dockerfile env). 15–25% faster request processing for free. ZJIT
  (Ruby 4.0) remains experimental — do not enable in production.
- **jemalloc** preloaded via `LD_PRELOAD` in the Dockerfile — dramatically
  reduces memory fragmentation in multithreaded Puma. Keep it.
- **Puma sizing** — `WEB_CONCURRENCY` (processes) × `RAILS_MAX_THREADS`
  (threads, default 3). Start with processes = physical cores, threads = 3;
  raise threads only for IO-heavy apps; more threads past ~5 mostly adds
  GVL contention and memory. The default `puma.rb` reads both env vars.
- **Thruster** in front of Puma (`bin/thrust bin/rails server` in the
  Dockerfile CMD) provides HTTP/2, TLS via Let's Encrypt, gzip compression,
  X-Sendfile acceleration, and **public asset caching** — so Rails is not
  re-serving `/assets/*` on every request. No config needed, no nginx to run.

## 6. Measuring: profiling and load testing

- Development: `rack-mini-profiler` badge per page (+ `stackprof` for
  `?pp=flamegraph`); server log line
  `Completed 200 OK in 312ms (Views: 240ms | ActiveRecord: 60ms)` tells you
  which half to attack first.
- Production: an APM riding the instrumentation hooks
  (`observability.md` §7) — optimize the endpoints that are slow *at p95 for
  real traffic*, not the ones that feel slow locally.
- Before capacity decisions, load-test a production-like deploy (`oha`, `wrk`,
  or `ab` against a staging Kamal destination) and tune `WEB_CONCURRENCY` /
  threads from measurements, not folklore.

## 7. Performance workflow

1. Measure first (§6). Views slow → fragment caching; ActiveRecord slow →
   N+1s and indexes.
2. Fix queries before adding caches — a cache over an N+1 hides a bug.
3. Cache in this order: HTTP caching (cheapest) → fragment caching →
   low-level caching. Each layer only where measurements justify it.
4. Verify with `bin/rails dev:cache` on and realistic data volumes
   (`db/seeds.rb` should create enough rows to expose N+1s).

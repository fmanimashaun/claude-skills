# Models: Migrations, Active Record, and Querying

## Contents
1. Migrations
2. Model anatomy and Active Record basics
3. Validations
4. Callbacks (and their limits)
5. Associations
6. Enums, normalization, tokens, store
7. Rich domain models the Rails way (concerns, POROs, delegated types)
8. Query interface
9. N+1s and eager loading
10. Transactions, locking, bulk writes
11. Encryption, multiple databases
12. Display numbers — the id a person reads (`TSK-0001`)
13. Fixing a slow query: index and query-rewrite techniques (the order of fixes is `performance-caching.md` §7)

---

## 1. Migrations

Generators infer intent from names: `AddXToY`, `RemoveXFromY`, `CreateY`,
`AddJoinTableXY`. Column modifiers ride along:
`bin/rails g migration AddDetailsToProducts 'price:decimal{10,2}' supplier:references{polymorphic}`.

```ruby
class CreateProducts < ActiveRecord::Migration[8.1]
  def change
    create_table :products do |t|
      t.string  :name, null: false
      t.decimal :price, precision: 10, scale: 2, null: false, default: 0
      t.references :supplier, null: false, foreign_key: true   # bigint + index
      t.integer :status, null: false, default: 0
      t.timestamps
    end
    add_index :products, :name, unique: true
  end
end
```

Rules of the road:

- **Constraints belong in the database**: `null: false`, `default:`, unique
  indexes for anything with `uniqueness:` validation, `foreign_key: true` for
  every `references`. Validations are UX; constraints are integrity.
- Prefer `change` with reversible operations; use `up`/`down` or
  `reversible { |d| d.up {...}; d.down {...} }` when not auto-reversible.
  Wrap raw SQL or destructive ops accordingly.
- **Never reference model classes in migrations** for data changes in ways
  that break when the class evolves — for data migrations, define a minimal
  inline model or use `execute`/`update_all`, and consider a separate data
  task for big backfills.
- `schema.rb` is authoritative and generated — never hand-edit; load fresh
  DBs with `db:prepare`/`db:schema:load`, not by replaying years of
  migrations. Switch to `structure.sql`
  (`config.active_record.schema_format = :sql`) only when using DB features
  schema.rb can't express (Postgres extensions, triggers). 8.1.0–8.1.3
  dumped schema.rb columns alphabetically; 8.1.4 reverted it, so columns are
  in definition order again, with no option to opt back in (activerecord
  CHANGELOG, v8.1.4).
- Other useful ops: `change_column_null`, `change_column_default from:/to:`
  (reversible), `rename_column` (on a table the running app uses, only as the
  last step of an expand–contract sequence: new column, dual-write, backfill,
  switch reads, stop writing, then `ignored_columns` and drop; per the
  strong_migrations README), `add_check_constraint`,
  `create_join_table`, `t.virtual` (generated columns),
  `disable_ddl_transaction!` + `add_index ..., algorithm: :concurrently`
  for big Postgres tables.

Commands: `db:migrate`, `db:rollback STEP=2`,
`db:migrate:redo`, `db:migrate:status`, `db:migrate VERSION=...`.

## 2. Model anatomy

The order a reader expects: associations, attachments, enums and normalization, validations and
scopes as declarations at the top, then domain behaviour as methods. The model below shows the
shape; its names are placeholders:

```ruby
class Product < ApplicationRecord
  belongs_to :supplier
  has_many :line_items, dependent: :destroy
  has_one_attached :photo

  enum :status, { draft: 0, active: 1, archived: 2 }, default: :draft
  normalizes :name, with: ->(name) { name.squish }

  validates :name, presence: true, uniqueness: true
  validates :price, numericality: { greater_than_or_equal_to: 0 }

  scope :visible, -> { active.where(archived_at: nil) }

  def discounted(pct) = price * (1 - pct / 100.0)
end
```

Conventions: class singular CamelCase ↔ table plural snake_case; `id` bigint
PK; `created_at`/`updated_at` maintained automatically; FK `<assoc>_id`.
Override only when wrapping legacy schemas (`self.table_name=`,
`self.primary_key=`). `ApplicationRecord` is the shared base — put app-wide
model behavior there.

## 3. Validations

Run on `save/create/update` (not `update_column`, `insert_all`, `delete`).
Check with `valid?`; read `errors.full_messages` /
`record.errors[:field]`.

Common validators: `presence`, `uniqueness` (+ `scope:`,
`case_sensitive:` — always back with a DB unique index),
`numericality` (`only_integer`, `in: 1..10`), `length` (`minimum:`,
`maximum:`, `in:`), `format: { with: /regex/ }`, `inclusion`/`exclusion`
(`in:`), `comparison: { greater_than: :starts_at }`, `confirmation`,
`acceptance`, `absence`. Associated records: `validates_associated` (avoid
on both sides — loops).

Options everywhere: `on: :create` / custom contexts
(`record.save(context: :import)`), `if:/unless:` (symbol or lambda),
`allow_nil:`, `allow_blank:`, `message:` (string or proc; i18n via
`errors.messages.*`).

Custom:

```ruby
validate :publishable_window
def publishable_window
  errors.add(:publish_at, "must be in the future") if publish_at&.past?
end
# reusable: class EmailValidator < ActiveModel::EachValidator; def validate_each(rec, attr, val)...
```

Errors carry types (`errors.added?(:name, :blank)`) — assert on types in
tests, not English strings.

## 4. Callbacks — use with restraint

Lifecycle: `before_validation → after_validation → before_save →
before_create/update → around_* → after_create/update → after_save →
after_commit/after_rollback` (+ `before/around/after_destroy`,
`after_touch`, `after_initialize`, `after_find`).

Good uses: defaulting/normalizing own attributes, maintaining derived
columns, enqueueing a job about *this* record
(`after_create_commit :send_welcome_email_later`). Prefer
`after_*_commit` for anything that leaves the process (jobs, mail,
broadcasts) — plain `after_save` fires before the transaction commits and the
job may not find the record. To run one method on create and on update, use
`after_save_commit :sync`; declaring `after_create_commit :sync` and
`after_update_commit :sync` with the same method name registers only the last
(both alias `after_commit`, which replaces an earlier callback of that name).

Avoid: touching other aggregates, conditional business branching, anything
you'll need to skip constantly. Halting: `throw :abort` in a `before_*`
callback cancels the save (`save` → false, `save!` → raises
`RecordNotSaved`). Callback objects (`after_commit PictureFileCallbacks.new`)
keep fat callbacks testable.

## 5. Associations

```ruby
belongs_to :author, counter_cache: true, touch: true          # required by default (optional: true to relax)
has_many   :comments, dependent: :destroy                     # or :destroy_async (via Active Job), :nullify, :delete_all
has_many   :commenters, through: :comments, source: :user
has_one    :profile, dependent: :destroy
has_and_belongs_to_many :tags                                 # prefer has_many :through when the join needs attributes
belongs_to :imageable, polymorphic: true                      # imageable_type + imageable_id (+ combined index)
has_many   :legacy_notes, deprecated: true                    # 8.1: reports every usage (:warn default, :raise, :notify)
```

Key options: `class_name:`/`foreign_key:` for nonstandard names,
`inverse_of:` when Rails can't infer it (custom FK/`:through` + scopes),
`dependent:` on the owning side, `counter_cache: true` (add the
`*_count` column, backfill with `Model.reset_counters`), `touch: true` to
bust russian-doll caches, association scopes
(`has_many :recent_comments, -> { order(created_at: :desc).limit(5) },
class_name: "Comment"`).

Association API adds `collection <<`, `build`, `create!`, `destroy`,
`ids`, `exists?`, plus singular `build_profile`/`create_profile!`.
`self-join`: `belongs_to :manager, class_name: "Employee", optional: true` +
`has_many :subordinates, class_name: "Employee", foreign_key: :manager_id`.

**Delegated types** (Rails-way alternative to STI for heterogeneous
collections):

```ruby
class Entry < ApplicationRecord
  delegated_type :entryable, types: %w[Message Comment], dependent: :destroy
end
module Entryable
  extend ActiveSupport::Concern
  included { has_one :entry, as: :entryable, touch: true }
end
```

STI (`type` column) is fine when subclasses share nearly all columns.

## 6. Enums, normalization, tokens, store

```ruby
enum :status, { draft: 0, active: 1 }, default: :draft, validate: true
# gives: product.active?  product.active!  Product.active  Product.not_active
# (on Rails main, unreleased, `not_active` also returns NULL rows: references/rails-8-2-readiness.md)
# prefix:/suffix: to avoid clashes: enum :delivery, {...}, prefix: true

normalizes :email, with: ->(e) { e.strip.downcase }   # applies on assignment AND in finders/uniqueness

has_secure_token :api_key                              # 24-char unique token column
generates_token_for :unsubscribe, expires_in: 30.days  # stateless signed tokens
# t = user.generate_token_for(:unsubscribe); User.find_by_token_for(:unsubscribe, t)

store_accessor :settings, :theme, :locale             # typed access into a json/jsonb column
```

Use integer-backed enums with explicit value hashes (never implicit arrays —
reordering corrupts data).

## 7. Rich domain models the Rails way

- **Concerns** (`app/models/concerns/`) extract cohesive traits:
  `Archivable`, `Searchable`. Use `included do ... end` for macros and keep
  each concern independently understandable. Model-specific concerns can live
  in `app/models/product/` (`Product::Pricing`).
- **POROs live in `app/models` too** — not everything is a table:
  `PriceQuote`, `Journey`, value objects via `composed_of` or plain classes.
  Include `ActiveModel::Model`/`ActiveModel::Attributes` to get validations,
  form binding, and casting on non-persisted objects (great for multi-model
  forms and search filters).
- **No service-object layer by default.** A verb wanting a home usually
  belongs on one of the nouns involved (`Subscription#cancel`,
  `Cart#checkout`), or is a job. If the project already has `app/services`,
  follow suit.

## 8. Query interface

```ruby
Product.find(1)                       # raises RecordNotFound
Product.find_by(slug: "x")            # nil if absent; find_by! raises
Product.where(status: :active, category: cats)         # IN for arrays/ranges
Product.where.not(supplier: nil).where(created_at: 1.week.ago..)
Product.where("lower(name) LIKE ?", "#{q.downcase}%")   # ALWAYS placeholders
Product.order(created_at: :desc).limit(20).offset(40)   # fine for small tables; at scale see §13 (keyset)
Product.select(:id, :name)            # a relation of partial records
Product.pluck(:name)                  # bare values, no models  (.pick = pluck + limit(1))
Product.distinct.count                # also: .sum(:price), .group(:status).count
Product.exists?(slug: "x")            # cheapest presence check
Product.find_each(batch_size: 500) { }  # batches; in_batches for relation chunks
Product.active.or(Product.where(featured: true))
Product.joins(:supplier).merge(Supplier.verified)       # reuse scopes across joins
Product.left_joins(:reviews).where(reviews: { id: nil })
Product.annotate("dashboard")         # SQL comment for slow-query forensics
Product.find_or_create_by!(sku:) { |p| p.name = name }  # or create_or_find_by for insert-first under unique index
```

- Scopes are composable and always return relations; class methods that can
  return nil break chains — prefer `scope`.
- Default scopes: almost never (they haunt updates, joins, and `unscoped`
  escapes).
- 8.1: `.first`/`.last` on relations with no inferable order is deprecated —
  order explicitly.
- Raw SQL escape hatches: `select("... AS computed")`,
  `from`, `find_by_sql`, `lease_connection.select_all` — keep them rare and
  parameterized.

## 9. N+1s and eager loading

```ruby
Post.includes(:author, comments: :reactions)   # let Rails pick preload vs eager_load
Post.preload(:author)                          # separate queries, always
Post.eager_load(:author)                       # LEFT JOIN, needed when where-ing on the association
Post.includes(:author).references(:authors).where("authors.name ILIKE ?", q)
```

Enforce discipline: `has_many :comments, strict_loading: true` per
association, `Post.strict_loading.first` per query, or globally
`config.active_record.strict_loading_by_default = true` in development to
surface every lazy load as an error (`:log` mode to warn instead).
`load_async` runs independent queries concurrently for dashboard-style
actions: `@a = Metric.heavy.load_async; @b = Other.heavy.load_async`.

## 10. Transactions, locking, bulk writes

```ruby
ApplicationRecord.transaction do
  order.confirm!
  inventory.decrement!(:stock)
end   # any raise rolls back; ActiveRecord::Rollback rolls back silently
```

- Side effects (mail, jobs, HTTP) go **after commit** — via
  `after_commit`/`after_create_commit` callbacks or by relying on Active
  Job's default enqueue-after-commit behavior (see jobs reference).
- Optimistic locking: add `lock_version` column → concurrent stale saves
  raise `ActiveRecord::StaleObjectError`. Pessimistic:
  `product.with_lock { ... }` (SELECT … FOR UPDATE inside a transaction).
- Bulk: `insert_all`, `upsert_all(rows, unique_by: :sku)` (skips
  validations/callbacks — you own integrity), `update_all`, `delete_all`,
  `touch_all`. 8.1 deprecates calling these through associations with
  unpersisted records.

## 11. Encryption and multiple databases

Attribute encryption (searchable-optional, key management via credentials —
`bin/rails db:encryption:init` to generate keys):

```ruby
class User < ApplicationRecord
  encrypts :ssn
  encrypts :email, deterministic: true   # allows where(email:) at the cost of equality-revealing ciphertext
end
```

Multiple databases (beyond the built-in Solid trio): define extra entries in
`database.yml` with `migrations_paths`, then:

```ruby
class AnalyticsRecord < ApplicationRecord
  self.abstract_class = true
  connects_to database: { writing: :analytics }
end
# replicas: connects_to database: { writing: :primary, reading: :primary_replica }
ActiveRecord::Base.connected_to(role: :reading) { ... }
```

Automatic read/write role switching for GET requests is available via
`config.active_record.database_selector`. Horizontal sharding uses
`connects_to shards: {...}` + `connected_to(shard: :one)`. Reach for these
only at real scale; the default single-primary + Solid databases covers most
apps.

## 12. Display numbers — the id a person reads (`TSK-0001`)

A person needs a way to name a record: to say it aloud, paste it into a chat, find it again. A raw
primary key or a UUID on screen does that job badly. So every **user-facing** model carries a
readable **display number** (#1274, maintainer decision):

- **The model declares its prefix**: three letters, unique across the app, such as `TSK`, `REQ` or
  `INV`.
- **The number is sequential and zero-padded to at least four digits.** The first is `TSK-0001`. The
  padding is a minimum width, not a cap, so record 10,000 is `TSK-10000`.
- **It is unique within its scope and never reused.** The scope is the tenant in a multi-tenant app,
  the way GitHub numbers issues per repository, so no customer sees another's volume. In a
  single-tenant app it is the whole app. A unique index on the scope and the number is the
  guarantee. Two concurrent creates must never receive the same number, and a collision must not
  abort the transaction around it. Prove both with a spec that creates concurrently. A deleted
  record's number is not handed out again, so gaps are expected.
- **Everywhere it is displayed, it is a link to the record**, in tables, headings, notifications,
  emails and audit logs. In a table index the link opens the record's details card in the modal frame
  rather than a show page, and the same URL followed directly renders that card over the list
  (`design-system` `components.md` → Table (CRUD)). A number that cannot be clicked sends the reader to search.
- **The URL keeps the opaque public id** (`multi-tenancy.md` §5). The display number shows how many
  records exist, which is harmless on screen but is exactly what an address must not reveal or let
  someone guess.
- **A raw primary key or UUID never reaches the screen.** Search accepts the display number, with or
  without its prefix.

Why a sequence and not a short hash: the first seven characters of a hex id collide with a
probability of 17% at 10,000 records and near certainty at 100,000. A sequence is shorter, reads
aloud, and is unique by construction.

## 13. Fixing a slow query: index and query-rewrite techniques

This section holds the **techniques**. The **order** to try them in, the evidence each needs and how to
prove the metric moved live in `performance-caching.md` §7: read that first, and do not skip ahead to a
technique because it is familiar. The statements about PostgreSQL and `add_index` / `remove_index` below were checked against the
PostgreSQL 16 docs and the Rails 8.1 API docs (`schema_statements`) on 2026-10-14; Active Record's other adapters
are not covered. The keyset recipe, the advice on rewrites and the summary-table paragraph are our own design
(#2039).

### Indexes

```ruby
add_index :orders, :customer_id, where: "billed = false"          # partial
add_index :accounts, [:branch_id, :party_id]                       # composite
add_index :accounts, :branch_id, include: :party_id                # covering (PostgreSQL only)
```

- **Partial** (`where:`; Rails supports it on PostgreSQL and SQLite only). The index holds only the rows the
  predicate selects, so it suits a query that always carries the same predicate on a small, hot part of a
  big table. PostgreSQL limits the predicate to the table's own columns: no subqueries, no aggregates.
- **Covering** (`include:`, PostgreSQL only). The extra columns are non-key: they cannot be searched on and
  play no part in uniqueness, but an index-only scan can return them without visiting the table, so a query
  that selects only the key and those columns can stop using the table. The index gets larger; add the columns
  a hot query actually returns, not every column.
- **Build on a big table without blocking writes**: `disable_ddl_transaction!` and `algorithm: :concurrently`
  (§1). A standard build locks out writes until it finishes. A concurrent build cannot run inside a
  transaction, and when it fails it leaves an **invalid** index that is ignored for queries but still costs
  writes: drop it and build again, or `REINDEX INDEX CONCURRENTLY`.
- **Roll back** with `remove_index :orders, name: :index_orders_on_customer_id, algorithm: :concurrently`
  (PostgreSQL only, not in a transaction), which runs `DROP INDEX CONCURRENTLY`. It takes one index at a time,
  cannot drop an index that backs a UNIQUE or PRIMARY KEY constraint, and does not work on a partitioned
  table. A plain `DROP INDEX` takes an ACCESS EXCLUSIVE lock on the table.
- Check that the plan actually uses the new index (`Order.where(...).explain(:analyze)`, or `EXPLAIN
  (GENERIC_PLAN)` below) before keeping it: an index nothing chooses is only write cost.

### Query rewrites

- **OFFSET to keyset.** PostgreSQL still computes the rows an `OFFSET` skips ("a large `OFFSET` might be inefficient"), so
  `offset(40)` does work for every earlier row and a deep page costs more than page 1. A keyset page asks for "the rows after the last one you showed":

```ruby
page = Product.order(:created_at, :id).limit(20)
page = page.where("(created_at, id) > (?, ?)", last.created_at, last.id) if last   # last = previous page's final row
```

  PostgreSQL compares a row constructor left to right, so `(created_at, id) > (a, b)` means `created_at > a`,
  or equal and `id > b`. Three consequences: end the order with a unique column (`id`) so no row is skipped or
  repeated; the comparison applies one operator to every column, so **all sort columns go the same direction**;
  and a NULL in the first pair that is not equal (a NULL leading sort column always is) makes the comparison
  unknown, so those rows drop out: keep the sort columns `NOT NULL`. The price is that a reader cannot jump to page 40.
- **A function on the column side** (`lower(name) = ?`) makes the comparison about the function's result: compare
  the bare column where the data allows, and check the plan before and after.
- **`COUNT` to `EXISTS`**: `exists?` for a yes/no question (§8); **`SELECT *` to `select`/`pluck`** (§8).
- **N+1** is §9, and **counter caches** are §5.

### Materialised view or summary table

When one expensive aggregate is read far more often than it changes, store its result.

- **Materialised view**: `REFRESH MATERIALIZED VIEW CONCURRENTLY name` refreshes without locking out readers, but
  needs at least one UNIQUE index on the view that uses only column names and covers all rows (no expression, no
  `WHERE`), cannot run on a view that is not yet populated (the first refresh is the plain form), cannot be
  combined with `WITH NO DATA`, and only one refresh at a time can run against a given view. The plain form
  can block readers. Run the statement through the connection (`lease_connection.execute`, §8), from a job.
- **Summary table**: a table your code updates itself (in the write path or a job). More code than a view, and
  the same staleness question.
- **How stale may the number be is a product rule**, not an engineering call: ask the owner and write the answer
  next to the view or table.

### Reading a plan you cannot run with real values

`EXPLAIN (GENERIC_PLAN) SELECT ... WHERE id > $1 AND id < $2` accepts parameter placeholders and returns a
**generic** plan that does not depend on the values. It is in the PostgreSQL 16 docs and not in 15 (docs compared
2026-10-14), and it **cannot be combined with `ANALYZE`**. A generic plan can differ from the custom plans a
prepared statement uses when the data is skewed, so label what you read as generic and confirm on a real value
with `explain(:analyze)`.

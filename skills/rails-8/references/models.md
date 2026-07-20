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
  schema.rb can't express (Postgres extensions, triggers). 8.1 alphabetizes
  columns in schema.rb.
- Other useful ops: `change_column_null`, `change_column_default from:/to:`
  (reversible), `rename_column`, `add_check_constraint`,
  `create_join_table`, `t.virtual` (generated columns),
  `disable_ddl_transaction!` + `add_index ..., algorithm: :concurrently`
  for big Postgres tables.

Commands: `db:migrate`, `db:rollback STEP=2`,
`db:migrate:redo`, `db:migrate:status`, `db:migrate VERSION=...`.

## 2. Model anatomy

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
job may not find the record.

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
Product.order(created_at: :desc).limit(20).offset(40)
Product.select(:id, :name)  /  .pluck(:name)  /  .pick(:name)
Product.distinct.count / .sum(:price) / .group(:status).count
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

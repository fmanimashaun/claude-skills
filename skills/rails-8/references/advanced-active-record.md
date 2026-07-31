# Advanced Active Record (Rails 8.1)

Deep-dives beyond `models.md`: composite primary keys, multiple databases and
sharding, and Active Record encryption. Reach for these only when the need is
real — each adds permanent complexity.

## Contents
1. Composite primary keys
2. Multiple databases (roles, shards, switching)
3. Full-text search in the database
4. Active Record Encryption

---

## 1. Composite primary keys

For legacy schemas or sharding/multitenancy where one column can't uniquely
identify a row. **Prefer a single `id` when you have the choice** — composite
keys are slower and complicate every layer.

### Migration and model

```ruby
create_table :products, primary_key: [:store_id, :sku] do |t|
  t.integer :store_id
  t.string  :sku
  t.text    :description
end
```

Active Record derives the composite key from the schema automatically; for
legacy tables declare it: `self.primary_key = [:store_id, :sku]`.

### Querying

```ruby
Product.find([3, "XYZ12345"])                       # one record
Product.find([[1, "ABC98765"], [7, "ZZZ11111"]])    # several — array of arrays
Product.where(Product.primary_key => [[1, "ABC98765"], [7, "ZZZ11111"]])  # tuple syntax
Product.first   # orders by the FULL composite key: store_id ASC, sku ASC
```

Trap: `find_by(id: ...)` / `where(id: ...)` match an **`id` column**, not the
composite primary key — on composite-PK models with an `id` column these are
different things. Use `find` (positional) for primary-key lookup.

### Associations

Rails won't infer composite foreign keys — declare both sides:

```ruby
class Order < ApplicationRecord
  self.primary_key = [:shop_id, :id]
  has_many :order_agreements, foreign_key: [:shop_id, :order_id]
end

class OrderAgreement < ApplicationRecord
  belongs_to :order, foreign_key: [:shop_id, :order_id]
end
```

(An array `foreign_key:` replaces the deprecated `query_constraints:` option.)

### Controllers, URLs, fixtures

- `to_param` joins key parts with `_` → URLs like `/products/3_XYZ12345`.
- Extract in controllers with `params.extract_value(:id)` →
  `["3", "XYZ12345"]`, then `Product.find(params.extract_value(:id))`.
- Forms: `form_with model: @product` works; the hidden id uses the composite
  param.
- Fixtures/factories: set every key column explicitly; there's no
  auto-generated id to lean on.

## 2. Multiple databases (roles, shards, switching)

Every Rails 8 app is already multi-DB (primary + queue + cache + cable — see
`project-setup.md`). This section is about *application* databases: replicas
and shards.

### Writer + replica

```yaml
# config/database.yml
production:
  primary:
    <<: *default
    database: myapp_production
  primary_replica:
    <<: *default
    database: myapp_production
    host: replica.internal
    replica: true          # read-only; skips migrations & schema dump
```

```ruby
class ApplicationRecord < ActiveRecord::Base
  primary_abstract_class
  connects_to database: { writing: :primary, reading: :primary_replica }
end
```

**Automatic role switching** (generate the initializer with
`bin/rails g active_record:multi_db`, then uncomment):

```ruby
Rails.application.configure do
  config.active_record.database_selector = { delay: 2.seconds }
  config.active_record.database_resolver = ActiveRecord::Middleware::DatabaseSelector::Resolver
  config.active_record.database_resolver_context = ActiveRecord::Middleware::DatabaseSelector::Resolver::Session
end
```

GET/HEAD requests read from the replica; anything else writes to primary; a
request within `delay` of a write sticks to primary (covers replication lag
for redirect-after-POST).

**Manual switching** when you need control:

```ruby
ActiveRecord::Base.connected_to(role: :reading) do
  Report.expensive_aggregate   # all queries in the block hit the replica
end
```

### Separate databases per domain

```yaml
  animals:
    <<: *default
    database: myapp_animals
    migrations_paths: db/animals_migrate
```

```ruby
class AnimalsRecord < ApplicationRecord
  self.abstract_class = true
  connects_to database: { writing: :animals }
end
class Dog < AnimalsRecord; end
```

Per-DB tasks appear automatically: `db:create:animals`,
`db:migrate:animals`, and generators accept `--database animals`. Schema
files are per-DB (`db/animals_schema.rb`). **No cross-database joins** —
`joins` across connections fails; use two queries + in-memory stitching, or
`disable_joins: true` on `has_many ... through:` associations that span DBs.

### Horizontal sharding

Same schema, many databases:

```ruby
class ApplicationRecord < ActiveRecord::Base
  primary_abstract_class
  connects_to shards: {
    default: { writing: :primary, reading: :primary_replica },
    shard_one: { writing: :shard_one, reading: :shard_one_replica }
  }
end

ActiveRecord::Base.connected_to(shard: :shard_one) do
  Order.create!(...)   # lands in shard_one
end
```

Automatic per-request shard selection via `config.active_record.shard_selector
= { lock: true }` + a `shard_resolver` lambda (e.g. resolve tenant from
subdomain). Sharding is a last resort — exhaust indexing, caching, and
read-replicas first.

Testing note: point each abstract class's role at the right test database in
`database.yml`; parallel tests create per-worker copies of **all** configured
databases.

## 3. Full-text search in the database (#98)

**Start in PostgreSQL.** `ecosystem-gems.md` §7 names the gems; this is the mechanism, its limits, and
the point at which the database stops being the right answer.

### The column, and the trigger you should no longer write

`tsvector` + a **GIN** index is the mechanism. Maintain the column with a **stored generated column**,
not a trigger — PostgreSQL's own documentation retired the trigger approach:

> *"The method described in this section has been obsoleted by the use of stored generated columns."*

```ruby
# Generated columns: PostgreSQL 12+. `t.virtual … stored: true` is Rails 7.0+.
create_table :documents do |t|
  t.string :title
  t.text   :body
  t.virtual :searchable, type: :tsvector, stored: true,
            as: "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,''))"
end
add_index :documents, :searchable, using: :gin
```

**Rails gives you the schema layer and no query builder.** There is no Active Record API for full text
— querying is a raw fragment, which is correct and worth knowing rather than hunting for:

```ruby
Document.where("searchable @@ to_tsquery('english', ?)", "cat & dog")
```

So **`pg_search` is for ergonomics, not necessity** — ranking, prefix matching, multi-column weights.
It works either way: query-time `to_tsvector` by default, or against a precomputed column, and its own
README notes the column *"speeds up searching dramatically"*. Status to be accurate about: last tagged
release **2.3.7 (Aug 2024)**, `activerecord >= 6.1` with no upper bound, repo active in 2026 — so it is
compatible by that floor rather than by a Rails 8 certification.

> **Name collision worth knowing.** There is also a **PostgreSQL extension** called `pg_search`
> (ParadeDB/Neon) that implements BM25 via tantivy. Different thing entirely from the Ruby gem our
> doctrine means. If you read a blog comparing "pg_search" to Elasticsearch, check which one.

### Do NOT shard a Postgres search index the way MySQL forces you to

Canonical practice here is **adapter-specific and does not transfer**. 37signals' fizzy shards its
search table **16 ways by CRC32 of the account id** — on MySQL. That is forced: MySQL documents that
*partitioned tables do not support `FULLTEXT` indexes or searches*, so anyone wanting a partitioned
full-text table on MySQL is pushed out of native partitioning and into application-level table
splitting.

**PostgreSQL has no such constraint.** Indexes on partitioned tables arrived in **PostgreSQL 11** — a
`CREATE INDEX … USING gin` on the parent is a template that propagates to every partition, present and
future. So declarative partitioning plus one GIN index gets the locality without any app-level shard
router. Copying the 16-way scheme onto Postgres would be inheriting a workaround for a limitation we do
not have. (The one real GIN restriction is unrelated: it cannot back an `EXCLUDE` constraint, on any
table.)

### When the database stops being enough — documented limits first

**Quotable, from PostgreSQL:**

- **GIN write amplification** — *"Updating a GIN index tends to be slow because of the intrinsic nature
  of inverted indexes: inserting or updating one heap row can cause many inserts into the index."*
  `fastupdate` defers some of it; for very large updates the docs suggest dropping and recreating.
- **Hard ceilings** — a `tsvector` under **1 MB**, each lexeme under **2 KB**, a `tsquery` under
  **32,768** nodes. Rarely reached, but real.

**Practitioner consensus, and labelled as such because no PostgreSQL document says it:**

- **Ranking.** `ts_rank` is term-frequency based with no corpus-wide IDF, so no BM25. Fine for "find
  the matching invoice", weak for relevance-ranked search over a large corpus.
- **Typo tolerance.** None natively; it means adding `pg_trgm`, a separate extension.
- **Faceting.** No native faceted counts — hand-rolled `GROUP BY` queries that get expensive.

**So: reach for Elasticsearch/OpenSearch/Meilisearch when you need BM25-quality ranking, typo
tolerance, or faceting at scale** — not because Postgres "cannot do search". Adding a search cluster is
a permanent operational commitment; the bar is a measured need, not an anticipated one.

## 4. Active Record Encryption

Application-level (in addition to at-rest disk) encryption for sensitive
columns — values are encrypted before SQL, so DB dumps and logs never see
plaintext.

### Setup

```bash
bin/rails db:encryption:init
# → paste output into bin/rails credentials:edit
active_record_encryption:
  primary_key: ...
  deterministic_key: ...
  key_derivation_salt: ...
```

### Declaring encrypted attributes

```ruby
class User < ApplicationRecord
  encrypts :medical_notes                            # non-deterministic (default, strongest)
  encrypts :email_address, deterministic: true       # same plaintext → same ciphertext → queryable
  encrypts :nin, deterministic: true, downcase: true # normalize before encrypting
end

User.find_by(email_address: "fisayo@example.com")   # works ONLY for deterministic
```

- Non-deterministic (random IV) for anything you never query by; deterministic
  only for exact-match lookup columns. Deterministic can't do `LIKE`.
- `ignore_case: true` (with an extra `original_<name>` column) preserves the
  original casing while querying case-insensitively.
- Columns should be `text` (or extend string limits ~4× — ciphertext + metadata
  is larger). For unique indexes on deterministic columns the index works as
  normal because equal plaintexts produce equal ciphertexts.
- Encrypted attributes are automatically added to `filter_parameters`.
- Action Text: `has_rich_text :content, encrypted: true`.

### Migrating existing data

```ruby
# 1. Deploy with both allowed:
config.active_record.encryption.support_unencrypted_data = true
# 2. Backfill:
User.where.not(medical_notes: nil).find_each(&:encrypt)   # or save! per record
# 3. Flip support_unencrypted_data to false once backfilled.
```

### Key rotation

List previous keys and Rails tries newest-first for decryption while
encrypting with the current key:

```yaml
active_record_encryption:
  primary_key:
    - old_key
    - new_key      # last = current for encrypting
```

Re-encrypt lazily on save or eagerly with a backfill loop. For
enterprise-grade setups a custom `key_provider` (envelope encryption per
record) can be configured via
`config.active_record.encryption.key_provider = ActiveRecord::Encryption::EnvelopeEncryptionKeyProvider.new`.

When to use: PII/PHI columns (national IDs, medical data, tokens), compliance
regimes (NDPA/GDPR "appropriate technical measures"). When not to: passwords
(`has_secure_password` already hashes — hashing ≠ encryption and is correct
there) and columns you need range/LIKE queries on.

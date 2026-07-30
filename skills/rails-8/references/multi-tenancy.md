# Multi-tenancy — row-level isolation, session-selected tenant

**Rails has no doctrine for this.** The guides' only use of the phrase "multi-tenant" is about
*horizontal sharding* — separate databases with the same schema. Shared-schema, row-level tenancy is
undocumented upstream, so **everything here that is a choice is recorded as a choice**, and everything
that is a framework fact is cited to source.

## Two axes. Never conflate them

Almost every muddled tenancy discussion is these two questions collapsed into one:

| Axis | Question | Options |
|---|---|---|
| **Isolation** | how is one tenant's data kept from another's? | separate database · separate schema · **row-level (shared schema, tenant FK)** |
| **Identification** | how does a request say which tenant it is for? | subdomain · URL path prefix · **session** · header |

They are independent. You can have row-level isolation with any identification scheme. Choosing
"subdomain" says **nothing** about how your queries are scoped, and that is exactly the confusion this
file exists to prevent.

**Our decisions: row-level isolation, session-selected identification.** Reasoning below.

---

## 1. Identification — session-selected, and the tenant is never in the URL

**The decision, with its reasoning, from fidara-ledger's decision register (D-009, accepted
19 Jul 2026):**

> *"The active organization is resolved from the signed-in user's membership and held in the session;
> URLs never name the org; multi-org users switch via a dropdown."*

Three reasons, in the order they actually mattered:

1. **It is the category norm.** Xero, QuickBooks, Wave, Zoho and FreshBooks all use an org switcher, not
   subdomains or path prefixes. For accounting and invoicing software, users expect a switcher.
2. **The alternative's main benefit did not apply.** Subdomains earn their cost when external users
   inhabit a standing per-tenant space. Ledger's external users hit **one-off tokenized links**, so
   there is no standing space to name.
3. **It is the most reversible.** Path-based (`/acme/…`) and subdomain (`acme.…`) tenancy can both be
   layered on later — for white-labelling, say — **without a data-model change**. Starting with either
   and backing out is the expensive direction.

### Subdomains are still used — for *planes*, not tenants

D-012 splits the app across three hosts: the **root domain** for marketing, **`app.`** for the tenant
product, **`admin.`** for the platform/operator console. `app.` is *"a single fixed application host —
**not** per-tenant subdomains"*.

Route it with `constraints subdomain:` plus `scope module:` — **not `namespace`** — so the host decides
which controller answers while the URLs stay identical:

```ruby
constraints subdomain: "app" do
  scope module: :tenant, as: :tenant do
    # the whole tenant product
  end
end

constraints subdomain: "admin" do
  scope module: :admin, as: :admin do
    # platform staff only — a separate identity and session
  end
end
```

**Each plane gets its own authentication stack, not a role check on a shared one.** Separate cookie,
separate `Current.*` attributes, and the staff stack only ever runs on the `admin.` host — so **a tenant
session grants zero admin access** structurally, rather than because a `before_action` remembered to
check. Keep the tenant concern off `ApplicationController` so the admin and public planes cannot
inherit it by accident.

### Do not trust the session value blindly

The session is server-controlled, which is most of why this scheme is safe — but the id in it still has
to be **re-authorised against the user's own memberships on every request**, because a session can
outlive a membership that was revoked:

```ruby
class Tenant::BaseController < ApplicationController
  include Authentication
  before_action :set_current_organization

  private
    # Resolved from the session ONLY — never from params or the URL.
    def set_current_organization
      return unless Current.user

      # `Current.user.organizations` is the authorisation: a session naming an org
      # the user is not a member of simply finds nothing.
      organization = Current.user.organizations.find_by(id: session[:organization_id])
      organization ||= Current.user.organizations.first.tap do |fallback|
        session[:organization_id] = fallback&.id
      end

      Current.organization = organization
      Current.membership = Current.user.memberships.find_by(organization: organization) if organization
    end
end
```

**The load-bearing detail is `Current.user.organizations`, not `Organization.find`.** Scoping the lookup
through the user's own association means an unauthorised org id cannot resolve at all. Written as
`Organization.find_by(id: session[:organization_id])` this same code would be a tenant-switching hole.

### If you do put the tenant in the URL — the mechanism, verified

Should a project need path-based tenancy later, this is the shape that works, and the reason it works is
worth knowing rather than copying blindly. A middleware moves the prefix from `PATH_INFO` to
`SCRIPT_NAME`:

```ruby
# Yank the prefix off PATH_INFO and move it to SCRIPT_NAME, so Rails
# behaves as though the app were mounted at that path.
request.engine_script_name = request.script_name = matched_prefix
request.path_info = remainder.presence || "/"
```

**Why every URL helper then just works:** `ActionController::UrlFor#url_options` merges
`options[:script_name] = request.script_name.dup` into every controller's `url_options`, and
`ActionDispatch::Http::URL.path_for` prepends it. So `*_path` / `*_url` / `url_for` re-emit the prefix
with no tenant argument anywhere. (Verified against Rails 8.1 source, not inferred.)

**Four things that do not come for free, and all four bite in production:**

- **Mailers get nothing.** Mailers have no request, so no `SCRIPT_NAME`. Rails' own docs say you must
  supply `:host`/`default_url_options` yourself. You need `default_url_options` to merge
  `script_name: Current.account.slug` **and** the tenant restored before the mailer renders — which
  means inside the delivery job, since that is where rendering happens.
- **Asset paths never inherit it.** Assets honour only the static `config.relative_url_root`. That is
  correct — assets are tenant-independent — but it means page URLs and asset URLs use two different
  mechanisms. Do not "fix" the asset paths.
- **Tenant-agnostic routes need `script_name: nil` explicitly.** Login and account-switch screens must
  *not* carry the current prefix, or Rails will helpfully re-prepend whichever tenant the request
  happened to arrive under.
- **Isolated engines are a known Rails gap** ([rails/rails#6933]) — an isolated engine calling
  `main_app.*_url` does not pick up the host's `SCRIPT_NAME`, which is why real implementations set
  `engine_script_name` as well as `script_name`.

[rails/rails#6933]: https://github.com/rails/rails/issues/6933

### Subdomain-per-tenant: the real trade-off, since it is the popular default

Not wrong — but pick it for a reason, not by habit:

- **Origin isolation is the genuine win.** An origin is scheme + host + port; **the path is not part of
  it**. So path-based (and session-based) tenants share one origin, meaning shared `localStorage` and
  `IndexedDB` — an XSS in one tenant's page can read another tenant's storage. Subdomains are separate
  origins and get browser-enforced isolation for free.
- **The cost is inverted infrastructure.** Wildcard DNS plus a wildcard/SAN certificate, and it does not
  work on `localhost` without `lvh.me` or `/etc/hosts` tricks. Path- and session-based need neither.

---

## 2. Isolation — scope through associations. Do not reach for `default_scope`

**Scope from the tenant, always:**

```ruby
Current.organization.invoices.find(params[:id])     # yes
Invoice.find(params[:id])                           # a cross-tenant read waiting to happen
```

This is **Rails' own idiom**, not merely a house style — `ActiveSupport::CurrentAttributes`' own
documentation uses exactly this shape (`Current.account.messages.create(…)`), alongside a warning worth
heeding: *"It's easy to overdo a global singleton like Current and tangle your model as a result.
Current should only be used for a few, top-level globals, like account, user, and request details."*

**Two production apps by relevant authors contain zero `default_scope`:** fidara-ledger (grepped, none)
and 37signals' fizzy (grepped, none — it scopes by association traversal and explicit
`where(account_id:)`). That is evidence, not proof, but it is the direction the evidence points.

### Why not `default_scope` — five verified hazards, not folklore

Every one of these was confirmed against Rails 8.1 source or by running it:

1. **A wrong-tenant lookup returns `nil`, not an error.** `find_by` silently misses, so controllers and
   tests read a blocked cross-tenant attempt as "not found". You lose the signal exactly where you
   wanted it loudest.
2. **It leaks into `new`/`create`.** A hash-shaped `default_scope` sets attributes on new records. Handy
   when `Current` is set; when it is `nil` you get a row with a null tenant FK and only a database
   `NOT NULL` constraint between you and orphaned data. **The constraint is the real safety net — add
   it regardless of which approach you choose.**
3. **`unscoped` bypasses it entirely**, and so does anything that goes through `unscoped` internally —
   including the one in §3, which is the dangerous case.
4. **It is evaluated when a `Relation` is constructed, not when the query runs.** A relation built under
   tenant A still reads tenant A after `Current` changes — verified by running it. Fine for ordinary
   controller actions that build fresh relations; **wrong** for a memoized class-level relation, a
   relation captured in a closure, or one handed across a thread or job boundary.
5. **`joins` with `default_scope` has a long tail of open Rails bugs** — nested and `through`
   associations, `includes`-versus-`joins`, `unscope` on `through` associations. The simple case works;
   the combinations are a minefield spanning Rails 4.2 to 7.2.

**The trade-off, stated honestly.** Association traversal avoids all five *by construction*, and costs
**discipline** — every query must go through the tenant, and nothing enforces that automatically.
`default_scope` (or `acts_as_tenant`, which is built on it) buys automatic scoping and inherits all
five. Neither is free. **Our decision is association traversal**, because the failure mode of
forgetting to scope is a code-review-visible missing `Current.organization.`, whereas the failure modes
above are invisible.

---

## 3. The job boundary — where tenant scoping actually breaks

This section is the one to read twice. Two verified facts combine into a hole that neither is obvious
about alone.

**Fact one: `Current` never survives the enqueue → perform boundary.**
`ActiveSupport::CurrentAttributes` *"resets automatically before and after each request"*, and ActiveJob
wraps every execution in the reloader, so `CurrentAttributes.clear_all` runs around every job. Rails
ships **no** built-in carrier — its own documented answer is to pass what you need as a job argument and
call `Current.set(…) { }` inside `perform` by hand.

**Fact two: GlobalID deliberately unscopes.** Our own doctrine says to pass **records** to jobs, which
serialises them as GlobalIDs. GlobalID's default locator is an `UnscopedLocator`:

```ruby
class UnscopedLocator < BaseLocator
  def locate(gid, options = {})
    unscoped(gid.model_class) { super }
  end
end
```

That has been the default since 2016, chosen on purpose so a record excluded by a scope can still be
located and processed.

**Therefore: `default_scope` provides *zero* protection for a record arriving as a job argument.** Not
"depends on ordering" — structurally none, by GlobalID's own design. And the ordering makes it worse:
`ActiveJob::Execution#perform_now` runs `deserialize_arguments_if_needed` **before**
`run_callbacks :perform`, so `before_perform` and `around_perform` **cannot** influence argument
deserialization. A tenant restored in `around_perform` is restored too late.

**What to do:**

- **Restore tenant context in the job's `deserialize(job_data)`**, not `around_perform`. That is the
  earliest hook and it runs before argument deserialization. (`around_enqueue` is producer-side and
  irrelevant here.)
- **Re-check tenancy explicitly inside `perform`** for any tenant-scoped record that arrived as an
  argument, whenever cross-tenant smuggling is a real threat:

  ```ruby
  class Invoice::DeliverJob < ApplicationJob
    def perform(invoice)
      # Nothing upstream enforced this. GlobalID located the record unscoped.
      raise ActiveJob::DeserializationError unless invoice.organization_id == Current.organization&.id
      invoice.deliver_now
    end
  end
  ```

- **Carry the tenant as its own serialised value**, not as an implicit ambient. Capture it at enqueue
  time so a retry re-resolves the *same* tenant rather than whatever the worker happens to hold.
- **Be careful with `discard_on ActiveJob::DeserializationError`.** `jobs-and-realtime.md` offers it for
  "record deleted before run — fine to drop". In a tenant-scoped job the same error also means *"the
  tenant vanished mid-flight"*, which is a materially more serious event. Decide per job; do not blanket
  it. (37signals' fizzy leaves this line deliberately commented out.)

---

## 4. PostgreSQL Row-Level Security — defence-in-depth, with one trap that makes it inert

RLS (PostgreSQL 9.5+) lets the database itself filter rows, so a missed `WHERE` cannot leak data. As a
second layer under application scoping it is genuinely valuable. **Never as the only layer**, and never
without knowing this:

> *"Superusers and roles with the `BYPASSRLS` attribute always bypass the row security system…
> **Table owners normally bypass row security as well**, though a table owner can choose to be subject
> to row security with `ALTER TABLE … FORCE ROW LEVEL SECURITY`."*

**A Rails app usually owns the tables its own migrations created.** So the default outcome is: policies
defined, `ENABLE ROW LEVEL SECURITY` run, and **RLS doing nothing at all**, silently. Ownership bypass
is unrelated to `BYPASSRLS`, so checking that your role lacks `BYPASSRLS` proves nothing.
**`FORCE ROW LEVEL SECURITY` is the lever that matters.**

Setting the tenant per request:

- Use **`SET LOCAL`** or `set_config(…, true)` — transaction-scoped. A bare `SET` is session-scoped and
  **leaks to the next tenant** that lands on the same pooled connection.
- `SET LOCAL` outside a transaction *"emits a warning and otherwise has no effect"* — a silent no-op, so
  it must be inside `ActiveRecord::Base.transaction`.
- Under **PgBouncer transaction pooling** this is the only safe choice; PgBouncer's own docs say clients
  *"must not use any session-based features"* in that mode.

**When not to bother:** if the app role owns the tables and you will not set `FORCE`, RLS is theatre.
Also note that *"referential integrity checks, such as unique or primary key constraints and foreign key
references, always bypass row security"*, so RLS cannot be your only defence against FK-adjacent leaks —
that last point is our reading of the docs' caveat, not a quoted rule.

---

## 5. Identifiers — what goes in a URL when the tenant does not

With the org out of the URL, records still need public identifiers. **Sequential integer PKs in URLs
leak volume and ordering, and invite enumeration.** Two sound answers:

### Ours: keep the PK, mint an opaque public id, let the database guarantee it

fidara-ledger mints a prefixed random `public_id` before validation on create, and treats the
**unique index as the guarantee** rather than trusting entropy:

```ruby
PUBLIC_ID_PREFIX = "ORG-".freeze
MAX_PUBLIC_ID_MINT_ATTEMPTS = 5

before_validation :mint_public_id, on: :create

private
  # Only a SELF-MINTED id is retried on collision — a caller-supplied value is
  # never silently rewritten, so a real duplicate surfaces the actual error.
  def mint_public_id
    return if public_id.present?
    self.public_id = generate_public_id
    @public_id_minted = true
  end

  def generate_public_id
    "#{PUBLIC_ID_PREFIX}#{SecureRandom.alphanumeric(10).upcase}"
  end
```

Three details that make this better than `has_secure_token`, and worth copying:

- **The unique index is the guarantee**, with a bounded retry on collision — uniqueness is a hard
  property of the schema, not a probabilistic hope about entropy.
- **Match the specific unique violation**, by index name rather than by sniffing the error message, so a
  future unrelated unique constraint on the same table cannot be misread as a public-id collision.
- **Only retry a self-minted value.** A caller-supplied duplicate must surface the real
  `ActiveRecord::RecordNotUnique` rather than being silently rewritten.

### The alternative: UUID primary keys — and the version boundaries matter

37signals' fizzy uses UUID PKs throughout. Viable, but four facts first:

- **`id: :uuid` is native to PostgreSQL only.** MySQL and SQLite have no `uuid` entry in their Rails
  adapters' native types at all — hence the third-party gems and fizzy's ~170 lines of custom type code.
- **PostgreSQL's default `gen_random_uuid()` is UUID *version 4* — random.** Random PKs scatter B-tree
  inserts, causing page splits and index bloat. This is the real objection to UUID PKs.
- **No Rails version generates UUIDv7.** Time-ordered UUIDv7 (RFC 9562) fixes the locality problem
  because its leading millisecond timestamp clusters inserts at the right edge of the index, like a
  sequence. It comes from **`SecureRandom.uuid_v7`, Ruby ≥ 3.3**, called by your app — or natively from
  **PostgreSQL ≥ 18**'s `uuidv7()`. Rails' own docs invite you to swap the function in; they do not do
  it for you.
- **16 bytes versus 8 for a bigint**, and that doubling repeats on every FK column referencing it.

**When not to use UUID PKs:** if you never merge data across databases and never expose PKs in URLs,
`bigint` plus a public token gets most of the benefit at none of the write-locality or storage cost.
"base36-encoded, 25 chars" is fizzy's own storage scheme, not a standard — RFC 9562's canonical form is
the 36-char hyphenated hex string.

---

## 6. Gems, and why we hand-roll

- **`acts_as_tenant`** — row-level, actively maintained, and honest that it *"uses Rails'
  `default_scope` method to scope models"*. Choosing it does not avoid §2's hazards; it centralises them
  behind a tested implementation. Note its own open issues at the ActiveJob boundary, including one
  specifically about **Solid Queue** — our default adapter — where the tenant is missing from the stored
  job payload. §3 is not theoretical.
- **`apartment` / `ros-apartment`** — these are **schema- or database-per-tenant**, a *different axis*
  entirely, and not row-level alternatives. `apartment` itself is effectively unmaintained;
  `ros-apartment` is the maintained fork. If you are considering either, you are considering a different
  isolation model — see the sharding section of `advanced-active-record.md`, and note it frames sharding
  as a last resort after indexing, caching and read replicas.

## 7. Enforcement — the honest state of it

This repo's own rule is that a guarantee nothing enforces is not a guarantee, so: **there is no standard
tool that proves every tenant query is scoped.** No established gem or matcher does this. The building
block is real — `ActiveSupport::Notifications` on `sql.active_record` carries `:sql` and `:binds` — so a
test-time subscriber asserting that every query against a tenant-scoped table carries the tenant filter
is a hand-roll, and worth writing if the data warrants it.

Until then the enforcement is: a `NOT NULL` tenant FK on every scoped table, association traversal that
makes an unscoped query *look* wrong in review, and per-job re-checks at the boundary in §3.

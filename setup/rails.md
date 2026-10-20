# Rails setup section (rails-stack)

`/rails-flow:setup-flow` runs this file for a project whose stack is Rails, after its neutral scaffold. The detector names
it: `detect_stack.py --descriptor` lists it under `setup_sections` from this plugin's `stacks.json`
(`descriptor.setup_section`). Work every section as `setup-flow` works its own: **diagnose, propose the diff, wait for
approval**, and stay idempotent.

`${CLAUDE_PLUGIN_ROOT}` below is **rails-flow's** plugin root: the command running this file is rails-flow's setup-flow,
and the scripts named here ship there.

## CLAUDE.md facts

What setup-flow's §1 inspection and §2 template read for a Rails project (#2196). The template names no stack; these
lines fill it.

- **Inspect** (§1): the Gemfile (Rails version, DB adapter, auth/authz gems, form builder, test stack, deployment),
  `config/application.rb`, the `db/schema.rb` header, and the directory shape (`app/services`? `spec/`? `mobile/`?).
  Every place the project deviates from the rails-8 skill's vanilla doctrine becomes a **Project Override**.
- **A database** (the template's conditional preflight): `config/database.yml`, or a database gem in the Gemfile.
- **Stack line**: `Rails <x>, <DB>, Hotwire, <CSS>, Solid Queue, Kamal 2`.
- **App Identity rows**: framework, database, jobs, cache, websockets, storage, auth, authorization, asset pipeline, CSS,
  deployment, test suite, each filled from the Gemfile and config.
- **Common Commands**: dev server, console, migrate, targeted and full rspec, rubocop on changed files, brakeman,
  bundler-audit, deploy; the project's real commands.
- **Project Override examples**: forms through simple_form, never raw `form_with` (styling lives in the initializer);
  CanCanCan with hash conditions only; every query scoped through `Current.<scope>`, public ids in URLs; prosopite
  raising in test. **Verification** greps: no raw `form_with` in views, no unguarded `.unscoped`.
- **Framework APIs to label `[Recall]`** until verified: Rails, Hotwire, a gem.

### Test-run preflight

The database is up (`pg_isready` for Postgres; start it and re-check if it is not), and no `bundler.lock` is held (a
Ruby LSP `bundle update` holds it).

### loop.md checks

2. Suite health: `bundle exec rspec --fail-fast --no-color`.
3. Lint drift: rubocop on Ruby files changed vs `origin/<base>`.
4. Security deltas: `bundle exec bundler-audit check --update` and `bundle exec brakeman -q` if installed; report NEW
   findings only.

## The `--skip-test` consequence — propose the `Tests:` steps as an approved diff (#779)

`project-setup.md` mandates `--skip-test` so the project gets RSpec instead of Minitest. Rails gates
the test steps in its own `config/ci.rb` template on **that same flag**, so a fresh scaffold has no
`Tests:` step and `bin/ci` — which this toolchain treats as the full gate — reports **green having
run zero specs**. #391 fixed the doctrine; nothing performed it, and it landed missing on two
unrelated greenfield apps from clean runs of the documented path.

**Detect the shape** — `config/ci.rb` exists, RSpec is present, and no step's *command* runs the
suite. The `ci-runs-tests` check answers exactly this and is the same question:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_ci_runs_tests.py"
```

Exit **1** means propose the steps; exit **3** means the project has no `config/ci.rb` and there is
nothing to offer. Take the block verbatim from `rails-8` `references/testing.md` — **all three
steps**, since Rails drops them on the same flag — and insert it **before** the Style and Security
steps, so a broken suite stops the run before the slower checks.

Read the block from that file rather than from here. This command printed its own copy until #1154,
and the copy had drifted in four ways at once — a different order, a different reset task, a
different step name and a different binstub — while still calling itself verbatim. The order in
particular was inverted: it seeded **before** the suite, which is the one thing `testing.md`'s own
reasoning forbids. Two copies of a block that must agree is one copy too many.

The shape to expect, so you can recognise a correct insertion — `db:test:prepare` first (`db:prepare`
does **not** purge), the suite second, the seed check last:

```ruby
  step "Tests: DB reset", "bin/rails db:test:prepare"
  step "Tests: RSpec", "bundle exec rspec"
  step "Tests: Seeds", "env RAILS_ENV=test bin/rails db:seed:replant"
```

**Propose the generators block in the same diff**, because it fails the same way. `project-setup.md`
§1 prescribes it "immediately after creation", and on both affected scaffolds `config/application.rb`
carried only Rails' own `config.generators.system_tests = nil`:

```ruby
config.generators do |g|
  g.test_framework :rspec, fixture: false
  g.fixture_replacement :factory_bot, dir: "spec/factories"
  g.system_tests nil
end
```

**And `factory_bot_rails` with it** — `fixture_replacement :factory_bot` is **inert** without the
gem, so `bin/rails generate` silently emits no factories. `bundle add factory_bot_rails --group
'development,test'`. The `mandated-gems` check refuses that combination by name.

Offer all three as one approved diff; do not write them unasked. Re-running is safe — every check
above is idempotent, and a project that already has the steps reports exit 0.

## Ask whether this project is monolingual, and RECORD the answer (#799)

**Ask.** *"Will this app serve more than one language?"* Most will not, and demanding locale files
everywhere is the false positive that gets a rule ignored — but demanding nothing leaves a
multi-locale app silently monolingual.

**Recording the answer is what makes a situational rule checkable at all.** Without a declaration
there are only two options and both are wrong: gate everyone, or gate nobody. With one, the check
gets three honest states — conforming, drifted, and *not applicable because this project declared
monolingual*. Same mechanism as `config.x.brand.pack` (#788).

```ruby
# config/initializers/locales.rb
Rails.application.configure do
  config.x.locales = %w[en]                 # monolingual — one element, still DECLARED
  # config.x.locales = %w[en ar fr]         # multi-locale
end
```

Write `%w[en]` even for a monolingual app. It is the difference between *"this project chose one
locale"* and *"nobody thought about it"*, and only the first can be checked.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_i18n_setup.py"
```

On a multi-locale answer, propose `skills/rails-8/references/i18n.md` §1–§2 — `available_locales`,
`rails-i18n`, and the `around_action` wrapper. **Never a `before_action`**: Rails' guide says
`I18n.locale` *"can leak into subsequent requests served by the same thread/process"*, and Puma is
threaded, so a locale set and never reset is served to whoever gets that thread next.

## Every reachable app gets the launch baseline; ask whether it should be INDEXED (#1289)

**The axis is reachability, not audience.** An app called "internal" is still on the public internet,
so every app we build gets the **baseline**:

- a `<title>` and a favicon on every page;
- a reachable `/robots.txt` that says what the project decided about search engines;
- a privacy policy and terms, drafted as below;
- a rate limit plus a bot check on **every unauthenticated endpoint**: sign-in, password reset,
  sign-up, contact (`skills/rails-8/references/auth-security.md` → *Unauthenticated endpoints*).
  The `unauthenticated-writes` gate enforces the rate-limit half (#1300);
- cookie consent **only if** the app sets a cookie that is not strictly necessary.

**Ask, and record the answer.** *"Should search engines index this app?"* A marketing site or a
public sign-up: yes. A work platform behind sign-in: no. Undeclared and "no" are different answers,
and only a declaration can be checked:

```ruby
# config/initializers/launch.rb
Rails.application.configure do
  config.x.indexable = false   # robots.txt must disallow indexing
  # config.x.indexable = true  # every page also needs a meta description and og:image, plus a sitemap
end
```

qa-flow's crawl then runs `launch_readiness.py`. It checks the baseline on every app. Not indexable,
`robots.txt` must carry `Disallow: /` for `User-agent: *`, or a search engine may list the sign-in
page. Indexable, it adds the **marketing set**: a meta description and an `og:image` on every page,
and a reachable `/sitemap.xml`.

**Privacy policy, terms and cookie consent: drafted from this app, for its jurisdiction.** Never
boilerplate. A generic policy describes an app that does not exist, and it is wrong in exactly the
places a regulator reads.

1. **Build the data inventory from the code, not from memory**, and write it as
   `config/privacy_inventory.yml`: table → column → `{ category, basis, retention }`, with
   `category: none` for a column that holds no personal data. The `privacy-inventory` gate then fails
   any `db/schema.rb` column (and any column of another `db/*_schema.rb`, such as a second database's
   `db/observability_schema.rb`; not the Solid trio) left unclassified, so a new personal field cannot slip past the policy
   (#1310, #1695). A Solid table the inventory NAMES is read and its listed entries judged; its unlisted columns are
   exempt (#1732). The inventory covers:
   - every personal-data field in `db/schema.rb`;
   - what each form collects;
   - what users upload (Active Storage);
   - every third party that receives data: mail, payments, analytics, error tracking, hosting. Read
     the `Gemfile`, the credentials keys and `config/`;
   - every cookie the app sets;
   - how long each kind of data is kept;
   - which region stores it.
2. **Name the jurisdiction.** Ask for the country (or countries) of operation, and where the users
   are, if the project has not recorded them. Write each document against the data-protection law
   that applies there, and name that law in it. Where users span jurisdictions, meet each one; do not
   pick the laxest.
3. **Draft the three documents.**
   - The **privacy policy** covers: what is collected and why, the basis for processing it, how long
     each kind is kept, who it is shared with, any cross-border transfer, the user's rights and how to
     exercise them, and a contact.
   - The **terms** cover: the service, accounts, acceptable use, liability, and the governing law of
     the country of operation.
   - The **cookie consent** follows best practice: strictly necessary cookies (the session) need a
     notice, not consent; any other cookie waits for consent; and refusing is as easy as accepting.
     An app that sets only necessary cookies needs no banner.
4. **Mark each draft for legal review.** Record the jurisdiction, the law and the draft date in the
   project's CLAUDE.md. An agent can misstate the law, and the reviewer needs the inventory beside
   the draft.

**They live as versioned records, edited in the app, not hard-coded** (maintainer decision on #1289).
Legal text changes more often than code, and a reviewer should not need a deploy to fix a sentence.
The outcomes:

- **An admin edits a draft and publishes it. Publishing creates a new, immutable version** with an
  effective date. A published version is never edited, because "what did this user agree to?" must
  have one answer.
- **Each user's acceptance is recorded against the version they accepted**, with when. A material
  change can require re-acceptance at the next sign-in.
- **Every draft save, publish and acceptance is an audit-log event**: who, which document, which
  version, when.
- **The agent's draft is version 1.** Review happens in the admin screen, and publishing is the
  sign-off.
- **Cookie consent is half content, half code.** The categories, and the rule that a non-essential
  cookie waits for consent, are code, because they describe what the app actually sets. Only their
  wording is content. Otherwise a notice could describe a cookie the app does not set, or miss one it
  does. Each visitor's choice is recorded against the version they saw.
- **Keep them true.** A new third party, a new personal-data field or a new cookie changes the
  inventory, so that PR says which document needs a new version.

Link all three from the footer (`design-system` `page-anatomies.md`).


## Multi-tenant? Install the tenancy cop, and record the answer (#1361)

`Invoice.find(params[:id])` in a controller reads across every tenant, and review is the only thing
that catches it. If `.rails-flow/tenancy.json` already exists, do not ask again; run the check in step 3.
Otherwise, **ask whether the app is multi-tenant, and which foreign key marks a tenant-owned table**
(e.g. `organization_id`). Record the answer:

```json
{"multi_tenant": true, "tenant_foreign_key": "organization_id",
 "unchecked_controllers": {"app/controllers/admin/**/*.rb": "the staff plane reads across tenants"}}
```

Save it as `.rails-flow/tenancy.json`. `unchecked_controllers` names, with a reason, every controller
the cop deliberately does not check, such as the admin plane that §7's config excludes. Globs match as
RuboCop's `Exclude` does: `*` stays in one directory and `**/` spans any number. The check refuses any
other controller the cop skips, and an excuse that matches nothing. `{"multi_tenant": false}` is an answer too: setup-flow does not ask
again, and the `tenancy-cop` check reports not applicable. On yes:

1. Copy the cop rails-flow ships, unmodified. The check refuses a hand-edited copy.

   ```bash
   mkdir -p lib/rubocop/cop/tenancy
   cp "${CLAUDE_PLUGIN_ROOT}/scaffold/tenancy/scoped_lookup.rb" lib/rubocop/cop/tenancy/scoped_lookup.rb
   ```

2. Add the `.rubocop.yml` block from the rails-8 skill's `references/multi-tenancy.md` §7. Set
   `TenantScope` to the app's `Current` attribute, and add one `TenantOwnedModels` entry per model whose
   table carries the tenant foreign key. Add its spec, from the same section, at
   `spec/rubocop/cop/tenancy/scoped_lookup_spec.rb`.
3. Run the check. It runs the project's own RuboCop at every real controller path, and names any where
   the cop does not flag a model or where `rubocop -a` would rewrite. It asks the app for each model's table,
   and names every table carrying the key that no model reaches, plus any key RuboCop would ignore silently.
   It also refuses a `rubocop:disable` that silences the cop anywhere except the same-line
   `-- <reason>` form. It takes about 0.3 s per controller:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_tenancy_cop.py"
   ```

   A tenant-keyed table read across tenants on purpose goes in `"unscoped_tables": {"<table>":
   "<why>"}`, and a reason is required.

Offer the files as one approved diff; do not write them unasked.

## Coverage that cannot catch a regression — propose the ratchet (#800)

`testing.md` used to ship `minimum_coverage 90` **commented out** with *"enable once realistic"*.
Nothing ever makes it realistic, so coverage goes unenforced from the first commit to the last.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_coverage_ratchet.py"
```

Exit **1** means propose the diff; exit **3** means no `simplecov` and nothing to offer.

**The ratchet** — in the SimpleCov block:

```ruby
enable_coverage :branch              # :branch below raises without it
refuse_coverage_drop :line, :branch
```

Today's number is the floor, so it is **never red on day one**, it **cannot slide**, and it **rises
by itself** as specs are written. Do **not** propose a fixed `minimum_coverage <n>` — below where the
repo sits it is inert, above it every run is red and it gets switched off.

**Its memory** — `.gitignore`, or the ratchet compares against nothing in CI:

```gitignore
/coverage/
!/coverage/.last_run.json
```

`coverage/.last_run.json` is the one file there that is not a build artifact. Committed, the diff
also shows coverage moving.

**Say plainly that this one gates.** A coverage *drop* is a measured regression against a recorded
baseline, not a judgement about whether 83% is good — which is why it can block a merge where a
threshold never could.

## The support directory nothing loads — propose the wiring as an approved diff (#803)

`testing.md` prescribes four files under `spec/support/` — `system.rb`, `authentication_helpers.rb`,
`webmock.rb`, `vcr.rb` — and **Rails generates the auto-loader commented out**. Left as generated,
every one of them is dead: no error, no output, and the specs that needed those helpers fail for
reasons that point somewhere else. `testing.md:99` says to uncomment it; nothing checked that anyone
had.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_spec_support.py"
```

Exit **1** means propose the wiring; exit **3** means no `spec/` and there is nothing to offer.

**The auto-loader**, in `spec/rails_helper.rb` — uncomment the generated line, or add it:

```ruby
Rails.root.glob("spec/support/**/*.rb").sort_by(&:to_s).each { |f| require f }
```

**The driver**, when `capybara` is present — `spec/support/system.rb`, verbatim from `testing.md` §8:

```ruby
RSpec.configure do |config|
  config.before(:each, type: :system) do
    driven_by :selenium, using: :headless_chrome, screen_size: [1400, 1400]
  end
  # For specs with zero JavaScript, rack_test is ~10x faster:
  config.before(:each, type: :system, js: false) { driven_by :rack_test }
end
```

**System specs are the developer testing workflow, and `qa-flow` is not a substitute** (#803). The
browser passes in `/qa-flow:crawl` and `/qa-flow:functional` are an **independent** layer — that
independence is the whole value, and folding one into the other destroys it. A developer with no
system specs has no browser feedback until QA runs; QA running the developer's specs is not
independent verification.

## The mandated gem nobody installs — propose `simple_form` as an approved diff (#778)

`ecosystem-gems.md` §2: *"simple_form is mandatory in this stack — no form, and no form element, is
built any other way."* It had **no installer and no gate**, and was missing on both scaffolds. Two of
the three "Always" gems already have checks; this one did not.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_mandated_gems.py"
```

On exit **1**, propose whatever it names. Two shapes come out of it:

**The prescribed testing stack** (#797). `skills/rails-8/references/testing.md` declares a complete
Gemfile block and that file is this stack's testing doctrine, not a menu — yet nothing installed it
and nothing checked it, so a scaffold could hold `rspec-rails` and no `simplecov`, `webmock` or
`vcr` and report clean everywhere. The check names each missing gem and the exact command:

```bash
bundle add rspec-rails factory_bot_rails faker --group 'development,test'
bundle add capybara selenium-webdriver simplecov webmock vcr rubocop-rspec --group test
```

Take the list from the **check's output**, not from this page — it is derived from `testing.md`, so
this block is illustrative and the check is authoritative. **`database_cleaner-active_record` is
deliberately not in it**: `testing.md` §2 says transactional fixtures already cover it.

**The mandated form gem:**

```bash
bundle add simple_form
bin/rails generate simple_form:install
```

The generator writes `config/initializers/simple_form.rb` and the wrappers this stack's form
partials assume. Do not hand-write that initializer — the generator's output is the version-correct
one, and `ecosystem-gems.md` §2 says to configure it once and never fight it per-form.

## Executable boundaries — propose `Archspec.rb` as an approved diff (#715)

The doctrine in `rails-8` `ecosystem-gems.md` §13 states two forbidden dependencies, and until a
project has an `Archspec.rb` **nothing checks either of them** — the `architecture-boundaries` check
reports *not-applicable*, forever. Offer the file; do not write it unasked.

Propose exactly this, adjusting the two component paths to what the project actually has, and skip
any rule whose paths are absent rather than inventing them:

```ruby
# Archspec.rb — at the project root, beside the Gemfile
source "app/**/*.rb", "db/**/*.rb"

component :models,             in: "app/models/**/*.rb"
component :migrations,         in: "db/migrate/**/*.rb"
component :tenant_concern,     in: "app/controllers/concerns/set_current_tenant.rb"
component :shared_controllers, in: "app/controllers/application_controller.rb"

# rails-8 models.md §1 — a migration that references a model breaks when the class evolves.
migrations.cannot_use :models

# rails-8 multi-tenancy.md §1 — the tenant concern must not reach ApplicationController, or the
# admin plane inherits it and "a tenant session grants zero admin access" stops being structural.
shared_controllers.cannot_use :tenant_concern
```

**No `architecture :preset` line.** `:vanilla_rails` requires `app/components` to stay empty and so
fails any project using ViewComponents; `:rails` passes but enforces none of the above. Presets also
make components **overlap**, and every rule applies to every component a file belongs to — which
turns one real finding into three. §13 has the measured detail.

Add the gem to the Gemfile's `:development, :test` group in the same diff, or the check reports a
missing binary rather than a verdict:

```ruby
gem "archspec", "~> 1.0"
gem "herb", "~> 0.10"
```

**Never offer `--update-todo`**, and if the project already has a todo file, say that it is a
suppression baseline rather than treating it as configuration.

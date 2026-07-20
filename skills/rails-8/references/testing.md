# Testing (Industry-Standard RSpec Stack)

This skill's testing stack is the **RSpec ecosystem** — the de-facto industry
standard used by the majority of production Rails teams. RSpec is the *only*
suite in our apps: projects are scaffolded with `--skip-test`
(`project-setup.md`), so the framework's default test scaffolding never
exists and there is no redundant `test/` directory to remove when
`rspec:install` runs.

## Contents
1. The stack and Gemfile
2. Installation and configuration (`rails_helper.rb`)
3. Spec types and directory layout
4. Factories — FactoryBot + Faker
5. Validations and associations — pure RSpec
6. Model specs
7. Request specs (the controller-testing standard)
8. System specs — Capybara + Selenium
9. Mocking: rspec-mocks, WebMock, VCR
10. Time, jobs, mailers, and other assertions
11. Coverage, linting, CI (`bin/ci`), parallelism

---

## 1. The stack and Gemfile

```ruby
group :development, :test do
  gem "rspec-rails"          # the framework, integrated with Rails
  gem "factory_bot_rails"    # dynamic test data instead of fixtures
  gem "faker"                # realistic randomized fake data
end

group :test do
  gem "capybara"             # user-level browser interaction DSL
  gem "selenium-webdriver"   # real/headless browser driver for system specs
  gem "simplecov", require: false   # code coverage reports
  gem "webmock"              # block + stub external HTTP
  gem "vcr"                  # record/replay real HTTP as cassettes
  gem "rubocop-rspec", require: false  # RSpec style linting (+ rubocop-factory_bot, rubocop-capybara)
  # gem "database_cleaner-active_record"  # only if transactions can't cover you — see §2
end
```

Roles at a glance: RSpec executes (and its built-in matchers cover model
specs — no matcher add-ons); FactoryBot + Faker generate data; Capybara +
Selenium drive the browser; SimpleCov measures; WebMock forces network
isolation; VCR makes real-API tests fast and deterministic; rubocop-rspec
keeps spec style consistent.

## 2. Installation and configuration

```bash
bundle install
bin/rails generate rspec:install
# creates: .rspec, spec/spec_helper.rb, spec/rails_helper.rb
```

`spec/spec_helper.rb` — put SimpleCov at the very top (must load before app
code):

```ruby
require "simplecov"
SimpleCov.start "rails" do
  enable_coverage :branch
  add_group "Jobs", "app/jobs"
  # minimum_coverage 90   # fail the suite below this — enable once realistic
end
```

`spec/rails_helper.rb` — the important settings:

```ruby
require "spec_helper"
ENV["RAILS_ENV"] ||= "test"
require_relative "../config/environment"
abort("Running in production!") if Rails.env.production?
require "rspec/rails"

# Auto-load spec/support/** (uncomment the generated line):
Rails.root.glob("spec/support/**/*.rb").sort_by(&:to_s).each { |f| require f }

RSpec.configure do |config|
  # Wrap every example in a DB transaction, rolled back after. Despite the
  # name this covers FactoryBot records too. Since Rails 5.1 the transaction
  # is shared with the app server thread, so it also works for system specs.
  config.use_transactional_fixtures = true

  config.infer_spec_type_from_file_location!   # spec/models → type: :model, etc.
  config.filter_rails_from_backtrace!

  config.include FactoryBot::Syntax::Methods           # create(:user) not FactoryBot.create
  config.include ActiveSupport::Testing::TimeHelpers   # travel_to / freeze_time
end
```

**database_cleaner** is *not* needed in the standard setup — transactional
fixtures cover it. Reach for `database_cleaner-active_record` (truncation
strategy) only when tests touch connections the transaction can't wrap:
multiple processes, a second app, or drivers/services with their own DB
connections. Don't add it "just in case"; truncation is much slower.

`.rspec`:

```
--require spec_helper
--format documentation
```

## 3. Spec types and directory layout

```
spec/
├── factories/          # FactoryBot definitions (one file per model)
├── models/             # unit: validations, scopes, methods
├── requests/           # HTTP-level controller behavior (the standard)
├── system/             # full browser flows (Capybara)
├── jobs/  mailers/  helpers/
├── support/            # shared helpers, shared_examples, config
├── rails_helper.rb  spec_helper.rb
```

Distribution mirrors the pyramid: many model specs, a solid layer of request
specs, **few** system specs (slowest, flakiest — reserve for money paths).
Note: *controller specs* (`type: :controller`) are legacy — write request
specs instead.

## 4. Factories — FactoryBot + Faker

`spec/factories/users.rb`:

```ruby
FactoryBot.define do
  factory :user do
    email_address { Faker::Internet.unique.email }
    password      { "s3cure-password" }
    name          { Faker::Name.name }

    trait :admin do
      role { :admin }
    end

    factory :user_with_posts do           # or use a trait
      transient { posts_count { 3 } }
      after(:create) do |user, ctx|
        create_list(:post, ctx.posts_count, author: user)
      end
    end
  end
end
```

Usage and the golden rules:

```ruby
build(:user)            # in memory — prefer when persistence isn't tested
build_stubbed(:user)    # fastest: fake id, no DB at all
create(:user, :admin)   # persisted; traits compose
create_list(:post, 3, author: user)
```

- **Minimal valid object** in the base factory; everything optional goes in
  traits. Fat factories are the #1 cause of slow suites.
- Associations declared in factories (`association :author, factory: :user`
  or just `author`) — but prefer passing them explicitly in specs for
  clarity.
- `Faker::Internet.unique.email` avoids uniqueness collisions;
  `Faker::UniqueGenerator.clear` runs between examples automatically via
  factory_bot_rails.
- Lint factories in CI so a broken factory fails fast:
  `bundle exec rake factory_bot:lint` (or a dedicated spec calling
  `FactoryBot.lint traits: true`).

## 5. Validations and associations — pure RSpec

No matcher add-ons in this stack — test the **behavior** a declaration
produces with plain RSpec. It reads honestly, teaches nothing gem-specific,
and survives matcher-library churn. (If an existing project uses
shoulda-matchers, follow the project.)

```ruby
RSpec.describe Product, type: :model do
  describe "validations" do
    it "builds a valid record from the factory" do
      expect(build(:product)).to be_valid     # guards the factory itself
    end

    it "requires a name" do
      product = build(:product, name: nil)
      expect(product).not_to be_valid
      expect(product.errors.of_kind?(:name, :blank)).to be(true)
    end

    it "rejects a duplicate sku within the same store" do
      existing = create(:product)
      dup = build(:product, sku: existing.sku, store: existing.store)
      expect(dup).not_to be_valid
      expect(dup.errors.of_kind?(:sku, :taken)).to be(true)
    end

    it "rejects a negative price" do
      product = build(:product, price_cents: -1)
      expect(product).not_to be_valid
      expect(product.errors[:price_cents]).to be_present
    end
  end

  describe "associations" do
    it "destroys dependent reviews" do
      product = create(:product)
      create(:review, product:)
      expect { product.destroy }.to change(Review, :count).by(-1)
    end

    it "exposes its reviews" do
      review = create(:review)
      expect(review.product.reviews).to include(review)
    end
  end
end
```

Idioms: `be_valid` plus `errors.of_kind?(:attribute, :error_key)` — symbolic
error keys (`:blank`, `:taken`, `:too_long`, `:invalid`) survive i18n and
message rewording, so prefer them over matching English strings
(`errors[:attr]` string checks are fine when the key is awkward). Lifecycle
consequences (`dependent: :destroy`, counter caches, touches) are asserted
with `expect { ... }.to change(...)`. One "valid factory" example per model
catches factory rot early. Don't write reflection tests
(`reflect_on_association`, checking a macro was typed) — that re-tests Rails,
not your app; assert what the declaration *does*.

## 6. Model specs

```ruby
RSpec.describe Order, type: :model do
  describe ".overdue" do
    it "returns only orders past their due date" do
      overdue = create(:order, due_on: 2.days.ago)
      create(:order, due_on: 2.days.from_now)

      expect(Order.overdue).to contain_exactly(overdue)
    end
  end

  describe "#total" do
    it "sums line items" do
      order = build_stubbed(:order)
      allow(order).to receive(:line_items).and_return([double(amount: 5), double(amount: 7)])

      expect(order.total).to eq(12)
    end
  end
end
```

Conventions: `describe ".class_method"` / `"#instance_method"`; `context`
strings start with "when/with/without"; `let` for lazily-built data, `let!`
sparingly; one behavior per example, `aggregate_failures` when asserting
several facets of one behavior.

## 7. Request specs (the controller-testing standard)

```ruby
RSpec.describe "Products", type: :request do
  let(:user) { create(:user) }
  before { sign_in user }   # helper below

  describe "POST /products" do
    it "creates a product and redirects (Turbo-compatible 303)" do
      expect {
        post products_path, params: { product: { name: "Desk", price_cents: 100 } }
      }.to change(Product, :count).by(1)

      expect(response).to have_http_status(:see_other)
      follow_redirect!
      expect(response.body).to include("Desk")
    end

    it "re-renders with 422 on invalid input" do
      post products_path, params: { product: { name: "" } }
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end

  it "returns JSON" do
    get products_path, headers: { "Accept" => "application/json" }
    expect(response.parsed_body).to be_an(Array)
  end
end
```

Auth helper for the Rails 8 built-in authentication generator —
`spec/support/authentication_helpers.rb`:

```ruby
module AuthenticationHelpers
  def sign_in(user, password: "s3cure-password")
    post session_path, params: { email_address: user.email_address, password: }
  end
end
RSpec.configure { |c| c.include AuthenticationHelpers, type: :request }
```


## 8. System specs — Capybara + Selenium

`spec/support/system.rb`:

```ruby
RSpec.configure do |config|
  config.before(:each, type: :system) do
    driven_by :selenium, using: :headless_chrome, screen_size: [1400, 1400]
  end
  # For specs with zero JavaScript, rack_test is ~10x faster:
  config.before(:each, type: :system, js: false) { driven_by :rack_test }
end
```

```ruby
RSpec.describe "Checkout", type: :system do
  it "completes a purchase" do
    user = create(:user)
    create(:product, name: "Desk")

    visit new_session_path
    fill_in "Email address", with: user.email_address
    fill_in "Password", with: "s3cure-password"
    click_button "Sign in"

    click_link "Desk"
    click_button "Add to cart"

    expect(page).to have_content("Added to cart")   # Capybara matchers auto-wait
  end
end
```

Rules: never `sleep` — `have_content`/`have_selector` retry up to
`Capybara.default_max_wait_time` (raise it, don't sleep); failures auto-save
screenshots to `tmp/capybara`; `save_and_open_screenshot` while debugging.
Alternative driver worth knowing: `cuprite` (CDP, no chromedriver binary).

## 9. Mocking: rspec-mocks, WebMock, VCR

rspec-mocks — use **verifying doubles** so stubs break when interfaces drift:

```ruby
gateway = instance_double(PaymentGateway, charge: true)
allow(PaymentGateway).to receive(:new).and_return(gateway)
expect(gateway).to have_received(:charge).with(amount: 100) # spy style after action
```

WebMock — block all real HTTP so no spec secretly hits the network
(`spec/support/webmock.rb`):

```ruby
require "webmock/rspec"
WebMock.disable_net_connect!(allow_localhost: true)  # localhost needed by Capybara/Selenium
```

```ruby
stub_request(:get, "https://api.example.com/rates")
  .with(query: { base: "USD" })
  .to_return(status: 200, body: { NGN: 1500 }.to_json,
             headers: { "Content-Type" => "application/json" })
```

VCR — for real third-party APIs, record once, replay forever
(`spec/support/vcr.rb`):

```ruby
VCR.configure do |c|
  c.cassette_library_dir = "spec/cassettes"
  c.hook_into :webmock
  c.configure_rspec_metadata!                 # enables `vcr: true` metadata
  c.default_cassette_options = { record: :once }
  c.filter_sensitive_data("<API_KEY>") { Rails.application.credentials.dig(:example, :api_key) }
end
```

```ruby
it "fetches live rates", vcr: { cassette_name: "rates/usd" } do
  expect(RateFetcher.call("USD")).to include("NGN")
end
```

Rule: stub/VCR at the HTTP boundary or mock your own wrapper class — never
both for the same call. Re-record cassettes deliberately
(`record: :new_episodes` temporarily), and always filter secrets before
committing cassettes.

## 10. Time, jobs, mailers, and other assertions

```ruby
# Time — prefer Rails' built-in TimeHelpers (already included in §2):
travel_to Time.zone.local(2026, 1, 1) do
  expect(subscription).to be_expired
end
freeze_time { ... }
# (timecop offers the same via Timecop.freeze/travel — fine in legacy suites;
#  don't mix both in one project.)

# Jobs:
expect { order.confirm! }.to have_enqueued_job(ReceiptJob).with(order)
perform_enqueued_jobs { order.confirm! }        # actually run them inline

# Mailers:
expect { perform_enqueued_jobs { order.confirm! } }
  .to change { ActionMailer::Base.deliveries.count }.by(1)

# Turbo Streams (turbo-rails provides matchers in request/system context):
expect(response.body).to include(%(turbo-stream action="append" target="comments"))
```

Add `config.include ActiveJob::TestHelper` for `perform_enqueued_jobs`. The
test adapter queues everything; nothing runs unless you perform it.

## 11. Coverage, linting, CI, parallelism

- **SimpleCov** (configured in §2) writes `coverage/index.html`; open it after
  a run and chase untested *branches*, not just lines. Gate with
  `minimum_coverage` once the number is honest.
- **rubocop-rspec** — in `.rubocop.yml` (alongside rails-omakase):

```yaml
inherit_gem: { rubocop-rails-omakase: rubocop.yml }
plugins:            # `require:` on RuboCop < 1.72
  - rubocop-rspec
  - rubocop-factory_bot
  - rubocop-capybara
```

- **`bin/ci`** — swap the test step in `config/ci.rb` (8.1 local CI):

```ruby
CI.run do
  step "Setup", "bin/setup --skip-server"
  step "Style: Ruby", "bin/rubocop"
  step "Security: Gem audit", "bin/bundler-audit"
  step "Security: Importmap audit", "bin/importmap audit"
  step "Security: Brakeman", "bin/brakeman --quiet --no-pager --exit-on-warn --exit-on-error"
  step "Tests: RSpec", "bundle exec rspec"
  step "Factories: lint", "bin/rails factory_bot:lint RAILS_ENV=test"
end
```

  Mirror the same steps in `.github/workflows/ci.yml` for the hosted gate.
- **Parallel execution** — RSpec has no built-in parallelizer; the standard is
  the `parallel_tests` gem: `rake parallel:create parallel:prepare` then
  `bundle exec parallel_rspec spec/`. SimpleCov needs result merging
  (`SimpleCov.command_name ENV["TEST_ENV_NUMBER"]`). Add when the suite
  passes ~1–2 minutes.
- **Suite profiling** — before parallelizing, profile with **test-prof**
  (`TAG_PROF=type bundle exec rspec`, `EVENT_PROF=factory.create ...`): it
  pinpoints factory cascades (the usual culprit) and offers `let_it_be` /
  `before_all` to share expensive setup safely. Fixing factories often beats
  adding workers.
- Flakes: quarantine with metadata + fix, or `rspec-retry` for
  system-spec-only retries — never as a blanket setting.

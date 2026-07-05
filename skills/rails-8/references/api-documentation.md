# API Documentation — OpenAPI / Swagger (Rails 8.1)

The global industry standard for documenting REST APIs is the **OpenAPI
Specification (OAS 3.x)** — formerly Swagger. The deliverable is a machine-
readable `openapi.yaml`/`swagger.json` describing every path, parameter,
schema, and auth scheme; UIs, client generators, and contract tests all hang
off that file. In Rails, generate it from code — never hand-maintain the YAML.

## Contents
1. Choosing a workflow
2. rswag — test-driven docs (this skill's default)
3. rspec-openapi — zero-DSL alternative
4. apipie-rails — controller annotations
5. Rendering: Swagger UI, Redoc, RapiDoc
6. Practices: schemas, auth, versioning, CI

---

## 1. Choosing a workflow

| Approach | Gem | Pick when |
|---|---|---|
| **Test-driven** (specs *are* the docs, and every doc claim is executed) | **rswag** | Default for RSpec teams — docs can't drift because CI runs them |
| **Test-observed** (docs generated from ordinary request specs) | rspec-openapi | Large existing suite; nobody wants a DSL |
| **Annotations** (DSL above controller actions) | apipie-rails | No RSpec, or docs must live next to controller code |

This skill pairs naturally with its RSpec doctrine (`testing.md`): **rswag**
is the default. It kills two birds — each documented response is a real HTTP
request asserted against your app.

## 2. rswag — test-driven docs

```ruby
# Gemfile
gem "rswag-api"    # serves the generated spec file
gem "rswag-ui"     # serves Swagger UI
group :development, :test do
  gem "rswag-specs"  # the RSpec DSL + generator
end
```

```bash
bin/rails g rswag:install
# → spec/swagger_helper.rb, config/initializers/rswag_{api,ui}.rb, routes mounts
```

`spec/swagger_helper.rb` — one place for document metadata, servers, shared
schemas, and security schemes:

```ruby
RSpec.configure do |config|
  config.openapi_root = Rails.root.join("swagger").to_s

  config.openapi_specs = {
    "v1/swagger.yaml" => {
      openapi: "3.0.1",
      info: { title: "API V1", version: "v1" },
      servers: [{ url: "https://{host}", variables: { host: { default: "api.myapp.example" } } }],
      components: {
        securitySchemes: {
          bearer_auth: { type: :http, scheme: :bearer, bearerFormat: "JWT" }
        },
        schemas: {
          product: {
            type: :object,
            properties: { id: { type: :integer }, name: { type: :string },
                          price_cents: { type: :integer } },
            required: %w[id name price_cents]
          },
          error: { type: :object, properties: { errors: { type: :object } } }
        }
      }
    }
  }

  config.openapi_format = :yaml
  # Fail specs whose real response doesn't match the declared schema:
  config.openapi_strict_schema_validation = true
end
```

The spec DSL (a superset of request specs — same auth helpers, factories,
matchers apply):

```ruby
# spec/requests/api/v1/products_spec.rb
require "swagger_helper"

RSpec.describe "Products API", type: :request do
  path "/api/v1/products" do
    get "Lists products" do
      tags "Products"
      produces "application/json"
      security [bearer_auth: []]
      parameter name: :page, in: :query, type: :integer, required: false

      response "200", "products found" do
        schema type: :array, items: { "$ref" => "#/components/schemas/product" }
        let(:Authorization) { "Bearer #{api_token_for(create(:user))}" }
        before { create_list(:product, 2) }
        run_test! do |response|
          expect(response.parsed_body.size).to eq(2)   # extra assertions welcome
        end
      end

      response "401", "unauthorized" do
        let(:Authorization) { nil }
        run_test!
      end
    end

    post "Creates a product" do
      tags "Products"
      consumes "application/json"
      security [bearer_auth: []]
      parameter name: :product, in: :body, schema: {
        type: :object,
        properties: { name: { type: :string }, price_cents: { type: :integer } },
        required: %w[name]
      }

      response "201", "created" do
        let(:Authorization) { "Bearer #{api_token_for(create(:user))}" }
        let(:product) { { name: "Desk", price_cents: 45_000 } }
        run_test!
      end

      response "422", "invalid" do
        schema "$ref" => "#/components/schemas/error"
        let(:Authorization) { "Bearer #{api_token_for(create(:user))}" }
        let(:product) { { name: "" } }
        run_test!
      end
    end
  end
end
```

Mechanics: `parameter ... in: :query|:path|:header|:body`; `let` names must
match parameter names (including `:Authorization` for the header);
`run_test!` fires the real request and asserts the status (plus body-vs-schema
with strict validation on). Generate and serve:

```bash
RAILS_ENV=test bin/rails rswag:specs:swaggerize   # writes swagger/v1/swagger.yaml
# Swagger UI now live at /api-docs (mounted by the installer)
```

## 3. rspec-openapi — zero-DSL alternative

Keep your request specs untouched; the gem watches real requests/responses
during the run and writes the spec:

```ruby
group :test do
  gem "rspec-openapi"
end
```

```bash
OPENAPI=1 bundle exec rspec spec/requests   # writes doc/openapi.yaml
```

Configure output path/metadata via `RSpec::OpenAPI.path` /
`.title` / `.servers` in `spec/spec_helper.rb`. Trade-off vs rswag: nothing
to learn and instant coverage of an existing suite, but schemas are inferred
from whatever examples happened to run — review the generated diff in git and
keep specs exercising every status code you want documented.

## 4. apipie-rails — controller annotations

When docs must live beside the actions (or the project isn't on RSpec):

```ruby
# Gemfile: gem "apipie-rails"   → rails g apipie:install (adds `apipie` route)

class Api::V1::ProductsController < Api::BaseController
  api :GET, "/v1/products/:id", "Show a product"
  param :id, :number, required: true, desc: "Product id"
  error code: 404, desc: "Not found"
  returns code: 200 do
    property :name, String
    property :price_cents, Integer
  end
  def show = render json: @product
end
```

Browsable docs at `/apipie`; declared `param`s can also *validate* incoming
requests (`Apipie.configuration.validate = true`). It predates OAS — export
to OpenAPI via its swagger generators if you need the standard file. Don't
run apipie and rswag in one app.

## 5. Rendering: Swagger UI, Redoc, RapiDoc

- **Swagger UI** — mounted by rswag at `/api-docs`; interactive "Try it out"
  against your real endpoints. Fine default for internal/partner docs.
- **Redoc / RapiDoc** — prettier single-page renderers for public docs; both
  are one static page pointed at the same generated file:

```erb
<%# app/views/docs/api.html.erb (route: get "/docs/api", ...) %>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
<redoc spec-url="/api-docs/v1/swagger.yaml"></redoc>
<%# RapiDoc equivalent: <rapi-doc spec-url="..."></rapi-doc> with its script %>
```

The spec file is the product; renderers are swappable skins.

## 6. Practices: schemas, auth, versioning, CI

- **Single source of truth for shapes.** Define response schemas once under
  `components/schemas` and `$ref` them everywhere. If you use serializer
  objects (blueprinter/alba — `ecosystem-gems.md`), mirror one schema per
  serializer and let the strict validation catch drift between them.
- **Document auth honestly**: a `securitySchemes` entry + `security` on every
  protected path + a `401` response example. Consumers hit auth first.
- **Version the document with the API**: `swagger/v1/swagger.yaml`,
  `swagger/v2/…` — matching your `namespace :v1` routing
  (`controllers-routing.md`); never mutate a published version's contract.
- **CI gate against drift** — regenerate and fail if the committed file is
  stale, as a step in `config/ci.rb` (`testing.md` §11):

```ruby
step "API docs: fresh", "RAILS_ENV=test bin/rails rswag:specs:swaggerize && git diff --exit-code swagger/"
```

- Commit the generated file (reviewable diffs = contract review in PRs), and
  serve it in production only if the API is public — otherwise constrain the
  `/api-docs` mounts to staff/admin.

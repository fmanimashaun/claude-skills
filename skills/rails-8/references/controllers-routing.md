# Controllers and Routing

## Contents
1. Routing
2. Controller anatomy
3. Strong parameters with `params.expect`
4. Filters, guards, and rate limiting
5. Session, cookies, flash
6. Rendering, redirecting, status codes (Turbo-critical)
7. Error handling
8. Formats, streaming, and 8.1 markdown
9. API-only applications

---

## 1. Routing

`config/routes.rb` is a DSL; resources are the unit of design.

```ruby
Rails.application.routes.draw do
  root "products#index"

  resources :products do
    resources :reviews, only: %i[create destroy]     # nest ONE level max
    collection { get :search }                        # /products/search
    member     { post :archive }                      # /products/:id/archive
  end

  resource :profile, only: %i[show edit update]       # singular: no :id, no index

  namespace :admin do                                  # /admin/..., Admin::OrdersController, admin_orders_path
    resources :orders
  end
  scope module: :storefront do resources :carts end    # controller in module, URL unchanged

  # Reusable route bundles
  concern :commentable do resources :comments end
  resources :posts, concerns: :commentable

  direct(:homepage) { "https://example.com" }          # homepage_url helper
  resolve("Basket") { [:cart] }                        # form_with model: @basket → cart_path

  get "up" => "rails/health#show", as: :rails_health_check
  # PWA routes ship commented out; uncomment to serve manifest/service worker
end
```

Guidelines:

- Prefer another **resource over a custom action**: "activate" a product →
  `resources :activations, only: [:create, :destroy]` nested under products,
  or at least a `member` route — never a bespoke non-REST verb sprawl.
- `only:`/`except:` keep the route table honest. Inspect with
  `bin/rails routes -g orders` or `--expanded`.
- Constraints: `resources :photos, constraints: { id: /[A-Z]\d{5}/ }`;
  authenticated sections via request constraints
  (`constraints ->(req) { req.session[:user_id] } do ... end`) or custom
  constraint classes.
- Path customization: `path:`, `as:`, `param: :slug` (pair with
  `to_param`/`find_by!` in the model). Redirect routes:
  `get "/old", to: redirect("/new", status: 301)`.
- Shallow nesting for deep hierarchies: `resources :posts do
  resources :comments, shallow: true end` — collection routes nested,
  member routes top-level.

## 1a. URL design — human paths vs REST resources (doctrine)

The default posture: **user-facing pages get human, readable URLs; records and the
JSON API get REST resource URLs.** A URL is UX — it's a ranking/trust signal, it's
shared and typed, and password managers + the `/.well-known/change-password` standard
key off it. `resources` is right for machine-addressable records; it's wrong when it
leaks developer vocabulary (`/registrations/new`) or a redundant id (`/users/42/account`
for *my* account) into a human's address bar.

**The rule — match the URL to what the reader is addressing:**

- **One of many interchangeable records** → REST resource URL with the id:
  `resources :articles` → `/articles/42`. The id is meaningful; the URL identifies
  *which* record. Also correct for another user's PUBLIC profile (`/users/42`).
- **A concept, or a singleton scoped to the current user** ("my account", "the
  dashboard", "the login page", "my cart") → human path, no id. Use Rails' singular
  `resource` (no id, plural controller) or an explicit vanity route:
  `resource :account` → `/account` + `account_path`; `/dashboard`, `/checkout`,
  `/settings`, `/search`. Forcing an id here (`/users/42/account`) is the smell — it's
  always *you*.
- **Machine-facing JSON API** → strict REST throughout, regardless of the above:
  `namespace :api { namespace :v1 { resources :sessions, :users } }`. That audience
  wants resource-CRUD consistency, not vanity.
- **Content/marketing** → descriptive slugs, shallow depth, hyphens not underscores,
  no opaque ids (`/pricing`, `/blog/url-slug-best-practices` — not `/pages/7`). Use
  `friendly_id` for record slugs (`/articles/rails-8-routing`).

**The reconciliation — RESTful controllers UNDER human URLs.** You don't choose
between clean controllers and clean URLs; keep the resource controller and alias the
route:

```ruby
# Human-facing HTML: vanity URL, REST controller underneath, natural helper
get    "/login",  to: "sessions#new",       as: :login
post   "/login",  to: "sessions#create"
delete "/logout", to: "sessions#destroy",   as: :logout
get    "/signup", to: "registrations#new",  as: :signup
post   "/signup", to: "registrations#create"
resource :account, only: [:show, :edit, :update]   # /account, account_path
get "/dashboard", to: "dashboards#show", as: :dashboard
get "/search",    to: "searches#show",   as: :search

# Machine-facing JSON API: strict REST for a different audience
namespace :api do
  namespace :v1 do
    resources :sessions, only: [:create, :destroy]
    resources :users,    only: [:create, :show, :update]
    resources :articles
  end
end
```

Now views read `link_to "Log in", login_path`; the controller stays
`SessionsController#create/destroy` (a session genuinely IS created/destroyed —
honest REST semantics); the URL is what users, browsers, and password managers expect;
and the API keeps resource consistency. Add `/.well-known/change-password` →
`redirect_to edit_password_path` so password managers can deep-link.

**On the Rails 8 auth generator specifically:** it ships `resource :session`,
`resource :registration`, `resource :password` — RESTful, and internally correct (a
session is a no-id singleton, so singular `resource` is the RIGHT tool, and it maps to
a plural `SessionsController` by design — a known but correct Rails quirk). But the
generated *helpers* (`new_session_path`) are developer vocabulary. For a user-facing
app, override to vanity paths as above — this is a documented Project Override, not a
generator bug. Trim generated routes to implemented actions
(`resource :session, only: [:new, :create, :destroy]`).

**Not a license to abandon REST.** Vanity paths are for singletons-to-me and concepts;
collections and specific records stay resourceful. The test: if the URL needs an id to
say which one, it's REST; if there's only ever one relative to the viewer (or it's a
concept/page), it's human. When a project's routes already encode a deliberate scheme,
treat it as a Project Override — don't "correct" a chosen convention.

## 2. Controller anatomy

```ruby
class ProductsController < ApplicationController
  before_action :set_product, only: %i[show edit update destroy]

  def index
    @products = Product.visible.order(:name)
  end

  def show; end

  def new    = @product = Product.new
  def create
    @product = Product.new(product_params)
    if @product.save
      redirect_to @product, notice: "Product created.", status: :see_other
    else
      render :new, status: :unprocessable_entity
    end
  end

  def update
    if @product.update(product_params)
      redirect_to @product, notice: "Product updated.", status: :see_other
    else
      render :edit, status: :unprocessable_entity
    end
  end

  def destroy
    @product.destroy!
    redirect_to products_path, notice: "Product deleted.", status: :see_other
  end

  private
    def set_product   = @product = Product.find(params[:id])
    def product_params = params.expect(product: [:name, :price, :status, :photo])
end
```

Keep controllers to translation work: fetch/build a model, call one model
method, choose a response. Shared behavior → `app/controllers/concerns/` or
`ApplicationController`. Instance variables are the view interface; set only
what the view needs.

`ApplicationController` in a fresh 8.x app includes
`allow_browser versions: :modern` (406 for ancient browsers — relax with
`versions: { safari: 16, ... }` or remove) and, after running the auth
generator, `include Authentication`.

## 3. Strong parameters — `params.expect`

`params.expect` (8.0+) is the required-shape API; it 400s on missing/mistyped
structure instead of 500ing, and permits in one call:

```ruby
params.expect(:id)                                   # required scalar
params.expect(user: [:email, :password])             # required hash of scalars
params.expect(post: [:title, tag_ids: [], comments_attributes: [[:body, :_destroy, :id]]])
#                                ^ array of scalars   ^^ DOUBLE brackets = array of hashes
```

Legacy `params.require(:user).permit(:email)` still works — match existing
codebases, but write `expect` in new code. Never `permit!`. Non-model params:
`params[:query]`, `params.fetch(:page, 1)`. Unpermitted keys log in
dev/test; `config.action_controller.action_on_unpermitted_parameters =
:raise` is a good strictness upgrade.

## 4. Filters, guards, rate limiting

```ruby
before_action :require_authentication          # from the auth generator
before_action :set_locale
skip_before_action :require_authentication, only: :show
around_action :switch_time_zone

rate_limit to: 10, within: 3.minutes, only: :create,
           with: -> { redirect_to new_session_url, alert: "Try again later." },
           by: -> { request.remote_ip }         # default key; counts via Rails.cache
```

Filters halt the chain by rendering or redirecting inside them. Prefer a
small number of intention-revealing filters over stacks of micro-filters.

## 5. Session, cookies, flash

- `session[:cart_id] = cart.id` — cookie-backed (~4 KB, encrypted). Store
  ids, not objects. `reset_session` on login/logout (fixation defense).
- `cookies[:theme] = { value: "dark", expires: 1.year }`;
  `cookies.signed[...]`, `cookies.encrypted[...]`,
  `cookies.permanent.signed[:session_id]` (the auth generator's pattern —
  httponly + same_site: :lax).
- `flash[:notice]` survives one redirect; `flash.now[:alert]` for renders in
  the same request. Prefer the `redirect_to ..., notice:/alert:` shorthand;
  arbitrary keys allowed (`flash[:success]`) if the layout renders them.

## 6. Rendering, redirecting, status codes — Turbo-critical

Every action renders its template by convention; explicit calls when
deviating:

```ruby
render :edit, status: :unprocessable_entity      # 422 — REQUIRED for form re-renders under Turbo
redirect_to @product, status: :see_other         # 303 — REQUIRED after destructive/non-GET actions
redirect_back_or_to root_path
render json: @product                            # or: plain:, xml:, body:, file:, inline:
render partial: "form", locals: { product: @product }
head :no_content
```

Why: Turbo submits forms as fetch; a 200 re-render is treated as success and
a 302 after DELETE can replay the DELETE. `:see_other` + `:unprocessable_entity`
are not optional style — they are correctness. Open-redirect protection:
`redirect_to params[:return_to]` raises unless
`allow_other_host: true` is explicit — keep it that way.

## 7. Error handling

```ruby
class ApplicationController < ActionController::Base
  rescue_from ActiveRecord::RecordNotFound, with: :render_not_found
  private def render_not_found = render file: Rails.public_path.join("404.html"), status: :not_found, layout: false
end
```

Unrescued exceptions map to public error pages in production
(404/422/500 under `public/`). Don't rescue broadly to hide bugs; report
unexpected errors via `Rails.error.report(e)` (see performance-caching.md).
For "not found should look like forbidden" cases, rescue and render 404
deliberately.

## 8. Formats, streaming, and 8.1 markdown

```ruby
respond_to do |format|
  format.html
  format.json { render json: @page }
  format.md   { render markdown: @page }   # 8.1 — calls @page.to_markdown
end
```

8.1 markdown rendering also supports `.md`/`.md.erb` templates rendered like
any other format — handy for docs endpoints and AI/agent-facing responses.

`send_data pdf, filename: "r.pdf", type: "application/pdf"` /
`send_file path, disposition: :inline` for downloads (but Active Storage for
user files). `ActionController::Live` + `response.stream` exists for SSE;
prefer Turbo Streams over hand-rolled SSE for UI updates.

## 9. API-only applications

`rails new api --api`: `ApplicationController < ActionController::API`, no
views/assets/Hotwire/CSRF middleware, jbuilder available. Auth via tokens:
`authenticate_or_request_with_http_token` + `has_secure_token` or signed
tokens (`generates_token_for`). Rate-limit and version through the router
(`namespace :v1`). If the app serves both HTML and JSON, stay a normal app
and add `format.json` — don't split into two apps prematurely. CORS via
`rack-cors` (commented in the generated Gemfile/initializer).

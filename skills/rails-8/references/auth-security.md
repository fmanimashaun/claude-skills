# Authentication, Authorization, and Security

## Contents
1. The built-in authentication generator (8.x)
2. Extending auth: registration, remember-me, roles
3. Authorization the Rails way
4. Security checklist (from the official Security guide)

---

## 1. `bin/rails generate authentication`

The Rails-way answer to "add login" — Rails 8 made third-party auth engines
unnecessary (an existing app with a different auth solution: stay consistent
with it). One command generates full, readable session-cookie auth you own:

```bash
bin/rails g authentication && bin/rails db:migrate
```

What you get and how it fits:

```ruby
# app/models/user.rb
class User < ApplicationRecord
  has_secure_password                       # bcrypt; password/password_confirmation virtuals
  has_many :sessions, dependent: :destroy
  normalizes :email_address, with: ->(e) { e.strip.downcase }
end

# app/models/session.rb — DB-backed sessions: revocable, auditable
class Session < ApplicationRecord
  belongs_to :user                          # + ip_address, user_agent columns
end

# app/models/current.rb
class Current < ActiveSupport::CurrentAttributes
  attribute :session
  delegate :user, to: :session, allow_nil: true
end

# app/controllers/concerns/authentication.rb (included in ApplicationController)
#   before_action :require_authentication   — redirects to login, remembers return URL
#   allow_unauthenticated_access only: ...  — class-level opt-out
#   authenticated?, resume_session, start_new_session_for(user), terminate_session
#   Cookie: cookies.signed.permanent[:session_id] (httponly, same_site: :lax)

# app/controllers/sessions_controller.rb
class SessionsController < ApplicationController
  allow_unauthenticated_access only: %i[new create]
  rate_limit to: 10, within: 3.minutes, only: :create,
             with: -> { redirect_to new_session_url, alert: "Try again later." }

  def create
    if user = User.authenticate_by(params.permit(:email_address, :password))
      start_new_session_for user
      redirect_to after_authentication_url
    else
      redirect_to new_session_path, alert: "Try another email address or password."
    end
  end

  def destroy
    terminate_session
    redirect_to new_session_path
  end
end

# app/controllers/passwords_controller.rb + PasswordsMailer — full reset flow:
#   uses user.password_reset_token / User.find_by_password_reset_token!
#   (built into has_secure_password, 15-minute expiry, single-use by design)

# routes: resource :session; resources :passwords, param: :token
```

Why this design is the recommendation: `authenticate_by` is
timing-attack-hardened; DB sessions can be listed and revoked ("sign out
everywhere": `user.sessions.destroy_all`); `Current` gives you
`Current.user` anywhere in the request without parameter threading;
everything is plain Rails you can read and modify. Views come unstyled —
style them like the rest of the app.

In tests, sign in through the front door (integration:
`post session_path, params: { email_address:, password: }`; system: fill the
form) or extract a small `sign_in_as(user)` helper doing the same.

## 2. Extending auth

**Registration** (not generated — add it):

```ruby
# routes: resource :registration, only: %i[new create]
class RegistrationsController < ApplicationController
  allow_unauthenticated_access
  def new = @user = User.new
  def create
    @user = User.new(params.expect(user: [:email_address, :password, :password_confirmation]))
    if @user.save
      start_new_session_for @user
      redirect_to root_path, notice: "Welcome!"
    else
      render :new, status: :unprocessable_entity
    end
  end
end
# User: validates :email_address, presence: true, uniqueness: true  (+ DB unique index)
#       validates :password, length: { minimum: 12 }, allow_nil: true
```

Email confirmation: `generates_token_for :email_verification, expires_in:
1.day` + a mailer + a verify endpoint flipping `verified_at`. Roles: start
with a boolean/enum on `users` (`admin:boolean`, or
`enum :role, { member: 0, admin: 1 }`) — no gem needed. OAuth/SSO: add
`omniauth` on top of the same Session model when genuinely required.

## 3. Authorization the Rails way

Start with the simplest thing that reads clearly:

```ruby
# scoping IS authorization for ownership:
def set_project = @project = Current.user.projects.find(params[:id])  # 404s strangers

# role gates as filters:
class Admin::BaseController < ApplicationController
  before_action :require_admin
  private def require_admin
    redirect_to root_path, alert: "Not authorized." unless Current.user&.admin?
  end
end

# per-record rules as model predicates:
class Post < ApplicationRecord
  def editable_by?(user) = user.admin? || author == user
end
# controller: head :forbidden unless @post.editable_by?(Current.user)
```

Graduate to Pundit (policy objects) or CanCanCan (ability DSL) only when
rules multiply beyond a handful of predicates — and if the project already
uses one, follow it (write policies/abilities there, never parallel ad-hoc
checks). Always authorize on the server; hiding buttons is UX, not security.

## 4. Security checklist

Rails defaults do a lot; your job is to not undo them and to cover the gaps.

**Injection & escaping**
- SQL: placeholders/hashes only — `where("name = ?", n)`,
  `where(name: n)`; `sanitize_sql_like` for LIKE terms. Dangerous raw-SQL
  APIs (`order`, `select` with strings) must not receive user input — map
  user sort keys through an allowlist hash.
- XSS: ERB escapes by default. `raw`/`html_safe` only for content you
  control; user HTML goes through `sanitize` (allowlist). Never interpolate
  user input into JS in templates without `j`/`json_escape`.
- Command injection: no backticks/`system` with interpolated input —
  `system("cmd", arg1, arg2)` array form if shelling out is unavoidable.

**Requests & sessions**
- CSRF: `protect_from_forgery with: :exception` is on; keep non-GET
  state changes non-GET (use `button_to`), and don't disable per-controller
  except token-authenticated JSON APIs.
- `reset_session` after login (the generator's flow effectively rotates by
  replacing the cookie) and on logout.
- Cookies: only signed/encrypted jar for anything trusted; `httponly:
  true`, `same_site: :lax` (default).
- Open redirects: never pass params to `redirect_to` without
  `allow_other_host` awareness (Rails raises by default — good).
- Host authorization (`config.hosts`) in development guards DNS rebinding;
  set it (or `config.action_dispatch.hosts` equivalents) appropriately when
  exposing dev servers.

**Transport & headers**
- Production ships `force_ssl` + `assume_ssl` — leave on; HSTS comes with
  `force_ssl`.
- Content Security Policy: enable in
  `config/initializers/content_security_policy.rb`; with importmap, use
  nonces (`content_security_policy_nonce_generator` +
  `javascript_importmap_tags` picks them up). Start report-only, then
  enforce.
- Default security headers (X-Frame-Options SAMEORIGIN, nosniff, etc.) are
  set — extend via `config.action_dispatch.default_headers` if needed.

**Data**
- Filter secrets from logs: `config/initializers/filter_parameter_logging.rb`
  covers `:passw, :email, :secret, :token…` — extend for domain PII.
  Production also limits `#inspect` to `:id`.
- Encrypt sensitive columns (`encrypts`), hash anything verify-only.
- Files: validate content type + size on upload; serve through Active
  Storage, never user-controlled paths (`send_file params[:path]` is a
  classic traversal hole).
- Mass assignment: `params.expect` everywhere; audit any `permit!`.

**Tooling (already in `bin/ci`)**
- `bin/brakeman` — static analysis; fix or explicitly ignore with
  justification (`config/brakeman.ignore`).
- `bin/bundler-audit` + `bin/importmap audit` — CVE scans for gems and
  pinned JS.
- Keep Rails patched: security releases land on supported series only —
  8.1 gets fixes; stay current.

## Route naming for auth (see controllers-routing §1a)

The generator's `resource :session`/`registration`/`password` are RESTful and correct,
but the helpers are developer vocabulary. For user-facing apps, expose vanity paths —
`/login`, `/logout`, `/signup`, `/forgot-password` — over the same REST controllers
(`get "/login", to: "sessions#new", as: :login`), and wire
`/.well-known/change-password` → `edit_password_path` for password managers. Full
doctrine (human paths vs REST records vs JSON API) is in
`references/controllers-routing.md` §1a. Treat a project's existing scheme as a
Project Override.

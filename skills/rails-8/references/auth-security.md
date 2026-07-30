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
- Open redirects: never pass params to `redirect_to` without `allow_other_host`
  awareness. Rails raises by default — arrived in **7.0** as
  `raise_on_open_redirects`, and **8.1 replaced that with
  `action_on_open_redirect`** (`:log` / `:notify` / `:raise`). The mattr default is
  `:log`, but framework defaults set `:raise`, so a fresh 8.1 app still raises.
  **"Another host" is an exact host match — subdomains count**, so `app.` → `admin.`
  is a cross-host redirect.
  - **Prefer `config.action_controller.allowed_redirect_hosts` (new in 8.1) over
    `allow_other_host: true`.** The flag disables the check for that *entire call*;
    the allowlist permits only the hosts you name and keeps every other host blocked.
- **Host authorization (`config.hosts`) is enabled in development and EMPTY in
  production** — where the list is empty the middleware returns immediately and does
  **nothing**. The Rails security guide says it plainly: *"It is enabled by default in
  the development environment, you have to activate it in production."* So anything
  that derives a URL or a redirect target from `request.host`/`request.domain` is
  trusting an attacker-controllable header until you set `config.hosts` in production.
  It rejects with **403 before the app runs**, which is what makes it a real defence
  rather than a check you could forget in a controller.

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

## Cross-plane sign-in — one front door, per-plane sessions (#98)

When an app is split across hosts — a marketing root, `app.` for the product, `admin.`
for an operator console (see [multi-tenancy.md](multi-tenancy.md)) — sessions cannot be
shared, and should not be. **A cookie with no `Domain` attribute is confined to the exact
host that set it** (RFC 6265: *"If the server omits the Domain attribute, the user agent
will return the cookie only to the origin server"*). Rails' generated session cookie is
host-only by default. Rails does offer `domain: :all` to share one cookie across
subdomains — **decline it**: a shared cookie means an XSS on one plane can reach another
plane's session, which is the isolation the separate hosts bought you.

So a unified sign-in needs a **hand-off**, not a shared cookie.

**The shape** (fidara-ledger D-038/D-039): one sign-in entry on the root host authenticates
against both realms, **holds no session of its own**, mints a short-lived single-use
**encrypted** grant, and redirects to the matching plane's host, which exchanges the grant
for its own host-scoped session.

- **Identifier-first, also called *home realm discovery*** — the standard identity term, so
  use it rather than inventing one. Step 1 takes the email only; step 2 takes the credential.
- **Step 2 advances for every email**, existing or not, and every failure message is
  identical. OWASP WSTG's account-enumeration test (**WSTG-IDNT-04**) asks for *"the same
  error message **and length**"* — note **length**, so keep the response *shape* constant,
  not merely the wording. Rate-limit both steps.
- **The front door belongs to no plane.** Put genuinely cross-plane controllers in their own
  `shared/` area inheriting the thin `ApplicationController` — not under the marketing
  namespace, and not under either plane's base controller, so it cannot inherit a session it
  must not have.

```ruby
class Shared::SessionsController < ApplicationController
  rate_limit to: 10, within: 3.minutes, only: %i[create identify],
    with: -> { redirect_to signin_path, alert: "Try again in a moment." }

  def create
    credentials = { email_address: params[:email_address].to_s, password: params[:password].to_s }

    if (user = User.authenticate_by(credentials))
      redirect_to plane_grant_url(:tenant, SigninGrant.mint(realm: "tenant", id: user.id))
    elsif (staff = StaffUser.authenticate_by(credentials))
      redirect_to plane_grant_url(:platform, SigninGrant.mint(realm: "platform", id: staff.id))
    else
      # Identical to every other failure — no realm, no existence, no hint.
      flash.now[:alert] = "Try another email address or password."
      render :identify, status: :unprocessable_content
    end
  end
end
```

**`authenticate_by` is required here, not optional.** Added in **Rails 7.1**, it *"takes the
same amount of time regardless of whether a user with a matching email is found"* — a
`find_by` + `authenticate` pair is a timing oracle for whether the address exists, which
would defeat the whole uniformity effort above.

**A residual timing channel the uniform messages do not close.** `User.authenticate_by ||
StaffUser.authenticate_by` runs **one** lookup when the tenant matches and **two** when
neither does, so total latency still varies by realm. If realm disclosure matters, evaluate
both unconditionally and choose afterwards.

### The grant: encrypted, not merely signed

```ruby
class SigninGrant
  EXPIRES_IN = 60.seconds
  PURPOSE = :signin_grant
  REALMS = %w[tenant platform].freeze

  class << self
    def mint(realm:, id:)
      raise ArgumentError, "unknown realm" unless REALMS.include?(realm.to_s)
      encryptor.encrypt_and_sign({ "realm" => realm.to_s, "id" => id, "jti" => SecureRandom.uuid },
                                 purpose: PURPOSE, expires_in: EXPIRES_IN)
    end

    def claim(token, expected_realm:)
      data = encryptor.decrypt_and_verify(token.to_s, purpose: PURPOSE)
      # nil-check FIRST: expiry and purpose mismatch return nil, they do not raise.
      return unless data.is_a?(Hash) && data["realm"] == expected_realm.to_s && data["id"].present?
      return unless consume(data["jti"])
      data["id"]
    rescue ActiveSupport::MessageEncryptor::InvalidMessage
      nil    # tamper / corrupt format — this is the only path that raises
    end

    private
      def encryptor
        key = Rails.application.key_generator.generate_key("signin_grant",
                                                          ActiveSupport::MessageEncryptor.key_len)
        ActiveSupport::MessageEncryptor.new(key)
      end
  end
end
```

**Encrypt, do not sign.** The grant rides in a **URL**, and `MessageVerifier`'s own
documentation is blunt about what signing does not give you:

> *"Signing is not encryption. The signed messages are not encrypted. **The payload is
> merely encoded (Base64 by default) and can be decoded by anyone.**"*

A signed-only grant would publish the raw record id to browser history, referrer headers,
proxy and CDN logs. `MessageEncryptor` keeps `realm`/`id`/`jti` confidential while expiry
and signature stay stateless — no table needed.

**The failure modes are not symmetrical, and this is the easiest thing to get wrong:**
`decrypt_and_verify` **returns `nil`** on expiry and on a purpose mismatch, and **raises
`InvalidMessage`** only on tamper or a corrupt format. A `rescue`-only implementation
therefore sails past an expired grant with a `nil` and blows up on the next method call.
Check the return value *and* rescue.

**Bind the grant to a realm** and verify it on exchange (`expected_realm:`), so a tenant
grant cannot be redeemed on the admin plane.

**Derive the key** with `Rails.application.key_generator.generate_key(salt, MessageEncryptor.key_len)`
— that is the sanctioned route from `secret_key_base`, and the only one: Rails ships
`Rails.application.message_verifier(name)` but has **no** equivalent encryptor factory.

### Single-use, and an honest note about atomicity

```ruby
def consume(jti)
  return false if jti.blank?
  Rails.cache.write("signin_grant:consumed:#{jti}", true,
                    expires_in: EXPIRES_IN + 1.minute, unless_exist: true)
end
```

`unless_exist` *"prevents overwriting an existing cache entry"*, and atomicity is
**store-specific, not an API guarantee**. On **Solid Cache** the write takes a
`SELECT … FOR UPDATE` row lock — genuinely atomic for a key that already exists, but a
brand-new key has **no row to lock**, so two truly concurrent first-claims can both win.
The window is narrow and bounded (same token, inside a ≤60s TTL, and the token is encrypted
so it is never readable from a URL or log), but write it down rather than implying the
primitive is airtight. A Redis `SET NX` or memcached `ADD` store has no such window — this
caveat is Solid Cache's, not `Rails.cache`'s in general. Harden to a unique-index claim when
the threat model warrants it.

**Two specs in this area pass whether or not the code works** — the Rails test environment
defaults to `config.cache_store = :null_store`:

- `NullStore` ignores `unless_exist` and returns `true` every time, so a **single-use** spec
  never sees a rejected second claim.
- `rate_limit` calls `store.increment`, which `NullStore` answers with `nil`, so the limit
  never trips — **`rate_limit` is a permanent no-op in test**. `rate_limit` itself arrived in
  **Rails 7.2** and needs a real backing store.

Stub a real store (`:memory_store`) in any example asserting either behaviour, or the test is
vacuous.

### The exchange side

```ruby
class Tenant::SessionGrantsController < Tenant::BaseController
  allow_unauthenticated_access only: :show
  rate_limit to: 20, within: 1.minute, only: :show,
    with: -> { redirect_to new_tenant_session_path, alert: "Try again in a moment." }

  def show
    if (id = SigninGrant.claim(params[:token], expected_realm: "tenant")) && (user = User.find_by(id: id))
      start_new_session_for user
      redirect_to after_authentication_url
    else
      # Fail closed, generic message: invalid, expired, replayed and wrong-realm
      # are indistinguishable to the caller.
      redirect_to new_tenant_session_path, alert: "That sign-in link has expired — please sign in again."
    end
  end
end
```

Unauthenticated by definition — the visitor has no session on this host yet, and the signed
single-use realm-scoped grant *is* the proof. **`allow_unauthenticated_access` is generated
code, not a framework method** — the Rails 8 authentication generator defines it as
`skip_before_action :require_authentication`. A two-realm app therefore decides whether one
`Authentication` concern covers both realms or each plane gets its own (`StaffAuthentication`
with its own `require_staff_authentication`); that is a design choice, not a framework fact.

### Deriving the target host — the part that depends on `config.hosts`

Building the hand-off URL from `request.domain` keeps one code path working across
`lvh.me` in development and the real domain in production:

```ruby
def plane_grant_url(plane, token)
  subdomain, helper = plane == :tenant ? ["app", :tenant_session_grant_url]
                                       : ["admin", :admin_session_grant_url]
  public_send(helper, token: token, host: "#{subdomain}.#{request.domain}",
              port: request.optional_port)
end
```

**This is only safe because Host authorization rejects a spoofed `Host:` first**, and per the
checklist above `config.hosts` is **empty in production by default**. Set it, keyed on your
real app host, or this line takes its redirect target from an attacker-controlled header.
Then either name both plane hosts in `allowed_redirect_hosts` (8.1) or pass
`allow_other_host: true` — the allowlist is the better of the two.


# Authentication, Authorization, and Security

## Contents
1. The built-in authentication generator (8.x)
2. Extending auth: registration, remember-me, roles
2a. Password policy — what NIST requires, and the rule it forbids
2b. Multi-factor — Rails ships none, and §2a already depends on it
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
      render :new, status: :unprocessable_content
    end
  end
end
# User: validates :email_address, presence: true, uniqueness: true  (+ DB unique index)
#       password policy: see §2a — do NOT copy a bare `length: { minimum: 12 }`
```

Email confirmation: `generates_token_for :email_verification, expires_in:
1.day` + a mailer + a verify endpoint flipping `verified_at`. Roles: start
with a boolean/enum on `users` (`admin:boolean`, or
`enum :role, { member: 0, admin: 1 }`) — no gem needed. OAuth/SSO: add
`omniauth` on top of the same Session model when genuinely required.

## 2a. Password policy — what NIST requires, and the rule it forbids

`has_secure_password` gives you bcrypt, the `password`/`password_confirmation` virtuals, and a
validation *"that the password does not exceed the maximum allowed bytes for BCrypt (72 bytes)"*. It
gives you **no strength policy at all**, so a fresh app accepts `a` as a password. Adding one is
therefore an obligation, and the shape of it is not a matter of taste.

### The one rule everybody adds, that you must not add

**Do NOT require a mixture of character types.** *NIST SP 800-63B-4* is explicit, and it is a
prohibition rather than a preference:

> "Verifiers and CSPs **SHALL NOT** impose other composition rules (e.g., requiring mixtures of
> different character types) for passwords."

This is the single most common thing a team bolts on, and it makes passwords *worse*: it pushes users
toward `Passw0rd!` — short, predictable, and in every breach corpus — and away from a long passphrase
that is stronger by every measure. If a reviewer asks for "at least one uppercase, one digit and one
symbol", the answer is this citation.

### What is actually required

| requirement | strength | source |
|---|---|---|
| minimum **15** characters where the password is the *only* factor | **SHALL** | SP 800-63B-4 |
| minimum **8** where it is one factor of *multi*-factor | **SHALL** | SP 800-63B-4 |
| compare against a blocklist of known compromised / commonly used passwords, on establish **and** change | **SHALL** | SP 800-63B-4 |
| permit a maximum of at least **64** characters | SHOULD | SP 800-63B-4 |
| **no** periodic forced rotation | **SHALL NOT** | SP 800-63B-4 |

A Rails app with the generated session auth and no second factor is the **single-factor** case, so
the floor is **15**, not the 12 that reads as generous.

**The `-4` in those citations is load-bearing.** SP 800-63B-4 (July 2025) **supersedes** the 2020
edition, and the 15-character single-factor floor is *new in revision 4* — the superseded document
required 8. So a citation reading bare *"SP 800-63B"* points at a document that does not contain the
number in the row above it. Cite the revision, here and anywhere else this table is quoted.

The standard requires a forced change only on **evidence of compromise**, and forbids one on a
**schedule**. Neither of those covers the accounts sitting below a floor you have just raised — that
case has no upstream and is decided in *Accounts already below the floor* below.

**The maximum is already handled — do not add a second validator.** `has_secure_password` validates
the bcrypt 72-**byte** ceiling for you. Note that 64 *characters* is not 72 *bytes*: a passphrase in
a non-Latin script can exceed 72 bytes well under 64 characters, so the honest message on that
failure is about bytes, not "too long".

### Where it is enforced, and where it must not be

```ruby
# app/models/user.rb
class User < ApplicationRecord
  has_secure_password

  # `allow_nil: true` so ordinary updates (changing an email, a role) do not demand the password
  # again. `has_secure_password` still requires presence on create, so this does not open a hole.
  validates :password, length: { minimum: 15 }, allow_nil: true
  validate  :password_not_compromised, if: -> { password.present? }

  private

  def password_not_compromised
    return unless PasswordBlocklist.include?(password)
    errors.add(:password, :compromised)
  end
end
```

**Write paths only — registration and password reset.** Never on sign-in. Sign-in calls
`User.authenticate_by`, which verifies the stored digest; re-validating strength there would lock out
every account created before the policy existed, which is a self-inflicted outage rather than a
security gain. The accounts already under the floor are dealt with **after** authentication succeeds,
never during it — see *Accounts already below the floor* below.

### The blocklist is the requirement people skip

`SHALL`, not `SHOULD` — and it is the half that actually stops the passwords that get used. Two
implementations, and the trade-off is real:

- **A local list** (the top ~10k–100k breached passwords, shipped as a file). No network, no latency,
  no third party in the auth path, and it works in a validator. This is the default.
- **A range API** (Pwned Passwords k-anonymity: send the first 5 hex characters of the SHA-1, match
  the suffix locally). Vastly larger corpus; the full password never leaves the process. But it puts a
  network call on a write path, so it needs a timeout and a decision about what happens when the
  service is unreachable — **fail open or fail closed, chosen deliberately and written down.** A
  silent `rescue` that lets everything through is the `gate-that-cannot-fail` defect in your auth.

Whichever you choose, compare case-insensitively and after normalising whitespace, or `PASSWORD1`
walks past a list containing `password1`.

### Accounts already below the floor — our decision, not NIST's

Raising the floor does nothing to the accounts already under it. Leave them alone and a six-character
password survives indefinitely, so the policy binds precisely the users who were going to comply anyway.
The rule is the opposite: **once a user authenticates successfully, an account whose stored password does
not meet the current policy may reach one destination — the change-password screen — until it does.**

**Say where the authority comes from, because it is not the standard.** SP 800-63B-4 names exactly one
mandatory trigger — *"verifiers SHALL force a change if there is evidence that the authenticator has been
compromised"* — and a password merely shorter than a floor raised after it was set is not evidence of
anything. What the standard prohibits is **periodic** rotation (*"SHALL NOT require subscribers to change
passwords periodically"*), and this is not that: the trigger is a specific condition, it fires once, and it
stops firing the moment the condition is resolved. So NIST neither mandates this nor forbids it, and a
citation claiming otherwise would be invented. **It is our decision** (#484), on the grounds that a floor
binding only new accounts is not a floor.

**You cannot ask the digest — the app has to have written it down.** `password_digest` is a bcrypt hash;
there is no way to recover the length of what produced it, and that irreversibility is the property you are
paying for. So the app can never *discover* that a stored password is sub-policy. It must have **recorded
the policy in force when the password was set**. The careless implementation reaches for the digest and
finds nothing to measure; the next-least-careless one adds a `password_length` column, which answers the
question by handing anyone who reads the `users` table a head start on every account. What gets recorded is
one integer — the policy's own version, stamped at set-time:

```ruby
# app/models/password_policy.rb
module PasswordPolicy
  # Bump when the floor rises OR the blocklist is replaced. One number covers both, because both
  # mean the same thing: the rules changed after this digest was written.
  VERSION = 2
end
```

```ruby
# db/migrate/..._add_password_policy_version_to_users.rb
add_column :users, :password_policy_version, :integer, null: false, default: 0
```

**`default: 0` is the load-bearing part.** Every row that predates the column was set under a policy the
app cannot name, so it is stale by construction and gets the forced change. Defaulting to `VERSION`
grandfathers in exactly the accounts this exists for.

The stamp belongs on the model rather than in a controller, so every write path gets it — registration, the
generated token reset, and the change screen below — without any of them remembering to:

```ruby
class User < ApplicationRecord
  # has_secure_password + the length and blocklist validations from above

  before_save :stamp_password_policy_version, if: :will_save_change_to_password_digest?

  def password_policy_current? = password_policy_version >= PasswordPolicy::VERSION

  private

  def stamp_password_policy_version
    self.password_policy_version = PasswordPolicy::VERSION
  end
end
```

`has_secure_password`'s `password=` writes `password_digest`, so `will_save_change_to_password_digest?` is
true on exactly the saves that set a password and on no others. (`password_digest_changed?` means the same
thing inside `before_save` on Rails 8 and is not deprecated — the `will_save_change_to_` form just says out
loud which side of the save it is asking about.)

### The guard: inescapable, and escapable from

The user **is authenticated** — the digest matched, `authenticate_by` returned them, `start_new_session_for`
gave them a session. This is not a failed sign-in and must not be modelled as one. They are not signed out,
not locked, not rate-limited; they hold a valid session that can reach exactly one page.

```ruby
# app/controllers/concerns/password_policy_guard.rb
module PasswordPolicyGuard
  extend ActiveSupport::Concern

  included do
    before_action :require_current_password_policy
  end

  private

  def require_current_password_policy
    return unless authenticated?                      # nobody signed in: nothing to confine
    return if Current.user.password_policy_current?
    redirect_to edit_password_change_path,
                alert: "Our password policy changed — please set a new password to continue."
  end
end
```

```ruby
# app/controllers/application_controller.rb
class ApplicationController < ActionController::Base
  include Authentication
  include PasswordPolicyGuard   # AFTER Authentication: before_actions run in the order they are set
  allow_browser versions: :modern
end
```

**A guard that exempts by omission is not a guard.** It goes in `ApplicationController` so every controller
inherits it and every exemption is a line somebody had to write. Bolting it onto "the controllers that need
it" makes the coverage equal to whatever the next person remembered.

**A guard that also runs on the change screen is an infinite redirect.** The one page that can resolve the
condition has to sit outside it:

```ruby
# routes: resource :password_change, only: %i[edit update]
class PasswordChangesController < ApplicationController
  skip_before_action :require_current_password_policy   # or every visit redirects to itself

  def edit = @user = Current.user

  def update
    @user = Current.user
    if @user.update(params.expect(user: [:password, :password_confirmation]))
      redirect_to root_path, notice: "Password updated."
    else
      render :edit, status: :unprocessable_content
    end
  end
end
```

Nothing there stamps the version: the model's `before_save` does, so a successful update clears the guard as
a side effect of the same save that ran the length and blocklist validations. (Whether this screen should
also demand the *current* password is a separate question — worth yes, and independent of the guard.)

**`allow_unauthenticated_access` does not exempt this, and sign-out is the case that bites.** That macro is
generated code, not a framework method: the generator defines it as `skip_before_action
:require_authentication` — one callback, by name, with no knowledge of any other. (The same fact the
cross-plane section below leans on.) A second `before_action` therefore keeps running everywhere that macro
appears, so each page that must stay reachable needs its own named skip:

```ruby
class SessionsController < ApplicationController
  allow_unauthenticated_access only: %i[new create]
  skip_before_action :require_current_password_policy, only: :destroy   # let them leave
end

class PasswordsController < ApplicationController
  allow_unauthenticated_access                          # generated
  skip_before_action :require_current_password_policy   # the emailed reset link must still work
end
```

`only: :destroy` rather than the whole controller: a signed-in stale user who opens `/session/new` should
still be sent to the change screen, and the spec below asserts exactly that. Note also that sign-out is
exempted with `skip_before_action` and **not** by widening `allow_unauthenticated_access` — the generated
`terminate_session` calls `Current.session.destroy`, so an unauthenticated route into it raises on `nil`.
And `skip_before_action` defaults to `raise: true`, so a renamed or misspelled guard takes the app down at
boot instead of quietly exempting everything; leave that default alone.

The cost is one primary-key lookup per request on otherwise-public pages, and only where a session cookie is
present — `authenticated?` is `Current.session ||= find_session_by_cookie`, memoised for the request, and
the same lookup `require_authentication` already performs everywhere else.

**Existing sessions are not revoked.** Nothing about the session changes when the policy tightens; the guard
simply starts redirecting on the next request. Do **not** reach for `user.sessions.destroy_all` — that is
the response to *compromise*, and here it would achieve nothing anyway: the digest is still valid, so the
user signs straight back in (sign-in must not test strength, per the rule above) and arrives in the same
confined state one round trip later. Authentication still succeeds; only the set of reachable pages changed.

**The blocklist half is the same mechanism with a blunter cost.** A password that was acceptable yesterday
can be in a breach corpus tomorrow. The `SHALL` is scoped to the moment of writing — *"When processing a
request to establish or change a password, verifiers SHALL compare the prospective secret against a
blocklist"* — so nothing in the standard re-checks stored passwords, and nothing could: you hold the digest,
not the password. Refreshing the list therefore reaches existing accounts only by bumping
`PasswordPolicy::VERSION`, which forces a change on **everyone**, including the majority who were never on
it. That is the trade, it is not avoidable from the digest alone, and it should be stated rather than
dressed up as a targeted sweep. There is one honest narrowing: at sign-in you do hold the plaintext for that
one request, so a *successful* authentication can compare it against the refreshed list and, on a match,
stamp that single row stale — hitting only the affected accounts. Two constraints on it are absolute. It
runs **after** `authenticate_by` has returned a user, never inside the validation path; and it may only ever
move a stamp *down*. The moment it can change what sign-in returns, the strength check is back on the
sign-in path under a new name, with the lock-out that rule exists to prevent.

Specs for the guard — request specs, because what is under test is controller wiring, not a validation:

```ruby
RSpec.describe "the password policy guard", type: :request do
  let(:phrase) { "correct horse battery staple wharf" }
  let(:compliant) { create(:user, password: phrase, password_confirmation: phrase) }
  let(:stale) do
    # Stamped current by the model on create, then wound back: an account whose password was set
    # under an older policy is the only thing "sub-policy" can mean once the plaintext is gone.
    create(:user, password: phrase, password_confirmation: phrase)
      .tap { |u| u.update_column(:password_policy_version, PasswordPolicy::VERSION - 1) }
  end

  # Through the front door, per §1's `sign_in_as`: the subject is a user who authenticated
  # successfully, so a spec that forges the session is testing something else.
  def sign_in_as(user) = post(session_path, params: { email_address: user.email_address, password: phrase })

  it "confines an authenticated sub-policy user to the change screen" do
    sign_in_as stale
    get root_path
    expect(response).to redirect_to(edit_password_change_path)
  end

  it "leaves the change screen itself reachable" do        # otherwise: infinite redirect
    sign_in_as stale
    get edit_password_change_path
    expect(response).to have_http_status(:ok)
  end

  it "leaves sign-out reachable" do                        # otherwise: the user is trapped
    sign_in_as stale
    delete session_path
    expect(response).to redirect_to(new_session_path)
  end

  # The near-miss for `only: :destroy`: allow_unauthenticated_access must NOT exempt the guard.
  it "still confines them on a page that allows unauthenticated access" do
    sign_in_as stale
    get new_session_path
    expect(response).to redirect_to(edit_password_change_path)
  end

  # The other whole-controller exemption, and the one only a SIGNED-IN stale user can hit:
  # signed out, the guard no-ops anyway, so this carve-out is untested unless the spec signs in.
  it "leaves the emailed reset flow reachable" do
    sign_in_as stale
    get edit_password_path(stale.password_reset_token)
    expect(response).to have_http_status(:ok)
  end

  it "does not redirect a user whose password meets the current policy" do
    sign_in_as compliant
    get root_path
    expect(response).to have_http_status(:ok)
  end
end
```

### Specs (pure matchers, no browser)

```ruby
RSpec.describe User do
  it "rejects a password under the single-factor floor" do
    user = build(:user, password: "a" * 14, password_confirmation: "a" * 14)
    expect(user).not_to be_valid
    expect(user.errors[:password]).to be_present
  end

  it "accepts a long passphrase with no symbols or digits" do
    phrase = "correct horse battery staple wharf"
    expect(build(:user, password: phrase, password_confirmation: phrase)).to be_valid
  end

  it "rejects a known-compromised password even when it is long enough" do
    weak = "password12345678"
    expect(build(:user, password: weak, password_confirmation: weak)).not_to be_valid
  end

  it "does not demand the password on an unrelated update" do
    user = create(:user)
    expect(user.update(email_address: "new@example.com")).to be true
  end

  # THE REGRESSION THAT MATTERS: raising the floor must not lock out existing accounts.
  it "still authenticates a digest that predates the policy" do
    user = create(:user, password: "short-legacy", password_confirmation: "short-legacy")
    user.update_column(:password_digest, BCrypt::Password.create("short-legacy"))
    expect(User.authenticate_by(email_address: user.email_address,
                                password: "short-legacy")).to eq(user)
  end
end
```

The second example is the one that documents the policy: a passphrase with no digit and no symbol is
**valid**, and a spec asserting otherwise is asserting the rule NIST forbids.

### The UI half

A live strength meter is worth having, and its contract is `design-system` → **Password strength**. It **may not render a character-class checklist** — that
is the prohibited rule wearing a progress indicator, and it teaches the user that `Passw0rd!` beats a
passphrase. What it can honestly show: length progress toward the floor, the confirmation-match
state, and the server's blocklist verdict. See `design-system` → forms for the component contract.

## 2b. Multi-factor — Rails ships none, and §2a already depends on it

§2a's table drops the password floor from 15 to **8 when the password is one factor of multi-factor**.
That is a conditional discount, and until this section existed the skill gave a reader **no way to
satisfy the condition** — which is the re-invented-per-app failure the policy was written to stop.

### What Rails 8 actually ships: nothing

**Verified against the installed gem**, not assumed: `railties` →
`lib/rails/generators/rails/authentication/`. The generator produces two migrations — the entire
persisted surface —

```ruby
generate "migration", "CreateUsers", "email_address:string!:uniq password_digest:string!", "--force"
generate "migration", "CreateSessions", "user:references ip_address:string user_agent:string", "--force"
```

and a case-insensitive sweep of the generator tree for `totp|webauthn|passkey|two.factor|mfa|otp` returns
**zero**. There is no `otp_secret`, no recovery-code table, no second-factor step in `SessionsController`.
*(Checked on 8.1.1 here and 8.1.3 elsewhere — same result. Re-check when the version in scope moves.)*

### What it does give you to build on

- **`authenticate_by` verifies multiple stored secrets in one timing-hardened call.** It partitions its
  arguments and requires **all** password-type ones to match. Useful, and **not** a TOTP mechanism: a
  TOTP is derived from a clock, so there is no stored digest to compare, and it cannot use this path.
- **The `Session` model is a row**, not a cookie payload. That is the hook: a session can record whether
  the second factor was satisfied, and be denied privileges until it is.
- **`Current`** carries the session per request, so the check is a `before_action` like any other.

### The one thing everybody gets wrong: replay

> "Verifiers **SHALL** accept a given OTP only once while it is valid to provide *replay resistance*."
> — SP 800-63B-4

`rotp` tells you whether a code is **valid right now**. It does not tell you whether it has **already
been used**. So `if totp.verify(code)` — the form our own `ecosystem-gems.md` used to suggest — accepts
the same six digits repeatedly for the whole window. That is not a second factor; it is a decoration
that looks like one.

**Record the last accepted timestep against the user and refuse a repeat**, inside the same transaction
that marks the session verified. `rotp`'s `verify(code, after:)` exists for exactly this — pass the last
accepted value, and it will not re-accept it.

### The second thing: MFA is a property of the SESSION, not of the user

A `user.mfa_enabled?` boolean answers the wrong question. The question at request time is *"has **this
session** satisfied the second factor?"* — otherwise every existing session silently becomes
multi-factor the moment the user enrols, including one an attacker already holds.

So the flag lives on the session row, it is set only after a verified code, and **enrolling must not
retroactively bless sessions that predate it**.

### SMS: restricted, not banned — and the popular claim is wrong

The widely repeated line that "NIST deprecated SMS" **is not what the standard says**, and shipping that
claim would be the same defect as any other unverified assertion. SP 800-63B-4:

> "Use of the PSTN for out-of-band verification is **restricted** … and **SHALL** satisfy the
> requirements of Sec. 3.2.9."

*Restricted* is a defined status with obligations, not a prohibition. If you offer SMS you owe:

- **an alternative** — *"verifiers SHALL ensure that alternative authenticator types are available to
  all subscribers"*;
- **a warning** — the CSP *SHOULD* remind subscribers of the limitation before binding a device;
- **risk signals** — *SHOULD* consider device swap, SIM change, number porting before delivering a
  secret over the PSTN.

Ours, on top of that: prefer TOTP or a passkey, and if SMS exists at all it is the **fallback**, never
the only option — which the first obligation makes mandatory anyway.

### Recovery codes are a set, and each is single-use

One `password_digest`-shaped column holds one secret; recovery codes are a **set**, so they need their
own table with one row per code and a `used_at`. Hash them like passwords — they are password-equivalent
— and show them **once**, at generation. A recovery code you can re-read in the UI is a second password
stored in plaintext-equivalent form.

### What is ours and what is a gem

**Ours** (this doctrine): where the flag lives, the replay rule, the enrolment-does-not-bless-old-sessions
rule, recovery-code storage and single-use, the SMS obligations, and the `before_action` shape.

**A gem** for the primitives only — `rotp` for TOTP arithmetic, `webauthn` for passkeys. Neither decides
any of the rules above, and both are chosen by the app rather than mandated here; naming a version in
doctrine would rot.

### Rate limiting, and a trap

`rate_limit` defaults to `by: -> { request.remote_ip }`. NIST's throttling obligation is **per account**,
so an IP-keyed limiter lets an attacker spread guesses across addresses against one user. Key the
second-factor limiter by the **user**, and note that the existing caveat about a `:null_store` cache
making `rate_limit` a no-op would then be silently disabling a `SHALL`.

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
- **`render json:` no longer HTML-escapes** — `load_defaults 8.1` sets
  `config.action_controller.escape_json_responses = false`, so the JSON renderer stops
  escaping `<`, `>`, `&`, U+2028 and U+2029. Rails' own changelog names the risk:
  *"vulnerabilities when the resulting JSON is embedded in HTML"*. The payload is fine
  while it is **consumed** as `application/json`; it is dangerous the moment a JSON body
  is inlined into a document. So:
  - **Never inline JSON into HTML raw.** In a template the Rails idiom is
    `<%= raw json_escape(@user.to_json) %>` inside a `<script>` — `json_escape` escapes
    all five characters itself and is untouched by the 8.1 flips. Better still, ship it
    as `<script type="application/json">…</script>` and `JSON.parse` it client-side.
  - Per-response restore: `render json: @posts, escape: true`.
  - **Do not** restore it globally with
    `config.action_controller.escape_json_responses = true` — 8.1 deprecates that
    assignment (*"is deprecated and will have no effect in Rails 8.2"*).
  - JSONP is **only partly** exempt. With `:callback` present the renderer skips the flip, so
    `<`, `>` and `&` are still escaped — but U+2028/U+2029 are not, because those are
    governed by the separate global flip below, which has no `:callback` carve-out. Read
    Rails' *"escaping will still occur when the `:callback` option is set"* as covering the
    HTML entities only.
- **`to_json` no longer escapes the JS line separators either** —
  `load_defaults 8.1` sets `config.active_support.escape_js_separators_in_json = false`,
  so U+2028/U+2029 pass through **everywhere** `ActiveSupport::JSON` encodes, views
  included — a wider blast radius than the controller flip above. `<`, `>` and `&` are
  still escaped there (`escape_html_entities_in_json` is untouched). Rails' stated
  reasoning is that ECMAScript 2019 made both characters legal inside JS string literals,
  so this is a behaviour change rather than a hole; `j`/`escape_javascript` and
  `json_escape` still escape them, which is one more reason the bullet above is the rule.
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
  `raise_on_open_redirects`; **8.1 *added* `action_on_open_redirect`**
  (`:log` / `:notify` / `:raise`) and the `load_defaults "7.0"` block sets it to
  `:raise`, so a fresh 8.1 app still raises. It did **not replace** the older flag:
  `raise_on_open_redirects` is still a live mattr (default `false`) and still takes
  precedence — the moment it is true the redirect raises whatever
  `action_on_open_redirect` says. **"Another host" is an exact host match — subdomains
  count**, so `app.` → `admin.` is a cross-host redirect.
  - **The reverse precedence is the trap on an upgrade.** An app that *explicitly* sets
    `config.action_controller.raise_on_open_redirects = false` has its framework-default
    `action_on_open_redirect = :raise` **silently downgraded to `:log`** — open redirects
    then warn and proceed. Rails does emit the "deprecated" warning, but only for apps
    that set the old key at all. Delete the old setting rather than carrying it forward.
  - **Prefer `config.action_controller.allowed_redirect_hosts` (new in 8.1) over
    `allow_other_host: true`.** The flag disables the check for that *entire call*;
    the allowlist permits only the hosts you name and keeps every other host blocked.
- **Path-relative redirects raise under `load_defaults 8.1`** — the sibling protection
  in the same area, and the one that catches new code. A `String` target starting with
  neither `/`, `?`, a scheme, nor `//` has the current protocol and host prepended
  **with no separator**, so `redirect_to "example.com"` sends the browser to
  `http://yourdomain.comexample.com` and `redirect_to "@attacker.com"` sends it to
  `http://yourdomain.com@attacker.com` — which browsers read as `userinfo@host`, i.e. a
  redirect to the attacker's site. `config.action_controller.action_on_path_relative_redirect`
  takes `:log` (the mattr default) / `:notify` / `:raise`, and **`load_defaults 8.1` sets
  `:raise`**, raising `ActionController::Redirecting::PathRelativeRedirectError`. Fix the
  target — a path helper, or a leading slash — rather than lowering the setting.
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

**They need *different* fixes, and this is the part to get right — one stub does not cover both.**

The single-use marker goes through `Rails.cache` directly, so a per-example stub works:

```ruby
before { allow(Rails).to receive(:cache).and_return(ActiveSupport::Cache::MemoryStore.new) }
```

**`rate_limit` cannot be stubbed that way at all.** It counts through
`config.action_controller.cache_store`, not `Rails.cache` — and the signature is
`rate_limit(to:, within:, …, store: cache_store)`, so that default is evaluated **when the
class body loads** and captured in the `before_action` closure. By the time an example runs,
the store is already bound. `allow(Rails).to receive(:cache)` never reaches it, and the spec
goes green while the limiter does nothing.

Give the limiter a real store in the test environment instead, and clear it between examples —
it is one instance per process, so counts otherwise accumulate across examples and the suite
becomes order-dependent:

```ruby
# config/environments/test.rb
config.cache_store = :null_store                          # keep general caching inert
config.action_controller.cache_store = :memory_store      # but let the limiter actually count

# spec/rails_helper.rb
config.before { ActionController::Base.cache_store.clear }
```

Then assert **both** edges — that it trips past the limit and does *not* trip inside it — and
prove the spec can fail by reverting the store to `:null_store` once. A throttle spec that has
never failed on purpose is indistinguishable from no spec at all.

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


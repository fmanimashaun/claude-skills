# Enterprise SSO — multi-tenant OIDC and SAML

The Rails 8 authentication generator owns sessions (`Session`, `Current.user`,
`start_new_session_for`). SSO changes how identity is *proven*, never how sessions
work: OmniAuth is the handshake layer in front of the generator, and everything
downstream sees an ordinary session. OIDC is the default protocol — every major
IdP (Entra, Okta, Google Workspace, Auth0, Keycloak) speaks it, and one generic
strategy serves them all. SAML is the escape hatch for IdPs that can't
(ruby-saml's signature-bypass CVE history is the reason it isn't the default).
Never Devise `:omniauthable`; never Rodauth (replaces the session machinery).

## Gems

```ruby
gem "omniauth"
gem "omniauth-rails_csrf_protection"   # POST-only request phase, CSRF-verified
gem "omniauth_openid_connect"          # one strategy for every OIDC IdP
# gem "omniauth-saml"                  # only when the SAML hatch opens
```

## Schema

`sub` is unique only *per issuer* — the identities uniqueness key MUST include
the issuer or two tenants' IdPs can collide. Identity is keyed on issuer+sub,
NEVER on email (email changes at the IdP would duplicate users).

```ruby
create_table :sso_configurations do |t|
  t.references :workspace, null: false, foreign_key: true, index: { unique: true }
  t.string  :issuer, null: false          # the real OIDC issuer URL — discovery needs it
  t.string  :client_id, null: false
  t.text    :client_secret, null: false   # text + encrypts; :string truncates SAML certs
  t.string  :allowed_domains, array: true, default: [], null: false
  t.jsonb   :role_mappings, default: {}, null: false   # {"IdP group/role" => "app_role"}
  t.boolean :enabled,  default: false, null: false     # enabled ALLOWS
  t.boolean :enforced, default: false, null: false     # enforced REQUIRES
  t.timestamps
end

create_table :identities do |t|
  t.references :user, null: false, foreign_key: true
  t.string :provider, null: false   # "oidc" / "saml"
  t.string :issuer,   null: false
  t.string :uid,      null: false   # OIDC sub / SAML NameID
  t.timestamps
end
add_index :identities, [:provider, :issuer, :uid], unique: true
```

Model: `encrypts :client_secret` (Rails 8 encryption) and
`normalizes :issuer, with: ->(v) { v.strip.chomp("/") }`. Store the issuer and use
`discovery: true` — never hand-entered authorization/token endpoints (no jwks
rotation, weakened issuer validation).

## Middleware — per-tenant dynamic setup

```ruby
# config/initializers/omniauth.rb
OmniAuth.config.allowed_request_methods = [:post]

SSO_SETUP = lambda do |env|
  req    = Rack::Request.new(env)
  config = Workspace.find_by(subdomain: req.host.split(".").first)&.sso_configuration
  next env["omniauth.strategy"].fail!(:sso_not_configured) unless config&.enabled?

  env["omniauth.strategy"].options.merge!(
    issuer: config.issuer, discovery: true,
    scope: %i[openid email profile], response_type: :code,
    client_options: { identifier: config.client_id, secret: config.client_secret,
                      redirect_uri: "#{req.base_url}/auth/oidc/callback" }
  )
end

Rails.application.config.middleware.use OmniAuth::Builder do
  provider :openid_connect, name: :oidc, setup: SSO_SETUP
end
```

Every tenant registers the SAME redirect URI in their IdP. Login button is
`button_to` (POST) with `data: { turbo: false }`. For a single-IdP app, delete
the lambda and put the four options statically in the initializer.

## Callback

```ruby
# routes.rb
post "/auth/:provider",          to: "sessions/omniauth#passthru", as: :omniauth
get  "/auth/:provider/callback", to: "sessions/omniauth#create"
get  "/auth/failure",            to: "sessions/omniauth#failure"
```

```ruby
class Sessions::OmniauthController < ApplicationController
  allow_unauthenticated_access
  rate_limit to: 10, within: 1.minute, only: :create

  def create
    auth      = request.env["omniauth.auth"]
    workspace = Workspace.find_by!(subdomain: request.subdomain)
    config    = workspace.sso_configuration
    email     = auth.info.email&.downcase

    identity = Identity.find_by(provider: "oidc", issuer: config.issuer, uid: auth.uid)
    user = identity&.user || locate_or_provision_user(workspace, config, email)
    return reject("That account isn't permitted here.") unless user

    Identity.find_or_create_by!(provider: "oidc", issuer: config.issuer, uid: auth.uid) { |i| i.user = user }
    sync_role_from_claims(user, config, auth)   # IdP is authoritative — see JIT
    audit(workspace, user, "sso_login_success")
    start_new_session_for user
    redirect_to after_authentication_url
  rescue ActiveRecord::RecordInvalid, OmniAuth::Error => e
    audit(workspace, nil, "sso_login_failure", error: e.class.name)
    reject("Single sign-on failed.")
  end

  def failure  = redirect_to(new_session_path, alert: "Single sign-on failed.")
  def passthru = head(:not_found)

  private

  def reject(msg) = redirect_to(new_session_path, alert: msg)

  # THE rule: assertions from a workspace's IdP may only ever grant access to
  # THAT workspace. Never match emails globally — a tenant admin controls their
  # own IdP and can assert any address (cross-tenant account takeover).
  def locate_or_provision_user(workspace, config, email)
    return nil if email.blank?
    user = workspace.users.find_by(email_address: email)
    return user if user
    return nil unless config.allowed_domains.include?(email.split("@").last)
    workspace.users.create!(email_address: email, password: SecureRandom.hex(32))
  end
end
```

## JIT role provisioning

Mappings are per-workspace data (`role_mappings`), never hardcoded group names.
Re-sync on EVERY login — the IdP is authoritative for roles under SSO; document
that to tenants. Hard ceiling: claims may assign member/manager tiers, never
owner/admin. SAML multi-valued groups need `auth.extra.raw_info.multi(:groups)`;
on Entra prefer the `roles` claim (app-role assignments) over `groups` — no
150-membership overage indirection.

## Enforcement (SSO-forced login)

`enabled` allows; `enforced` requires — conflating them blocks passwords during
rollout and during IdP outages. Guard BOTH password surfaces: `Sessions#create`
AND `Passwords#create` (the reset email is the classic bypass). Exempt the
workspace **owner** (role-derived, not a settable boolean) as break-glass against
tenant lockout — and audit every break-glass password login. UI law: enforcement
cannot be switched on until a successful test login has completed through the
new configuration.

## Tenant self-service dashboard

Admin-only AND step-up (recent password re-auth) — SSO config is an
account-takeover lever. The secret field is WRITE-ONLY: blank on edit, show a
fingerprint, update only when present; never re-render stored credentials into
HTML. Show the SP panel: redirect URI, entity ID, metadata URL. Audit every
change with sensitive values redacted — `saved_changes` includes secrets and
`filter_parameters` does not reach it.

Ship a provider-tabbed setup guide in the dashboard: OIDC instructions first per
vendor (issuer + client ID + secret), SAML behind a tab; advertise only endpoints
actually implemented (no SLO line unless enabled); one exact claim name per
attribute, vendor variants mapped server-side; always include the
"assign users/groups to the app" step — its omission is the #1 setup ticket
(`AADSTS50105` on Entra, bare 403 on Google Workspace).

## SAML hatch (only when an IdP can't do OIDC)

Second provider behind the same identities/callback architecture. IdP cert in a
`text` column, full-cert pinning (never fingerprint-only). Sign with a single
global SP keypair from credentials:
`security: { authn_requests_signed: true, want_assertions_signed: true,
signature_method: <RSA_SHA256>, digest_method: <SHA256> }` — verify the exact
constants against the installed ruby-saml. SP-initiated only by default;
IdP-initiated flows are replay-prone. SP metadata endpoint per tenant:
`settings.sp_entity_id = "https://#{request.host}"` (the SP's identity — never
the IdP's), ACS URL, render `OneLogin::RubySaml::Metadata.new.generate(settings)`.

Validate certificates as data, at save time:

```ruby
normalizes :idp_cert, with: ->(pem) {
  body = pem.to_s.gsub(/-----(BEGIN|END) CERTIFICATE-----|\s+/, "")
  "-----BEGIN CERTIFICATE-----\n#{body.scan(/.{1,64}/).join("\n")}\n-----END CERTIFICATE-----\n"
}

def idp_cert_is_valid_x509
  cert = OpenSSL::X509::Certificate.new(idp_cert)
  errors.add(:idp_cert, "expired #{cert.not_after.to_date}") if cert.not_after < Time.current
  errors.add(:idp_cert, "is not yet valid")                  if cert.not_before > Time.current
  self.idp_cert_not_after   = cert.not_after
  self.idp_cert_fingerprint = OpenSSL::Digest::SHA256.hexdigest(cert.to_der).scan(/../).join(":")
rescue OpenSSL::X509::CertificateError
  errors.add(:idp_cert, "is not a valid X.509 certificate — paste the full PEM")
end
```

Rotation: store an `idp_metadata_url` per tenant and poll it daily (Solid Queue
recurring job, ruby-saml `IdpMetadataParser#parse_remote`) — new certs auto-stage
into `idp_cert_multi`, pruned by expiry, never removed until a login verifies
under the successor; audit every change. The `not_after` captured above feeds
admin alerts at 30/14/3 days. Manual two-slot rotation is the fallback when an
IdP publishes no metadata URL. All of this is SAML-only — OIDC discovery rotates
keys via `jwks_uri` for free.

Logout: OIDC RP-initiated logout (redirect to the discovered
`end_session_endpoint`) is the default. SAML SLO only on customer demand, and
then: validate the signed LogoutRequest WITH settings first, terminate the
session second, and send a proper LogoutResponse back to the IdP — never
terminate-then-validate, never flash-and-forget.

## Audit events

Dedicated table for auth events (login success/failure, enforcement toggled,
break-glass login while enforced, domain-gate rejections); PaperTrail (with the
secret filtered) for config-change history. `user` optional; log error CLASSES
internally, never flash exception messages to users.

## Testing (pure RSpec, prove the new behavior)

`OmniAuth.config.test_mode = true` + `mock_auth[:oidc]` in a support file;
request specs with `host!` for tenancy. The proving set: happy-path session,
wrong-domain provisioning rejected, cross-workspace email isolation, identity
idempotency on repeat login, role assigned from mapped claims, IdP-authoritative
re-sync (mapping change reflected next login), enforced workspace rejects
password login, owner break-glass passes (and is audited), audit rows written
with secrets redacted.

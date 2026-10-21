# Rails security checklist (rails-stack)

`/rails-flow:secure-design` reads this file for a project whose stack is Rails, after it has drawn the data flow and the
trust boundaries. The detector names it: `detect_stack.py` lists it under `security` from this plugin's `stacks.json`
(`descriptor.security.checklist`), with the scanners the stack runs.

The process is the same for every stack (when to model, the template, `TM-n` ids, the audit before ready). This file is
only the Rails **surface**: the questions a STRIDE pass asks of a Rails app, each answered in the model as a row with a
decision (mitigate, transfer, accept, eliminate) and pointing at the doctrine that already says how. It adds no doctrine
of its own; the answers live in rails-stack's `skills/rails-8/references/`.

## Spoofing — who is this request from?

- Does the boundary sit behind the authentication concern, or is it opened on purpose with `allow_unauthenticated_access`?
  An opened route needs a rate limit and a reason (rails-stack's `skills/rails-8/references/auth-security.md`, §2b
  *Unauthenticated endpoints*).
- A webhook or callback: how is the sender proven (a signature over the raw body, a shared secret), and what happens to a
  request that fails it?
- A token or magic link: is it single-use, short-lived and bound to one purpose (`auth-security.md`, *Cross-plane sign-in*)?

## Tampering — can the input change what it must not?

- Mass assignment: which attributes does this boundary permit, and is the list explicit (`auth-security.md`, §4)?
- CSRF: does every state-changing browser request carry the token, and is any controller skipping the check? Say why.
- Raw SQL, `html_safe`, `raw` or a redirect to a parameter: each is a row of its own (`auth-security.md`, §4).

## Repudiation — can we show who did it?

- Is the action recorded with who, what and when, and can the application role rewrite that record?

## Information disclosure — what can leak?

- New personal data: is it classified (category, basis, retention), filtered from logs, and encrypted where it is
  verify-only or sensitive (`auth-security.md`, §4; `advanced-active-record.md`, *encrypts*)?
- Errors and responses: does a failure return more than the caller may see?

## Denial of service — what can be exhausted?

- Uploads and imports: size, count and archive-expansion ceilings before processing.
- Public writes: a rate limit, per the rails-flow gate that requires one on every unauthenticated write route.

## Elevation of privilege — who may do this?

- Authorization: is the check in a scope or a model predicate, not only in the view (`auth-security.md`, §3
  *Authorization the Rails way*)? Name the rule and the role.
- Tenancy: is every query for this boundary scoped to the tenant (`multi-tenancy.md`)?
- The database role the app runs as: may it do more than this boundary needs?

## Scanners this stack runs

`brakeman`, `bundler-audit` and `importmap audit`, as the descriptor lists them. A threat-model row a scanner covers says
which one, so the per-row audit (#2119) can point at its output.

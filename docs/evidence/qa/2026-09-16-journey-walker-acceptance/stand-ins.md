# Stand-ins run during the walk — 16 Sep 2026, Retask QA server http://127.0.0.1:3002

Rules applied: `plugins/qa-flow/reference/stand-ins.md` — only the two calls the plan declares
(`retask-plan.json` → `stand_ins`), run verbatim through the project's runner, and a stood-in step
proves nothing about itself.

The server on port 3002 is `puma` pid 45994 with cwd
`/private/tmp/claude-502/…/scratchpad/retask-walk` and no `RAILS_ENV` in its environment
(`ps eww 45994`), so it reads `retask_development` — the same database the runner below wrote to.
Checked before running anything.

## 1. E-signature — `Contract#record_signature!`

**Step replaced:** Applicant journey step 4, the vendor's Zoho Sign signature on contract
`vcn_1K3PHvaFpkZi` (W. Tester, Issued 16 Sep, read from Admin's `/contract-archive`). The Guest has
no sign control in the app (`/contract/signature` is *planned* in ROUTES.md and answers 404 by
fetch) and no Zoho mail is sent, so the walk could not reach the post-signature pages without it.

**Command, verbatim as declared, run at 2026-09-16T13:12:20Z:**

```
bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!' -- vcn_1K3PHvaFpkZi
```

**Result: failed, exit 1.**

```
app/models/contract.rb:112:in 'Contract#record_signature!': missing keyword: :document (ArgumentError)
    |   def record_signature!(document:, signer_ip: nil, now: Time.current)
```

The method the plan declares now requires a `document:` keyword (the executed PDF Zoho's webhook
downloads). Rule 1 of `stand-ins.md` forbids inventing an argument or a new transition, so the
step is **Blocked** and nothing was changed: `/application` still shows `Contract · Issued`, and
`/bank-details` still redirects to `/dashboard` with *"Bank details are asked for once a contract
is signed, and not before."* (screenshot `1440-guest-bank-details-after-standin-failed.png`).

Consequences recorded:

- `handoffs.csv` step "4 vendor signature" → **Blocked**, naming this command.
- `notifications.csv` `contract-executed` and `vendor-onboarding` → **Blocked** (never reached
  `contract.rb:187` / `:200`; and mail enqueued from a runner would die with the process under
  the async adapter in any case).
- **Finding F9**: the declared stand-in in `qa/qa.config.yml → walkthrough.stand_ins` is stale
  against the app it describes.

## 2. Provisioning — `Provisioning#activate!`

**Not run.** The journey never reached provisioning (it sits after signature → bank details →
vendor onboarding, all Blocked above), so there was no `Provisioning` record to stand in for.
Command as declared, for the record:

```
bin/rails runner 'Provisioning.find_by!(public_id: ARGV[0]).activate!'
```

## Not stand-ins, but worth saying

- **Admin sign-in.** The plan's recipe is `password`; the app refused it (*"That account signs in
  with Zoho."*, read from `#toasts` after `POST /login` → `/?as=staff&login=1`). I did not fall
  back to the fixture session cookie. I used the sign-in card's own fallback — *"Can't sign in? Get
  a one-time sign-in link"* — which sent a real mail I read from the dev inbox. That is a sign-in
  the person experiences, not a stand-in.
- **Freelancer sign-in.** The fixture `freelancer_magic_token` had expired (`exp
  2026-09-16T08:54:19Z`, walk at 13:09Z; the app answered *"That link has expired or has already
  been used."*). I requested a fresh one-time link for `sweep.freelancer@example.test` through
  `/login/link` and followed it from the inbox — the `magic-link` recipe, performed for real.
- Both one-time-link mails carry `http://localhost:3000/login/link/…` (the mailer's URL host);
  I substituted `127.0.0.1:3002` and kept the token unchanged.
- **Root** was not signed in: no `ROOT_ADMIN_PASSWORD` in the environment. Recorded Blocked.

# Journey walk — Retask (QA server http://127.0.0.1:3002, worktree `retask-walk`), 16 Sep 2026

Personas walked: **Guest** (new applicant `walk.20260916a@example.test`, created through `/apply`,
signed in with password + inbox code), **Admin** (`sweep.admin@example.test`, one-time link — the
`password` recipe was refused by the app), **Freelancer** (`sweep.freelancer@example.test`, fresh
one-time link — the fixture token had expired). **Root**: Blocked (no `ROOT_ADMIN_PASSWORD`).
**Requester**: not walked — outside the caller's three scoped legs and the ~90-minute time-box; no
requester page is reported. Viewports 1440 / 820 / 390 (390 by DevTools viewport emulation; the
window itself floors at 500px, and the one landing row first measured at 500 was re-measured).

Evidence: `pages.csv` (49 rows: 18 Pass, 26 Fail, 5 Blocked), `handoffs.csv` (8: 3 Landed,
1 Missing, 4 Blocked), `notifications.csv` (11: 3 Sent, 4 Missing, 4 Blocked), `stand-ins.md`, and
the screenshots in this directory. Both profiled CSVs pass `validate_evidence.py`.

Ranking: severity first, then reach (how many people / steps it touches).

---

## F1 · S1 — With Demo data off, Admin cannot offboard or suspend anyone (W5 and W6 are unreachable)

**Spec:** admin.md §4 W5 *"ADMIN INVESTIGATES → ADMIN DECIDES — cause + reason required"*; W6
*"Admin suspends with a required reason, and records a reason again when lifting"*; §5.2
*Suspensions — "Suspend for cause or lift, reason required"*; ROUTES.md `/offboardings` — *"every
row opens the decision"*; ROUTES.md Placeholders — *"off … an action writes a real record
(`AdminShell::LiveActions`) or is refused with its control disabled"*.

**What the page says vs the spec:** `/offboardings` (Demo data OFF — the header button `Demo data`,
`aria-pressed=false`, a form `POST /dev/mode`) lists two threshold flags (sweep.freelancer *"2 of 2 ·
Data entry turnaround 25.0%, Rejection rate 55.6%"*, sweep.reviewer) each with a live
**Investigate** link. Clicking either fetches
`GET /admin/actions/offboard/new?ref=usr_26mLasJEhRFY` → **404** (network reqid 370; second row
reqid 554) and the modal reads *"Not available — This action is not open to you: the record has
gone, it has already been decided, or it is routed to another role."* The control is not disabled,
as the ROUTES rule requires — it is offered and then refused. `/suspensions` says *"Nobody is
suspended … lifting it is one action here"* and has **no control to suspend**; the freelancer
detail `/admin/freelancers/usr_26mLasJEhRFY` has no suspend/offboard control (main contains links
only); `/performance-flags` is evidence-only by design.

**Mechanism (read, not guessed):** `app/controllers/admin/actions_controller.rb#set_action` calls
`AdminShell::Action.find(kind, ref:, demo: false, …)`. In `app/models/admin_shell/action.rb:28-46`
the live (`!demo`) branches cover `setting`, the four `STAFF_KINDS`, `onsite` and `issue` — there is
**no live branch for `offboard`, `suspend` or `lift`**, so the call falls through to
`Canvas.modal(kind, ref)`, which knows the canvas's sample refs (`OFF-FL-0073`) and not a real
`usr_…` public_id → `nil` → 404. Meanwhile `LiveActions::KINDS` (`live_actions.rb:20-23`) does list
`offboard suspend lift`, and `live_actions.rb:91` documents that the *only* place suspension
happens is inside this modal (*"suspend first (reversible), dismiss the flag, or offboard"*).

**Reproduction:** sign in as Admin → header `Demo data` off → Accountability › Offboarding flags →
Investigate. **HTTP 404**, final URL `/offboardings` (modal frame). Instances: 2 of 2 rows;
3 screens without a suspend control. Screenshots
`1440-admin-offboardings-demo-off.png`, `1440-admin-offboard-investigate-modal.png`,
`1440-admin-suspensions-demo-off.png`, `1440-admin-freelancer-detail-sweep-freelancer.png`.

**Consequence not testable:** because no decision could be made, the freelancer-side checks (W5
step 2 "no sign-in succeeds"; §9.1 shell *"Your access is paused…"*; claimed tasks released) are
**Blocked**, not passed. As sweep.freelancer (fresh link, 13:09Z) access was intact — the expected
state given nothing was decided.

---

## F2 · S1 — The applicant is told their contract is "signed on both sides" while it is merely Issued

**Spec:** freelancer.md §2 *"CONTRACT ISSUED → awaiting vendor signature (window:
contract_signature_window_days) … SIGNED → COUNTERSIGNED AUTOMATICALLY, the instant they sign"*;
F-29 *"no PDF is rendered before both signatures are recorded"*; the walker doctrine's own example
of an intent failure (*"signed on both sides" over a contract the spec calls issued*).

**What the page says:** `/application` for the walk's applicant, immediately after the pass:
*Where it is* — `Contract · Issued · September 16, 2026`; *What happens next* — **"Your contract is
signed on both sides. We will email you as your account is set up."** No one has signed: Admin's
`/contract-archive` row reads `vcn_1K3PHvaFpkZi · W. Tester · Issued`; no contract mail was sent
(inbox: one sign-in code); and `/bank-details` on the same account redirects with *"Bank details are
asked for once a contract is signed, and not before."* — the app contradicts itself two clicks
apart. There is no sign control anywhere for the Guest (`/contract/signature` is planned; fetch →
404), so the applicant is told there is nothing to do at the exact step where the funnel needs
them to act.

**Reproduction:** apply → pass the test → `/application`. **HTTP 200**, final URL `/application`.
Instances: 1 account, 3 widths. Screenshots `1440-application-thread-after-pass.png`,
`820-application-thread-after-pass.png`, `390-application-thread-after-pass.png`,
`1440-admin-contract-archive.png`, `1440-guest-bank-details-before-signature.png`.

---

## F3 · S1 — Four recruitment notifications exist in the catalogue and are never sent

**Spec:** F-31 (the catalogue is the send log); `app/models/notifications/catalogue.rb` keys
`application-received` (:28), `test-invite` (:46), `test-passed` (:65), `contract-issued` (:82);
freelancer.md §2 *"APTITUDE TEST issued automatically"*, *"CONTRACT ISSUED → awaiting vendor
signature"*; the Guest dashboard's own promise *"We'll email you at every step."*; the result page's
*"Your vendor contract … will arrive by email for signature."*

**Observed:** four server-side steps (account created 12:55Z, code verified, test submitted and
passed ~13:0xZ, contract issued) produced **one** mail: `Your Retask sign-in code`. The Guest's
`/notifications` agrees: *"1 notification · 1 unread"*. `grep -rn 'notify("' app` finds callers only
for `access-ended`, `contract-executed`, `payout-released`, `vendor-onboarding` — the four
Applicant-group templates have no caller. Rows in `notifications.csv`: `application-received`
(S3), `test-invite` (S2), `test-passed` (S2), `contract-issued` (S1 — it is the only way the
applicant could ever be asked to sign).

Screenshots `1440-inbox-after-apply-only-sign-in-code.png`,
`1440-inbox-end-of-walk-three-messages.png`, `1440-guest-notifications-send-log.png`.

---

## F4 · S2 — The new applicant lands on a dead end: `/dashboard` says "nothing to do" and links nowhere

**Spec:** freelancer.md §3 — five Guest screens, *My application: "Status, history, what happens
next"*; landing page STEP 2 *"Take the test — Straight away, on the platform"* and *"the test starts
right after it — one sitting"*.

**What the page says:** after the code, `/welcome` → *Go to dashboard* → `/dashboard`: h1 *"Your
application"*, copy *"Your application is in. We've got everything we need for now. We'll email you
the moment there's something to do."* `main` has **0 links**; the header account menu holds only
**Sign out**; there is no rail. The thread `/application` — which does say *"Take the aptitude test"*
with a **Take the test** link — is reachable only by typing its URL (taken from ROUTES.md 15.2).
With F3 (no `test-invite` mail) the applicant has no route to the assessment.

**Reproduction:** `/apply` → code → `/welcome` → `/dashboard`. **HTTP 200**. Screenshots
`1440-guest-dashboard-no-test-link.png`, `1440-welcome-offer-documents-ready-claim.png`,
`1440-application-thread-take-the-test.png`.

---

## F5 · S2 — Freelancer rail entries lead to "designed and not yet built" placeholders

**Spec:** walker rubric *"A rail entry that leads to a placeholder is a defect"*; freelancer.md §10
*My tasks — "Claimed and in progress, against the WIP limit"*, *Profile and documents*, *Close my
account*; §5 `wip_limit_per_freelancer` shown as *"3 of 5"*.

**Observed (signed in as sweep.freelancer):** rail **My tasks** → `/mine-tasks` 200: *"This screen
is designed and not yet built — F-14. My tasks is on its way"* — while the dashboard reports **"My
active tasks 13 · Claimed by you"** with no limit shown. Rail **Account** → `/account` 200: *"designed
and not yet built — F-03"*. `/close-my-account` is built (fetch 200, h1 *Close my account*) but
nothing in the rail leads to it, because its parent is the placeholder. Same-origin fetch of every
rail href: 2 of 10 destinations are placeholders (`/mine-tasks`, `/account`).

Screenshots `1440-freelancer-my-tasks-wip.png`, `1440-freelancer-account.png`,
`1440-freelancer-dashboard-after-magic-link.png`.

---

## F6 · S2 — "Overturn" is offered on a result whose contract has already issued

**Spec:** F-27 *"Admin override: only while the result is the applicant's current state — after a
contract issues the state has moved on (F3, D-025)"*; admin.md W7 `[derived]` *"The control is
available only while the result is the applicant's current state."*

**Observed:** `/test-results` row *"W. Tester attempt 1 · 100% 85% 0% Passed"* has an **Overturn**
link; `GET /admin/actions/aptitudeOverride/new?ref=apt_VBYuxRZneN4o` → **200** and the modal offers
*"Record as: Failed — The application is closed"* with a reason field — while the same applicant's
contract is `Issued` in `/contract-archive`. The modal's own footnote says *"Only while this is the
applicant's current result"*. Not submitted (it would close a live contract). Screenshots
`1440-admin-overturn-modal-on-issued-contract.png`, `1440-admin-test-results.png`.

---

## F7 · S3 — The aptitude test is not the work screen: one block, no split view, no timer, and a reload wipes the typing

**Spec:** freelancer.md §3 *"Aptitude test — Two parts, generated per attempt, same split-screen
interface as real work … The test is the interface"*; §5 *"The work screen — split view. Scan left …
entry form right … autosave, no explicit save"*; `aptitude_tests_controller.rb#show` *"a browser
refresh must not spend it"*.

**Observed:** `/aptitude-test` renders a typed value strip (*Full name Amaka Olawale · Date of birth
25th August @026 · Plan name — · Phone 0872113994 …*) above six inputs in a single **Principal**
block — not scan-left/form-right, and one form, not two parts; *"About 45 minutes"* with no
countdown (`@minutes` is computed in the controller; nothing on the page shows it). Changing the
viewport emulation reloaded the page: the **same attempt resumed** (same values — the controller's
promise holds) but **every typed value and every flag was gone** (DOM query after reload: all
`blocks[principal][values][*]` empty, `flags` []). The eight defect categories are named on screen
(Pass). Test taken faithfully — copy as printed, three planted faults flagged (unreadable date, plan
blank, phone digit count) — result 100 / 85 / 0, Passed. Screenshots
`1440-aptitude-test-split-screen-start.png`, `1440-aptitude-test-filled-three-flags.png`,
`820-aptitude-test-filled-three-flags.png`, `390-aptitude-test-filled-three-flags.png`,
`1440-aptitude-result-after-submit.png`.

---

## F8 · S3 — Figures that disagree with each other on the same or adjacent Admin screens

**Spec:** admin.md §5.2 Applicant pipeline *"Applications by state and country"*; ROUTES.md
`/contract-archive` *"how long is left to sign"*; §5 *"Each row shows item count, age…"*.

- `/applicants`: **"Passed the rubric 2 — All time, after any override"** vs *By country* Passed
  **1 + 0 + 0**. Same page.
- `/applicants`: **"Contracts issued — (Arrives with contract signature (F-29))"** vs
  `/contract-archive` listing **four** Issued contracts, including the one issued during the walk.
- `/contract-archive`: **Signature window "—"** on every Issued row — the one figure the route
  promises; the `State` column shows account states (*Active, Provisioned, Vendor approved*).
- `/freelancers` roster: **"sweep.freelancer … 5 active"** vs that person's own dashboard **"My
  active tasks 13"**.

Screenshots `1440-admin-people-pipeline-tally-mismatch.png`, `1440-admin-contract-archive.png`,
`1440-admin-freelancer-detail-sweep-freelancer.png`, `1440-freelancer-dashboard-after-magic-link.png`.

---

## F9 · S3 — The QA configuration no longer matches the app it drives (stand-in and two sign-in recipes)

**Spec:** `plugins/qa-flow/reference/stand-ins.md` rule 1 (a stand-in is a call the fixtures already
make); the plan's persona recipes.

- Declared stand-in `bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!'`
  → **ArgumentError: missing keyword: :document** at `app/models/contract.rb:112`. The signature
  step is un-walkable by the declared means (`stand-ins.md`).
- Admin recipe `password` → the app answers *"That account signs in with Zoho."* (`sessions_controller.rb:55`).
- Freelancer recipe `magic-link` from the fixture → token expired (`exp 08:54:19Z`, 15-minute
  lifetime, fixture minted 08:39Z) — *"That link has expired or has already been used."* Not an app
  defect; a fixture that cannot be reused after 15 minutes.
- Mailer links point at `http://localhost:3000`, not the QA server.

---

## F10 · S3 — No notification template exists for suspension, and suspend/lift send nothing

**Spec:** admin.md §7.2 *"Suspension applied or lifted → The freelancer, both addresses"*; §14.7a
*"Access locks the moment the person is notified"*.

**Observed:** `Notifications::Catalogue` has no suspension key (the only stopping template is
`access-ended`, :257), and `app/models/admin_shell/live_actions.rb` — where `suspend!`/`lift` are
applied — contains no mailer call (`grep -rn 'notify("' app` → mailer, `contract.rb`, `user.rb`
only). Recorded Blocked in `notifications.csv` because the step itself could not run (F1); it is a
catalogue gap the F-31 acceptance criterion cannot see.

---

## F11 · S4 — Copy that contradicts itself or the state of the account

- **Three labels for one page** (rubric: *"Three labels for one page is a defect"*): Admin
  `<title>` *Home — Retask* / h1 *Oversight* / rail *Dashboard*; Guest *Home* / *Your application* /
  header *Dashboard*; Freelancer *Home* / *Your work today* / *Dashboard*. 3 instances.
- `/welcome` to a brand-new applicant: *"Your application status and offer documents are ready."*
  There is no offer.
- One-time link: card says *"expires after 10 minutes"*, `/login/link/sent` says *"15 minutes"*;
  the token's `exp` is 15 minutes after send — the card is wrong. 2 instances (admin, freelancer).
- Sign-in-code mail on **account creation** says *"Someone signed in with your email address and
  password."*
- Test screen label *"Hmo"* for the HMO id.

---

## F12 · note — Suspensions and Offboarding flags live under Accountability; the spec files them under People

admin.md §5.2 lists both under PEOPLE; the app's People tab strip has neither and Accountability
carries both. `app/models/admin_shell.rb:32` calls the move deliberate. Spec drift, not a product
defect — recorded so the spec can be brought into line.

---

## What passed

Landing, apply wizard (3 steps, consent correctly gated on opening the privacy notice), code step,
`/application` thread structure and the *Take the test* link, aptitude scoring (faithful copy +
correct flags = 100/85/0 Pass), result page reporting accuracy and judgement apart, `/notifications`
as an honest send log, `/application/edit` restricting the editable fields, `/bank-details` gate,
Admin shell navigation at three bands (expanded rail 1440 → 72px icon rail 820 → drawer + hamburger
390, `aria-current` on the deepest item), `/performance-flags` being evidence-only. **Horizontal
overflow:** `main` never exceeded its client width on any recorded page at any width; the only
`overflow-x` container wider than itself was `/offboardings`'s table wrapper at 390 (`div.scroll-x`
548 > 348) — the permitted table-scroll fallback.

## What I could not do, and why

- **W5 / W6 as Admin and their consequence as the freelancer** — the only linked control 404s and no
  suspend control exists (F1). Blocked.
- **Signature → countersignature → bank details → vendor onboarding → provisioning** — no Guest sign
  control, no Zoho, declared stand-in broken (F9). Blocked; the second stand-in never had a record
  to act on.
- **Root** — no `ROOT_ADMIN_PASSWORD`. Blocked.
- **Requester** — not walked (scope and time-box). Not reported.
- **Admin `password` recipe** — refused by the app; signed in via the card's own one-time link.

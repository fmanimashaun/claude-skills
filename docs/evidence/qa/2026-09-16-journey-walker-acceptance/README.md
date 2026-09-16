# 2026-09-16 — `journey-walker` acceptance run against Retask

The acceptance criterion of #993, in its own words: *"Run against Retask on the same dev commit, it
independently finds at least #305, #311 and #312 (the three the shipped layers missed)."* This is
the record of that run.

## Verdict — the three were rediscovered, and eight more

| Retask issue, filed by hand on 16 Sep | the walk's finding | same mechanism? |
|---|---|---|
| **#305** applicant sent to a dashboard placeholder with no way to the test | **F4** (S2) | yes — `/dashboard` Guest empty state, 0 links, `/application` reachable only by URL |
| **#311** Admin cannot suspend, lift or offboard with demo data off | **F1** (S1) | yes — `AdminShell::Action.find` has no live branch for `offboard`/`suspend`/`lift`, so a real `usr_…` ref falls through to `Canvas.modal` and returns nil; both `/offboardings` rows 404 |
| **#312** a passed test sends no email, and the thread says "signed on both sides" over an `issued` contract | **F2** (S1) + **F3** (S1) | yes — `guest_applications/show.html.erb`'s `elsif @contract` branch, and four catalogue templates with no caller |

**Eight further distinct defects** the hand walk had not filed: F5 rail entries to placeholders, F6
"Overturn" offered on an already-issued result, F7 the aptitude test is not the work screen and a
reload wipes the typing, F8 figures that disagree across Admin screens, **F9 the QA configuration
itself is stale**, F10 no suspension notification, F11 copy contradictions, F12 a spec-drift note.

## What was verified by hand afterwards, not taken on the walker's word

An agent's report is a hypothesis, so the four load-bearing mechanisms were re-read in Retask's
source before this record was written:

- `app/models/admin_shell/action.rb:28-46` — the branch list is `LOCAL`, `setting`, `STAFF_KINDS`,
  `onsite`, `issue`, else `Canvas.modal`. **No `offboard`, `suspend` or `lift`.** (F1)
- `app/views/guest_applications/show.html.erb:62-65` — `elsif @contract` renders *"Your contract is
  signed on both sides"* for any contract that is not `awaiting_signature`. (F2)
- `app/models/notifications/catalogue.rb:28,46,65,82` define `application-received`, `test-invite`,
  `test-passed`, `contract-issued`; `grep -rn 'notify("<key>"' app/` returns **nothing** for all
  four. (F3)
- `app/models/contract.rb:112` — `record_signature!(document:, …)` requires a keyword the declared
  stand-in does not pass. (F9)

## How independent it was, stated plainly

The walker was **not told what to find**: no issue numbers, no titles, no expected defects. It was
told which journeys to walk (the applicant's, and Admin's W5/W6), given the spec documents and the
design doctrine as its rubric, and left to judge. That is the honest claim. It is **not** the
stronger claim that it chose its own route — the run was scoped to two legs and a ~90-minute box,
because a full five-persona walk is a working day. A scoped walk finding the three is evidence the
layer works; it is not evidence that an unscoped walk would find them in one pass.

## The run

- Target: Retask at `http://127.0.0.1:3002`, QA mode, booted from the worktree at `a4be146`
  (`ae2ee5e` plus the walkthrough config), same `retask_development` database as the runner.
- Personas walked: **guest** (a new applicant created through `/apply`, signed in with password +
  a code read from the dev inbox), **admin**, **freelancer**. `root` **Blocked** — no
  `ROOT_ADMIN_PASSWORD`. `requester` not walked (outside the two scoped legs).
- Widths: 1440, 820, 390 — the three bands `walkthrough_plan.py` requires.
- 48 screenshots were captured. **They are not committed here**: 16 MB of another app's screens do
  not belong in a marketplace repo. They are published on Retask's own evidence branch, and the
  issues filed from this run embed them from there.

| artefact | rows | statuses |
|---|---|---|
| `pages.csv` | 49 | 18 Pass · 26 Fail · 5 Blocked |
| `handoffs.csv` | 8 | 3 Landed · 1 Missing · 4 Blocked |
| `notifications.csv` | 11 | 3 Sent · 4 Missing · 4 Blocked |

Both new profiles were validated by the gate they ship with, and both pass:

```
python3 plugins/qa-flow/scripts/validate_evidence.py docs/evidence/qa/2026-09-16-journey-walker-acceptance/handoffs.csv
python3 plugins/qa-flow/scripts/validate_evidence.py docs/evidence/qa/2026-09-16-journey-walker-acceptance/notifications.csv
```

## What the run taught us about the layer itself

- **The stand-in rules held under pressure.** The declared e-signature call raised
  `ArgumentError: missing keyword: :document`. Rule 1 forbids inventing an argument, so the walker
  stopped, recorded the step **Blocked**, and filed the staleness as F9 — rather than reaching for
  a different method and reporting a journey it had not walked. That is the behaviour the rules
  exist for, observed rather than asserted.
- **The sign-in recipes earned their place.** The plan's `password` recipe for admin was **refused
  by the app** (*"That account signs in with Zoho."*) and the fixture's freelancer magic token had
  expired. The walker did not fall back to a session cookie; it used the app's own one-time-link
  path and read the mail. A cookie-only walk would have skipped both sign-ins and reported nothing
  about either.
- **`handoffs.csv` is where the layer pays.** Its one `Missing` row is the applicant→applicant
  notification gap; the four `Blocked` rows are all downstream of the stand-in failure, and they
  say so. A page-only sweep would have recorded those pages as simply unvisited.

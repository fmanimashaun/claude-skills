# Hotwire frontend architecture: claims to verify (#2223, phase 1)

Status: **phase 1, verification only. No skill text is edited by this file.** Written for the maintainer and the coordinator; the React counterpart is #2222 (claude-skills-40), same layer headings. Owner direction is quoted on #2220.

Versions in scope: Turbo 8.0.23, Stimulus 3.2.2, turbo-rails 2.0.23 (`plugins/rails-stack/skills/hotwire/SKILL.md:42-53`), Rails 8.x.

Layer headings (agreed with claude-skills-40): 1 Composition · 2 Shell, navigation and page templates · 3 Regions and flow · 4 Data and state · 5 UX · 6 Performance · 7 Security · 8 Anti-patterns that bite (the closing table below: every row marked A).

## A. What the skills already say (file:line, measured with grep over `plugins/rails-stack/skills`)

| layer | `hotwire` skill | `rails-8` skill | gap |
|---|---|---|---|
| 1 Composition | `stimulus.md:23` (scopes), `:354-368` (patterns and anti-patterns), `production.md:639-769` (Stimulus at 35 and 69 controllers) | `views-hotwire.md:18-47` (layouts, partials), `:247` (Stimulus), `ecosystem-gems.md:48,469,534` (ViewComponent vs partials) | no rule on frame granularity, duplicate DOM ids, controller cleanup |
| 2 Shell, navigation, templates | `turbo.md:17-39` (Drive), `:40-97` (attributes, caching) | `views-hotwire.md:125` (Drive) | page templates and the shell live in `design-system`, not here; no rule on what the Drive cache restores |
| 3 Regions and flow | `turbo.md:156-200` (Frames), `:201-335` (Streams, delivery), `production.md:72-398` (streams at scale) | `views-hotwire.md:145-223` (frames, streams), `:289` (choosing the tool) | breaking out of a frame, `Accept`-based fallback, OAuth with Turbo |
| 4 Data and state | `stimulus.md:208` (values), `:354-368` (state in values) | `views-hotwire.md:60-98` (forms) | no single statement of where state lives (server, DOM, value) |
| 5 UX | `turbo.md:389-436` (a failed request), `:25-29` (303 and 422), `production.md:141,314` | `views-hotwire.md:60-98`, `:186` | loading and busy states, submit feedback, progressive enhancement |
| 6 Performance | `turbo.md:175,439` (lazy and eager frames), `:40-97` (prefetch) | `performance-caching.md:71-?` (fragment, Russian-doll), `:173,251` (N+1) | prefetch hazard, N+1 in broadcast partials, `touch: true` |
| 7 Security | none for streams | `views-hotwire.md:45-46,96-97`, `auth-security.md:648,682,731-734` (escape, CSRF, CSP nonce) | **nothing on authorizing Turbo Stream subscriptions or broadcasts**: `grep -in 'signed\|verified'` over `hotwire/references` and `rails-8/references/jobs-and-realtime.md` finds only `production.md:580-594` (Action Cable callbacks) |

## B. Candidate claims

Each is one precise claim with its failure and fix. **None is doctrine until the verdict column says CONFIRMED against the official source for the version in scope.** "Tool" is whether Brakeman or erb-lint already catches it (to be verified too).

| id | layer | kind | claim | failure it causes | fix | enforcement (owner ruling: a rule that is not enforced is not shipped) |
|---|---|---|---|---|---|---|
| H1 | 1 | P | A Turbo Frame is an independent region identified by `id`; the response to a request made inside a frame must contain a `<turbo-frame>` with the same `id`, conventionally `dom_id(record)` | the frame shows "Content missing" and nothing updates | wrap the response body in the same `turbo_frame_tag dom_id(record)` | **1 mechanical (rendered).** The qa-flow crawl judge fails any page whose DOM holds `.turbo-frame-error` or that fired `turbo:frame-missing`; negative fixture: a page with a frame link to a response lacking the frame |
| H2 | 1 | A | Duplicate DOM `id`s on one page break Turbo Stream and Frame targeting | a stream `replace`/`update` hits only the first element with that id; the others never change | give every repeated element an id from `dom_id(record)` | **1 mechanical (rendered).** Duplicate-id finding in the crawl's markup-integrity judge (the Retask `markupFindings` check, to be generalised into qa-flow); fixture: two rows sharing an id |
| H3 | 1 | P | A Stimulus controller keeps no state that must survive navigation in instance fields; state lives in `values`, `classes` and targets, i.e. in the DOM | after a Turbo Drive restoration visit the cached DOM returns without the instance state | use the values API (`static values`) | **3 review verdict.** "State that must survive navigation lives in values" is a judgement; reviewer records pass/fail per controller touched, `check_review_record.py` refuses a PR with a missing verdict |
| H4 | 1 | A | A Stimulus controller that adds listeners, timers or third-party instances in `connect()` must undo them in `disconnect()` | handlers and instances accumulate across Turbo navigations and cached restores | symmetric `disconnect()` cleanup | **not shipped as written** (INCONCLUSIVE). Narrowed form (timers and window/document listeners added in `connect()` need a `disconnect()`) is **1 mechanical** (JS lint) once re-verified |
| H5 | 1 | A | Stimulus controllers do not build HTML strings to update the page; the server returns a Turbo Stream or Frame | the markup duplicates server templates and drifts | request a stream/frame | **1 mechanical**, recorded as the maintainer's decision (no upstream rule): lint for `innerHTML =` and HTML template literals in controllers |
| H6 | 2 | P | Turbo Drive keeps a snapshot cache for back/forward; ephemeral UI (open menu, toast) is removed before caching, with `data-turbo-temporary` or a `turbo:before-cache` handler | the restored page shows stale open UI | mark or reset it | **3 review verdict** (open UI reset before cache); no mechanical test of "ephemeral" |
| H7 | 2 | P | Turbo Drive: `data-turbo-track="reload"` on asset tags forces a full reload when the asset fingerprint changes | a deploy leaves a stale bundle running against new HTML | `data-turbo-track: "reload"` on the stylesheet and importmap tags | **1 mechanical.** Layout check: stylesheet and importmap tags carry `data-turbo-track="reload"`; fixture: layout without it |
| H8 | 3 | P | A successful form submission answers with a redirect (303); a failed validation re-renders with 422 | Turbo does not render a 200 response to a form submit, so the page appears dead | `redirect_to ..., status: :see_other`; `render :new, status: :unprocessable_content` | **1 mechanical.** Check script: `render :new` or `render :edit` in a create/update branch without `status: 422` (either symbol), and a crawl console finding on "Form responses must redirect"; fixtures for both |
| H9 | 3 | A | A link or form inside a `<turbo-frame>` navigates that frame; to leave the frame use `data-turbo-frame="_top"` | a response that is a full page with no matching frame shows "Content missing" | `data-turbo-frame="_top"` on the link or form | **1 mechanical (rendered).** Same crawl judge as H1 (`turbo:frame-missing`); fixture: an in-frame link whose response has no frame |
| H10 | 3 | P | A controller action that answers a form with a Turbo Stream also answers HTML (`format.html`) | a client without Turbo, or a failed stream request, gets nothing usable | keep a `format.html` branch | **1 mechanical.** Check script: a `respond_to` with `format.turbo_stream` and no `format.html`; fixture: the bare case |
| H11 | 3 | A | OAuth sign-in through a Turbo-handled link or form fails because the redirect leaves the origin during a fetch | the sign-in click does nothing or errors | `data-turbo="false"` on the OAuth form or link | **not shipped** (INCONCLUSIVE, no citation). Needs an official source first |
| H12 | 4 | P | Where state lives, in order: the server and the URL first, then the DOM (`values`, `classes`) for UI state; never a client-side store that must be synchronised | two copies of the state disagree after a stream update | derive UI from server-rendered HTML and `data-*` values | **3 review verdict**, recorded as the maintainer's decision (state order is our stance, not upstream) |
| H13 | 5 | P | Turbo marks a busy frame with the `busy` attribute and a submitting form and `html` with `aria-busy="true"`; loading styles hang on those, with no script | a slow request gives no feedback | CSS on `turbo-frame[busy]`, `form[aria-busy="true"]` | **1 mechanical.** If the project has any `turbo_frame_tag ... src:` or lazy frame, its CSS must contain a `[busy]` or `[aria-busy]` rule; fixture: lazy frame, no rule |
| H14 | 5 | P | `data-turbo-submits-with` swaps a submit button's label and disables it during the request | double submits | set it on `submit` buttons | **ships as tested advice** (owner clarification: advice is fine when it is tested against a standard): it describes Turbo's own default, cited to turbo `form_submission.js:182-193` and `config/forms.js`; no check needed |
| H15 | 5 | P | Links and forms work without JavaScript; Turbo is an enhancement (real `href`, real `action`, server fallback) | the page is unusable when scripts fail or load late | no `href="#"` handlers; real URLs | **1 mechanical.** Check script: `href="#"` and `<a>` without `href` carrying `data-action`, in views and components; erb_lint has no such linter |
| H16 | 6 | P | A frame below the fold uses `loading="lazy"` with a `src`; an eager `src` frame fetches when it connects | every page load pays for regions nobody scrolled to | `turbo_frame_tag ..., src:, loading: :lazy` | **1 mechanical (declaration).** Every `turbo_frame_tag` with `src:` passes `loading:` explicitly, so the eager/lazy decision is visible; fixture: a `src:` frame with no `loading:` |
| H17 | 6 | A | Turbo 8 prefetches a link on hover by default; GET links with side effects fire on hover | an unsafe GET runs when someone hovers | make GETs safe; `data-turbo-prefetch="false"` on exceptions | **2 declaration, verified by script.** The layout declares the prefetch policy (`turbo-prefetch` meta set, or links opted out); the script refuses a layout with neither; whether GETs are safe is H-review below |
| H18 | 6 | P | Russian-doll fragment caching needs `touch: true` on the child's `belongs_to` | the parent fragment keeps serving stale content | `belongs_to :parent, touch: true` | **3 review verdict** (fragment cache key chain touches its parents); no sound static test of which fragments nest |
| H19 | 6 | A | A collection partial rendered in a broadcast issues one query per row unless its associations are preloaded | each broadcast costs N queries | `includes`, `strict_loading`; use `broadcast_*_later_to` | **not shipped here** (INCONCLUSIVE for broadcasts); the generic N+1 rule belongs to `rails-8` performance and needs its own enforcement (`strict_loading_by_default` check or a Bullet gate): file separately |
| H20 | 7 | A | `raw` / `html_safe` on user-controlled input is cross-site scripting; escape by default, `sanitize` when HTML is required | script runs in other users' browsers | remove `raw`; `sanitize` | **1 mechanical, upstream first.** Brakeman (`CheckCrossSiteScripting`, `CheckSanitizeMethods`, `CheckStripTags`) must be a registered gate: today `plugins/rails-flow/checks.json` has no Brakeman row, so wiring it is the enforcement; fixture: `raw(params[:x])` |
| H21 | 7 | P | Turbo form submissions carry the CSRF token; a `fetch` from a Stimulus controller must send `X-CSRF-Token` from the `csrf_meta_tags` meta | a non-GET request from a controller is rejected with 422 | read the meta tag and set the header | **1 mechanical.** Lint: a non-GET `fetch(` in a Stimulus controller must set `X-CSRF-Token`; Brakeman `CheckForgerySetting` covers the setting only |
| H22 | 7 | P | `turbo_stream_from` subscribes through a **signed** stream name; the signature is the access control, so a stream name is only embedded in pages the viewer is allowed to see, and per-user content uses a per-user stream | a shared stream broadcasts a record to every subscriber, whoever they are | per-user or per-tenant stream names (`[current_user, :notifications]`) | **1 mechanical + 2 declaration.** Check script: `turbo_stream_from` with a literal shared name or no streamable is a finding unless the stream is declared public in a verified file with a reason; plus a check that a custom channel declares `subscription_allowed?`. Fixtures: shared literal name, per-user name, declared public stream |
| H23 | 7 | A | A partial rendered by a broadcast has no `current_user` or session; it must not depend on them or contain per-viewer data | it raises, or renders one viewer's data to all subscribers | render viewer-neutral HTML; per-viewer parts through the viewer's own stream | **1 mechanical.** Check script: a partial passed to `broadcast_*`/`broadcasts_to` that mentions `current_user`, `current_*` or `session`; fixture: such a partial |
| H24 | 7 | P | With a strict CSP and importmap, scripts need a per-request nonce and the layout includes `csp_meta_tag` so Turbo's injected progress-bar `<style>` carries it | the policy blocks the progress bar or forces `unsafe-inline` | `content_security_policy_nonce_generator`, `csp_meta_tag`, nonce directives | **1 mechanical.** If a CSP nonce generator is configured, the layout must include `csp_meta_tag`; the importmap sub-claim is not enforced (unverified); fixture: generator set, tag missing |

## C. Verdicts and tool coverage

Verified by `doctrine-verifier` (read-only) on 2026-10-21 against: turbo-site handbook and reference (Turbo 8.x), hotwired/turbo **v8.0.23** source, hotwired/turbo-rails **v2.0.23**, Rails guides **v8.0.2**, stimulus.hotwired.dev (3.2.x), Brakeman and erb_lint docs. `turbo.hotwired.dev` failed TLS from the verifying machine, so the raw repository files stand in for it. I spot-checked the load-bearing one (H22) against turbo-rails v2.0.23 `app/channels/turbo/streams_channel.rb`: `subscribed` rejects only when the signed name does not verify, and the documented way to add a check is a custom channel's `subscription_allowed?`.

Tally: **18 CONFIRMED** (H1-3, H6-10, H13-18, H20, H21, H23, H24; H24 with one sub-claim unverified) · **1 REFUTED as worded, restated CONFIRMED** (H22) · **5 INCONCLUSIVE** (H4, H5, H11, H12, H19). Only CONFIRMED claims, with the wording fixes in the last column, proceed to phase 2.

| id | verdict | source (file:line at the version) | wording change required before it is skill text | Brakeman / erb_lint |
|---|---|---|---|---|
| H1 | CONFIRMED | turbo-site `handbook/04_frames.md:49,260`; turbo v8.0.23 `src/core/frames/frame_view.js:6`, `frame_controller.js:433-435` | `dom_id` is a Rails convention, not Turbo's; also fires `turbo:frame-missing` and raises `TurboFrameMissingError` | no / no [quotes: H1] |
| H2 | CONFIRMED | turbo `src/elements/stream_element.js:188-190` (`getElementById`) | true for `target=` (first match only); `targets=` (CSS selector) hits all | no / no [quotes: H2] |
| H3 | CONFIRMED | stimulus-site `00_the_origin_of_stimulus.md:65`, `05_managing_state.md:10`; turbo-site `handbook/07_building.md:45` | say "listeners and JS data are discarded by `cloneNode`", not "instance state" | no / no [quotes: H3] |
| H4 | INCONCLUSIVE (partly) | stimulus reference lifecycle-callbacks; handbook `06_working_with_external_resources.md:129-156` | docs show the timer cleanup pattern but state no "must undo" rule; restore visits create new instances, so only timers and globals (window/document listeners, third-party instances) accumulate. Rewrite narrowly and re-verify | no / no |
| H5 | INCONCLUSIVE | stimulus-site `00_the_origin_of_stimulus.md:54` (philosophy) | advice, not a verified failure; record as the maintainer's design stance | no / no |
| H6 | CONFIRMED | turbo-site `handbook/07_building.md:49,57`; `reference/attributes.md:22` | `turbo:before-cache` resets open UI; `data-turbo-temporary` is for flash and alerts | no / no [quotes: H6] |
| H7 | CONFIRMED | turbo-site `handbook/02_drive.md:244-250`; `reference/attributes.md:15` | needs a fingerprint in the asset URL; the importmap-tag case is not in the Turbo docs | no / no [quotes: H7] |
| H8 | CONFIRMED | turbo-site `handbook/02_drive.md:335-337`; turbo `form_submission.js:148-149,242-243`, `navigator.js:29`, `frame_controller.js:194` | a Drive submit needs a redirect ("Form responses must redirect to another location"); **frame submits do not**. `:unprocessable_entity` is the 8.0.x scaffold symbol; `:unprocessable_content` needs Rack 3.1+ (existing `turbo.md:27-29` already says this) | no / no [quotes: H8] |
| H9 | CONFIRMED | turbo-site `handbook/04_frames.md:130,161`; `frame_controller.js:433` | "Content missing" only when the response lacks the matching frame; `turbo-visit-control: reload` and `turbo:frame-missing` are alternatives | no / no [quotes: H9] |
| H10 | CONFIRMED | turbo-site `handbook/05_streams.md:124-128`; turbo-rails `streams_helper.rb` doc example | say "keep a `format.html` branch (usually a redirect)"; drop "failed stream request gets nothing" (inference) | no / no [quotes: H10] |
| H11 | INCONCLUSIVE | no official text on OAuth with Turbo | practitioner knowledge only; needs an official or maintainer-issue citation before it is doctrine | no / no |
| H12 | INCONCLUSIVE (partly) | stimulus-site `05_managing_state.md:10` | DOM-first is confirmed for Stimulus; "server and URL first, never a client store" is **our design stance**: record it as a maintainer decision | no / no |
| H13 | CONFIRMED | turbo-site `reference/attributes.md:37-41`; turbo `src/util.js:117-124` | frames also get `aria-busy`; form, frame and `html` are marked | no / no [quotes: H13] |
| H14 | CONFIRMED | `reference/attributes.md:27`; turbo `form_submission.js:182-193`, `config/forms.js` | `data-turbo-submits-with` only swaps the label; disabling comes from the default `config.forms.submitter` | no / no [quotes: H14] |
| H15 | CONFIRMED | turbo-site `handbook/01_introduction.md:9`; stimulus `04_designing_for_resilience.md:14` | cite the principle only | no / partly (none flags `href="#"`) [quotes: H15] |
| H16 | CONFIRMED | turbo-site `handbook/04_frames.md:116`; `reference/frames.md:25-40,109-112` | eager is the default `loading` | no / no [quotes: H16] |
| H17 | CONFIRMED | turbo-site `handbook/02_drive.md:351,357`; turbo `link_prefetch_observer.js:47,60-70,175-186` | prefetch is on `mouseenter` only, GET only; skips `data-turbo-method` non-GET, `data-turbo-confirm`, `data-turbo-stream`; opt out per link or with the meta tag | no / no [quotes: H17] |
| H18 | CONFIRMED | Rails guide `caching_with_rails.md:159-172` | none | no / no [quotes: H18] |
| H19 | INCONCLUSIVE | Rails guide `active_record_querying.md:1757` (generic `strict_loading`) | nothing in turbo-rails ties N+1 to broadcasts; reword as generic N+1 (already `performance-caching.md:173,251`). `_later` moves the render to a job (`broadcasts.rb:46-95`) but does not remove the queries | no / no |
| H20 | CONFIRMED | Rails Security guide `security.md:972,993,982-986` | the guide does not name `raw` or `html_safe` in that section | **Brakeman yes**: `CheckCrossSiteScripting`, `CheckSanitizeMethods`, `CheckStripTags`; erb_lint partly (`ErbSafety`; `Rubocop` linter with `Rails/OutputSafety` if enabled) [quotes: H20] |
| H21 | CONFIRMED | turbo-site `handbook/04_frames.md:256`; Rails guide `security.md:508-514`; rails `exception_wrapper.rb:21` | rejection is 422 via `rescue_responses` | Brakeman partly (`CheckForgerySetting`, not a missing header); erb_lint no [quotes: H21] |
| H22 | **REFUTED as worded** | turbo-rails v2.0.23 `app/channels/turbo/streams/stream_name.rb`, `streams_channel.rb` (`subscribed`), `streams_helper.rb`, `lib/turbo.rb:15` (no `expires_in`) | the premise "the signature is the access control" is wrong. **Restated, CONFIRMED by the same sources:** the signature protects the **integrity** of a stream name (a client cannot forge or alter one); it is not authorization. `Turbo::StreamsChannel#subscribed` does not check `current_user`, anyone holding a valid signed name can subscribe, and the name does not expire. Access control is (a) which pages embed the name, (b) Action Cable connection auth, (c) a custom `channel:` with `subscription_allowed?` (documented in `streams_channel.rb`). Per-user stream names stand as name hygiene only | Brakeman no; erb_lint no |
| H22r | CONFIRMED | turbo-rails v2.0.23 `app/channels/turbo/streams_channel.rb` (the `subscribed` method rejects only when the signed name does not verify) | the restated claim: the signature protects the **integrity** of a stream name (it cannot be forged or altered); it is not authorization, anyone holding a valid signed name can subscribe, and the name does not expire | Brakeman no; erb_lint no [quotes: H22r] |
| H23 | CONFIRMED | turbo-rails `broadcasts.rb:112-113` (`ApplicationController.render`), `:46-95`; `README.md:222-229` | no request, session or cookies in a broadcast render, so `current_user` is undefined or nil; pass data as locals | no / no [quotes: H23] |
| H24 | CONFIRMED | turbo `progress_bar.js:108-115`, `util.js:179-185`; Rails guide `security.md:1450,1471-1473,1492-1498` | the importmap-tag nonce behaviour is not in the guide section read: unverified, keep it out of skill text until it is | Brakeman no; erb_lint partly (`RequireScriptNonce`, not the progress-bar style) [quotes: H24] |

**Tool coverage, summarised.** Brakeman covers only H20 (XSS) and, partly, H21; erb_lint covers H20 and H24 partly and H15 not at all. **No upstream check covers H1-H19, H22 or H23**, so any enforcement for those is ours (`checks.json`), and only where a pattern can be detected mechanically; the rest is labelled advice.

**What this changes in phase 2.** (1) H22 is the largest finding: today the skills say nothing about authorizing Turbo Stream subscriptions, and the intuitive claim ("signed means protected") is wrong. (2) H4, H5, H11, H12 and H19 do not become doctrine as written: H5 and H12 are recorded as maintainer decisions, H4 is narrowed and re-verified, H11 needs a citation, H19 stays in `performance-caching.md`. (3) H8 and H14 carry wording corrections.

## D. Carried in from #2220 (coordinator ruling relayed by claude-skills-4a, 2026-10-21)

"Modal-driven CRUD" (`plugins/rails-stack/skills/design-system/SKILL.md:106` and `references/crud-modal-pattern.md`, 274 lines) is a Rails/Turbo choice, not a stack-neutral rule. The neutral architecture page will not carry it; **#2223 takes it** into the Hotwire doctrine. It has two parts, judged differently:

- **Our design choice** (CRUD opens in a shared modal, in page; the purchase flow is the full-page exception, `crud-modal-pattern.md:216`): the authority is the maintainer's recorded decision, not a citation. Phase 2 links the decision and states it as ours.
- **The Turbo mechanics it relies on** (a shared `turbo-frame` the modal loads into, a form response that closes it, `422` re-render inside the frame): external claims, candidates H25 and H26 below, to be verified like the rest.

| id | layer | kind | claim | failure it causes | fix | enforcement (owner ruling: a rule that is not enforced is not shipped) |
|---|---|---|---|---|---|---|
| H25 | 3 | P | A modal opened by a link with `data-turbo-frame="modal"` loads the response's matching `<turbo-frame id="modal">` into the shared frame without navigating the page | the whole page navigates, or "Content missing" if the response has no `modal` frame | the edit/new views render inside `turbo_frame_tag "modal"` | **1 mechanical.** Check script: `new`/`edit` templates reached from a `data-turbo-frame="modal"` link render inside `turbo_frame_tag "modal"`; plus the H1/H9 crawl judge; fixtures for both |
| H26 | 3 | P | A form inside the modal frame that fails validation re-renders with 422 inside the same frame; a success redirect with a Turbo Stream (or a `_top` visit) closes it | a success leaves the modal open, or a failure replaces the page | 422 re-render; success responds with a stream that clears the frame or a redirect with `data-turbo-frame="_top"` | **1 mechanical + e2e.** H8's 422 check for modal forms, and an e2e test case per modal form (no feature without a QA case) asserting the failure re-renders in the frame and the success closes it |

### Verdicts for H25 and H26 (`doctrine-verifier`, Turbo 8.0.23 source and handbook; turbo-rails and the Rails guides not needed for these)

| id | verdict | source | wording change required | Brakeman / erb_lint |
|---|---|---|---|---|
| H25 | CONFIRMED | turbo-site `handbook/04_frames.md` (a link or form with `data-turbo-frame` drives the named frame); turbo v8.0.23 `src/core/frames/frame_controller.js:446-450`; the literal "Content missing" is at `src/core/frames/frame_view.js:6` (checked directly: the second verifier could not find it, the first did) | "Content missing" is the frame's default text; Turbo also raises `TurboFrameMissingError` and fires a cancelable `turbo:frame-missing`, which an app can handle or turn into a visit. The frame is matched by id | no / no [quotes: H25] |
| H26 | CONFIRMED | turbo `form_submission.js:140-153`, `frame_controller.js:246-260,489` (`_top` is not frame-handled), `stream_observer.js:44-50` | (1) a 422 re-renders in the frame only if the response contains a matching `<turbo-frame id="modal">`; without one it is the frame-missing error, not a whole-page replace. (2) a successful non-GET submit must redirect or return a stream; a plain 200 HTML raises "Form responses must redirect to another location". (3) a redirect inside a frame loads into the frame and needs a matching frame, so to leave the modal use `data-turbo-frame="_top"` or respond with a stream. (4) a stream `update` of `modal` clears it; the handbook does not state this for frame-targeted forms, it is confirmed from source | no / no [quotes: H26] |

**Final tally for phase 1: 20 CONFIRMED (H1-3, H6-10, H13-18, H20, H21, H23-26), 1 REFUTED as worded and restated (H22), 5 INCONCLUSIVE (H4, H5, H11, H12, H19)**, of 26 claims. The modal-CRUD design choice itself (section D) stays a maintainer decision.


## E. Enforcement (owner ruling on #2223, 2026-10-21: "everything must be enforced, a claim or rule not enforced is useless")

The last column of the claim tables names, for each rule, one of the coordinator's three kinds: **1** mechanical check registered in `checks.json` with a negative fixture and a mutation guard; **2** required declaration verified by script; **3** recorded review verdict that a script refuses when missing. Summary, from that column:

- **Shipped with a mechanical check (1):** H1, H2, H5, H7, H8, H9, H10, H13, H15, H16, H20, H21, H22, H23, H24, H25, H26 (17). Four of them are **rendered-page** checks for the qa-flow crawl (H1, H2, H9 and the H26 e2e), the rest are static checks over views, controllers, partials, layouts and Stimulus JS.
- **Shipped with a declaration (2):** H17 (the layout declares the prefetch policy), and the public-stream declaration inside H22.
- **Shipped with a review verdict (3):** H3, H6, H12, H18. Each needs the reviewer record and the script that refuses its absence; that script is **#2225** (one home, shared with #2222 and #2220), so the four rules point there and build nothing of their own.
- **Ships as advice tested against a standard:** H14 (describes Turbo's default `config.forms.submitter`, cited to the source line).
- **Not shipped:** H4 (until narrowed and re-verified), H11 (no citation), H19 (generic N+1, belongs to `rails-8`; needs its own enforcement, to be filed).
- **Upstream first:** only H20 has an upstream tool that already catches it (Brakeman); today **no Brakeman gate is registered** in `plugins/rails-flow/checks.json`, so wiring one is the first enforcement and a gap in its own right. Everything else is ours, because Brakeman and erb_lint cover nothing else on this list (section C).
- **Cost, stated plainly:** about 14 new static or rendered checks, each needing a negative fixture and a mutation guard, plus one shared review-record script. That is the size of phase 2's check work; the skill text is the smaller half.

## F. Is H22 a live finding anywhere we run? (read-only check of Retask, 2026-10-21)

Measured with `git grep` over `origin/dev` (415ccc352) of the Retask repository, paths `app lib config spec`, patterns `turbo_stream_from`, `turbo-cable-stream-source`, `stream_from`, `broadcast`, `broadcasts_to`, `Turbo::StreamsChannel`, `ActionCable.server.broadcast`: **no match.** Retask uses Solid Cable (`config/cable.yml`, `Gemfile:43`) and has one channel file, `app/channels/application_cable/connection.rb`, which identifies the connection by the signed session cookie and refuses an expired session or an ended user (`connection.rb`, #1225). So Retask has **no Turbo Stream subscriptions today, and nothing for H22 to leak**. The connection-level authentication is the right shape for the day it adds one. Nothing is filed on Retask. The H22 check (section E) would be vacuous on Retask now; it matters for the next app that adds `turbo_stream_from`.

## G. Phase 2 plan (approved order, starts after #2205's slot)

0. **First item: a Brakeman row in rails-stack's `checks.json`**, with a negative fixture (a view with `raw(params[:x])` must fail it). Rails security gates belong in rails-stack now (coordinator ruling), so the row goes in `plugins/rails-stack/`, not rails-flow; this is the enforcement for H20 and, partly, H21.
1. **H22 security section**: the restated claim (integrity, not authorization), the `turbo_stream_from` check and its public-stream declaration, the `subscription_allowed?` check.
2. **Modal CRUD plus Frames and Streams flow**: H25, H26 with the corrected wording, H1, H8, H9, H10 and their checks.
3. **Composition and performance**: H2, H3 (review verdict, #2225), H5, H7, H13, H15, H16, H17, H18 (review verdict), H21, H23, H24.
Each step: skill text first only for CONFIRMED claims with the wording fixes of section C, the check and its negative fixture and mutation guard in the same PR, CHANGELOG naming the citation and the version boundary.

## H. Verbatim quotes for the CONFIRMED verdicts

Each phrase below was matched against the raw text of its URL (the #2233 procedure, `scripts/check_verdict_quotes.py`). A CONFIRMED verdict that quotes a page the verifier did not see cannot pass this check.

```quotes H1
https://raw.githubusercontent.com/hotwired/turbo/v8.0.23/src/core/frames/frame_view.js | turbo v8.0.23 | Content missing
```

```quotes H2
https://raw.githubusercontent.com/hotwired/turbo/v8.0.23/src/elements/stream_element.js | turbo v8.0.23 | getElementById(this.target)
```

```quotes H3
https://raw.githubusercontent.com/hotwired/stimulus-site/main/_source/handbook/00_the_origin_of_stimulus.md | stimulus-site main, read 2026-10-21 | State is stored in the HTML, so that controllers can be discarded between page changes
```

```quotes H6
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/07_building.md | turbo-site main, read 2026-10-21 | Listen for the `turbo:before-cache` event if you need to prepare the document before Turbo Drive caches it
```

```quotes H7
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/02_drive.md | turbo-site main, read 2026-10-21 | data-turbo-track="reload"
```

```quotes H8
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/02_drive.md | turbo-site main, read 2026-10-21 | HTTP 303 redirect response
```

```quotes H9
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/04_frames.md | turbo-site main, read 2026-10-21 | setting the target to `_top`
```

```quotes H10
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/05_streams.md | turbo-site main, read 2026-10-21 | text/vnd.turbo-stream.html
```

```quotes H13
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/reference/attributes.md | turbo-site main, read 2026-10-21 | `aria-busy` is added to
```

```quotes H14
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/reference/attributes.md | turbo-site main, read 2026-10-21 | specifies text to display when submitting a form
```

```quotes H15
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/01_introduction.md | turbo-site main, read 2026-10-21 | progressively enhanced web applications
```

```quotes H16
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/reference/frames.md | turbo-site main, read 2026-10-21 | Content will be replaced when the frame becomes visible
```

```quotes H17
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/02_drive.md | turbo-site main, read 2026-10-21 | <meta name="turbo-prefetch" content="false">
```

```quotes H18
https://raw.githubusercontent.com/rails/rails/v8.0.2/guides/source/caching_with_rails.md | rails v8.0.2 | belongs_to :product, touch: true
```

```quotes H20
https://raw.githubusercontent.com/rails/rails/v8.0.2/guides/source/security.md | rails v8.0.2 | escape all output
```

```quotes H21
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/04_frames.md | turbo-site main, read 2026-10-21 | X-CSRF-TOKEN
```

```quotes H22r
https://raw.githubusercontent.com/hotwired/turbo-rails/v2.0.23/app/channels/turbo/streams_channel.rb | turbo-rails v2.0.23 | If the signed stream name cannot be verified, the subscription is rejected.
```

```quotes H23
https://raw.githubusercontent.com/hotwired/turbo-rails/v2.0.23/app/channels/turbo/streams/broadcasts.rb | turbo-rails v2.0.23 | ApplicationController.render(formats: [ format ], **rendering)
```

```quotes H24
https://raw.githubusercontent.com/hotwired/turbo/v8.0.23/src/core/drive/progress_bar.js | turbo v8.0.23 | element.nonce = cspNonce
```

```quotes H25
https://raw.githubusercontent.com/hotwired/turbo-site/main/_source/handbook/04_frames.md | turbo-site main, read 2026-10-21 | it can drive another named frame by setting the target
```

```quotes H26
https://raw.githubusercontent.com/hotwired/turbo/v8.0.23/src/core/drive/form_submission.js | turbo v8.0.23 | Form responses must redirect to another location
```


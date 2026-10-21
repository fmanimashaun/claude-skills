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

| id | layer | kind | claim | failure it causes | fix |
|---|---|---|---|---|---|
| H1 | 1 | P | A Turbo Frame is an independent region identified by `id`; the response to a request made inside a frame must contain a `<turbo-frame>` with the same `id`, conventionally `dom_id(record)` | the frame shows "Content missing" and nothing updates | wrap the response body in the same `turbo_frame_tag dom_id(record)` |
| H2 | 1 | A | Duplicate DOM `id`s on one page break Turbo Stream and Frame targeting | a stream `replace`/`update` hits only the first element with that id; the others never change | give every repeated element an id from `dom_id(record)` |
| H3 | 1 | P | A Stimulus controller keeps no state that must survive navigation in instance fields; state lives in `values`, `classes` and targets, i.e. in the DOM | after a Turbo Drive restoration visit the cached DOM returns without the instance state | use the values API (`static values`) |
| H4 | 1 | A | A Stimulus controller that adds listeners, timers or third-party instances in `connect()` must undo them in `disconnect()` | handlers and instances accumulate across Turbo navigations and cached restores | symmetric `disconnect()` cleanup |
| H5 | 1 | A | Stimulus controllers do not build HTML strings to update the page; the server returns a Turbo Stream or Frame | the markup duplicates server templates and drifts | request a stream/frame |
| H6 | 2 | P | Turbo Drive keeps a snapshot cache for back/forward; ephemeral UI (open menu, toast) is removed before caching, with `data-turbo-temporary` or a `turbo:before-cache` handler | the restored page shows stale open UI | mark or reset it |
| H7 | 2 | P | Turbo Drive: `data-turbo-track="reload"` on asset tags forces a full reload when the asset fingerprint changes | a deploy leaves a stale bundle running against new HTML | `data-turbo-track: "reload"` on the stylesheet and importmap tags |
| H8 | 3 | P | A successful form submission answers with a redirect (303); a failed validation re-renders with 422 | Turbo does not render a 200 response to a form submit, so the page appears dead | `redirect_to ..., status: :see_other`; `render :new, status: :unprocessable_content` |
| H9 | 3 | A | A link or form inside a `<turbo-frame>` navigates that frame; to leave the frame use `data-turbo-frame="_top"` | a response that is a full page with no matching frame shows "Content missing" | `data-turbo-frame="_top"` on the link or form |
| H10 | 3 | P | A controller action that answers a form with a Turbo Stream also answers HTML (`format.html`) | a client without Turbo, or a failed stream request, gets nothing usable | keep a `format.html` branch |
| H11 | 3 | A | OAuth sign-in through a Turbo-handled link or form fails because the redirect leaves the origin during a fetch | the sign-in click does nothing or errors | `data-turbo="false"` on the OAuth form or link |
| H12 | 4 | P | Where state lives, in order: the server and the URL first, then the DOM (`values`, `classes`) for UI state; never a client-side store that must be synchronised | two copies of the state disagree after a stream update | derive UI from server-rendered HTML and `data-*` values |
| H13 | 5 | P | Turbo marks a busy frame with the `busy` attribute and a submitting form and `html` with `aria-busy="true"`; loading styles hang on those, with no script | a slow request gives no feedback | CSS on `turbo-frame[busy]`, `form[aria-busy="true"]` |
| H14 | 5 | P | `data-turbo-submits-with` swaps a submit button's label and disables it during the request | double submits | set it on `submit` buttons |
| H15 | 5 | P | Links and forms work without JavaScript; Turbo is an enhancement (real `href`, real `action`, server fallback) | the page is unusable when scripts fail or load late | no `href="#"` handlers; real URLs |
| H16 | 6 | P | A frame below the fold uses `loading="lazy"` with a `src`; an eager `src` frame fetches when it connects | every page load pays for regions nobody scrolled to | `turbo_frame_tag ..., src:, loading: :lazy` |
| H17 | 6 | A | Turbo 8 prefetches a link on hover by default; GET links with side effects fire on hover | an unsafe GET runs when someone hovers | make GETs safe; `data-turbo-prefetch="false"` on exceptions |
| H18 | 6 | P | Russian-doll fragment caching needs `touch: true` on the child's `belongs_to` | the parent fragment keeps serving stale content | `belongs_to :parent, touch: true` |
| H19 | 6 | A | A collection partial rendered in a broadcast issues one query per row unless its associations are preloaded | each broadcast costs N queries | `includes`, `strict_loading`; use `broadcast_*_later_to` |
| H20 | 7 | A | `raw` / `html_safe` on user-controlled input is cross-site scripting; escape by default, `sanitize` when HTML is required | script runs in other users' browsers | remove `raw`; `sanitize` |
| H21 | 7 | P | Turbo form submissions carry the CSRF token; a `fetch` from a Stimulus controller must send `X-CSRF-Token` from the `csrf_meta_tags` meta | a non-GET request from a controller is rejected with 422 | read the meta tag and set the header |
| H22 | 7 | P | `turbo_stream_from` subscribes through a **signed** stream name; the signature is the access control, so a stream name is only embedded in pages the viewer is allowed to see, and per-user content uses a per-user stream | a shared stream broadcasts a record to every subscriber, whoever they are | per-user or per-tenant stream names (`[current_user, :notifications]`) |
| H23 | 7 | A | A partial rendered by a broadcast has no `current_user` or session; it must not depend on them or contain per-viewer data | it raises, or renders one viewer's data to all subscribers | render viewer-neutral HTML; per-viewer parts through the viewer's own stream |
| H24 | 7 | P | With a strict CSP and importmap, scripts need a per-request nonce and the layout includes `csp_meta_tag` so Turbo's injected progress-bar `<style>` carries it | the policy blocks the progress bar or forces `unsafe-inline` | `content_security_policy_nonce_generator`, `csp_meta_tag`, nonce directives |

## C. Verdicts and tool coverage

Verified by `doctrine-verifier` (read-only) on 2026-10-21 against: turbo-site handbook and reference (Turbo 8.x), hotwired/turbo **v8.0.23** source, hotwired/turbo-rails **v2.0.23**, Rails guides **v8.0.2**, stimulus.hotwired.dev (3.2.x), Brakeman and erb_lint docs. `turbo.hotwired.dev` failed TLS from the verifying machine, so the raw repository files stand in for it. I spot-checked the load-bearing one (H22) against turbo-rails v2.0.23 `app/channels/turbo/streams_channel.rb`: `subscribed` rejects only when the signed name does not verify, and the documented way to add a check is a custom channel's `subscription_allowed?`.

Tally: **18 CONFIRMED** (H1-3, H6-10, H13-18, H20, H21, H23, H24; H24 with one sub-claim unverified) · **1 REFUTED as worded, restated CONFIRMED** (H22) · **5 INCONCLUSIVE** (H4, H5, H11, H12, H19). Only CONFIRMED claims, with the wording fixes in the last column, proceed to phase 2.

| id | verdict | source (file:line at the version) | wording change required before it is skill text | Brakeman / erb_lint |
|---|---|---|---|---|
| H1 | CONFIRMED | turbo-site `handbook/04_frames.md:49,260`; turbo v8.0.23 `src/core/frames/frame_view.js:6`, `frame_controller.js:433-435` | `dom_id` is a Rails convention, not Turbo's; also fires `turbo:frame-missing` and raises `TurboFrameMissingError` | no / no |
| H2 | CONFIRMED | turbo `src/elements/stream_element.js:188-190` (`getElementById`) | true for `target=` (first match only); `targets=` (CSS selector) hits all | no / no |
| H3 | CONFIRMED | stimulus-site `00_the_origin_of_stimulus.md:65`, `05_managing_state.md:10`; turbo-site `handbook/07_building.md:45` | say "listeners and JS data are discarded by `cloneNode`", not "instance state" | no / no |
| H4 | INCONCLUSIVE (partly) | stimulus reference lifecycle-callbacks; handbook `06_working_with_external_resources.md:129-156` | docs show the timer cleanup pattern but state no "must undo" rule; restore visits create new instances, so only timers and globals (window/document listeners, third-party instances) accumulate. Rewrite narrowly and re-verify | no / no |
| H5 | INCONCLUSIVE | stimulus-site `00_the_origin_of_stimulus.md:54` (philosophy) | advice, not a verified failure; record as the maintainer's design stance | no / no |
| H6 | CONFIRMED | turbo-site `handbook/07_building.md:49,57`; `reference/attributes.md:22` | `turbo:before-cache` resets open UI; `data-turbo-temporary` is for flash and alerts | no / no |
| H7 | CONFIRMED | turbo-site `handbook/02_drive.md:244-250`; `reference/attributes.md:15` | needs a fingerprint in the asset URL; the importmap-tag case is not in the Turbo docs | no / no |
| H8 | CONFIRMED (wording) | turbo-site `handbook/02_drive.md:335-337`; turbo `form_submission.js:148-149,242-243`, `navigator.js:29`, `frame_controller.js:194` | a Drive submit needs a redirect ("Form responses must redirect to another location"); **frame submits do not**. `:unprocessable_entity` is the 8.0.x scaffold symbol; `:unprocessable_content` needs Rack 3.1+ (existing `turbo.md:27-29` already says this) | no / no |
| H9 | CONFIRMED | turbo-site `handbook/04_frames.md:130,161`; `frame_controller.js:433` | "Content missing" only when the response lacks the matching frame; `turbo-visit-control: reload` and `turbo:frame-missing` are alternatives | no / no |
| H10 | CONFIRMED | turbo-site `handbook/05_streams.md:124-128`; turbo-rails `streams_helper.rb` doc example | say "keep a `format.html` branch (usually a redirect)"; drop "failed stream request gets nothing" (inference) | no / no |
| H11 | INCONCLUSIVE | no official text on OAuth with Turbo | practitioner knowledge only; needs an official or maintainer-issue citation before it is doctrine | no / no |
| H12 | INCONCLUSIVE (partly) | stimulus-site `05_managing_state.md:10` | DOM-first is confirmed for Stimulus; "server and URL first, never a client store" is **our design stance**: record it as a maintainer decision | no / no |
| H13 | CONFIRMED | turbo-site `reference/attributes.md:37-41`; turbo `src/util.js:117-124` | frames also get `aria-busy`; form, frame and `html` are marked | no / no |
| H14 | CONFIRMED (wording) | `reference/attributes.md:27`; turbo `form_submission.js:182-193`, `config/forms.js` | `data-turbo-submits-with` only swaps the label; disabling comes from the default `config.forms.submitter` | no / no |
| H15 | CONFIRMED | turbo-site `handbook/01_introduction.md:9`; stimulus `04_designing_for_resilience.md:14` | cite the principle only | no / partly (none flags `href="#"`) |
| H16 | CONFIRMED | turbo-site `handbook/04_frames.md:116`; `reference/frames.md:25-40,109-112` | eager is the default `loading` | no / no |
| H17 | CONFIRMED | turbo-site `handbook/02_drive.md:351,357`; turbo `link_prefetch_observer.js:47,60-70,175-186` | prefetch is on `mouseenter` only, GET only; skips `data-turbo-method` non-GET, `data-turbo-confirm`, `data-turbo-stream`; opt out per link or with the meta tag | no / no |
| H18 | CONFIRMED | Rails guide `caching_with_rails.md:159-172` | none | no / no |
| H19 | INCONCLUSIVE | Rails guide `active_record_querying.md:1757` (generic `strict_loading`) | nothing in turbo-rails ties N+1 to broadcasts; reword as generic N+1 (already `performance-caching.md:173,251`). `_later` moves the render to a job (`broadcasts.rb:46-95`) but does not remove the queries | no / no |
| H20 | CONFIRMED | Rails Security guide `security.md:972,993,982-986` | the guide does not name `raw` or `html_safe` in that section | **Brakeman yes**: `CheckCrossSiteScripting`, `CheckSanitizeMethods`, `CheckStripTags`; erb_lint partly (`ErbSafety`; `Rubocop` linter with `Rails/OutputSafety` if enabled) |
| H21 | CONFIRMED | turbo-site `handbook/04_frames.md:256`; Rails guide `security.md:508-514`; rails `exception_wrapper.rb:21` | rejection is 422 via `rescue_responses` | Brakeman partly (`CheckForgerySetting`, not a missing header); erb_lint no |
| H22 | **REFUTED as worded** | turbo-rails v2.0.23 `app/channels/turbo/streams/stream_name.rb`, `streams_channel.rb` (`subscribed`), `streams_helper.rb`, `lib/turbo.rb:15` (no `expires_in`) | the premise "the signature is the access control" is wrong. **Restated, CONFIRMED by the same sources:** the signature protects the **integrity** of a stream name (a client cannot forge or alter one); it is not authorization. `Turbo::StreamsChannel#subscribed` does not check `current_user`, anyone holding a valid signed name can subscribe, and the name does not expire. Access control is (a) which pages embed the name, (b) Action Cable connection auth, (c) a custom `channel:` with `subscription_allowed?` (documented in `streams_channel.rb`). Per-user stream names stand as name hygiene only | Brakeman no; erb_lint no |
| H23 | CONFIRMED | turbo-rails `broadcasts.rb:112-113` (`ApplicationController.render`), `:46-95`; `README.md:222-229` | no request, session or cookies in a broadcast render, so `current_user` is undefined or nil; pass data as locals | no / no |
| H24 | CONFIRMED (sub-claim unverified) | turbo `progress_bar.js:108-115`, `util.js:179-185`; Rails guide `security.md:1450,1471-1473,1492-1498` | the importmap-tag nonce behaviour is not in the guide section read: unverified, keep it out of skill text until it is | Brakeman no; erb_lint partly (`RequireScriptNonce`, not the progress-bar style) |

**Tool coverage, summarised.** Brakeman covers only H20 (XSS) and, partly, H21; erb_lint covers H20 and H24 partly and H15 not at all. **No upstream check covers H1-H19, H22 or H23**, so any enforcement for those is ours (`checks.json`), and only where a pattern can be detected mechanically; the rest is labelled advice.

**What this changes in phase 2.** (1) H22 is the largest finding: today the skills say nothing about authorizing Turbo Stream subscriptions, and the intuitive claim ("signed means protected") is wrong. (2) H4, H5, H11, H12 and H19 do not become doctrine as written: H5 and H12 are recorded as maintainer decisions, H4 is narrowed and re-verified, H11 needs a citation, H19 stays in `performance-caching.md`. (3) H8 and H14 carry wording corrections.

## D. Carried in from #2220 (coordinator ruling relayed by claude-skills-4a, 2026-10-21)

"Modal-driven CRUD" (`plugins/rails-stack/skills/design-system/SKILL.md:106` and `references/crud-modal-pattern.md`, 274 lines) is a Rails/Turbo choice, not a stack-neutral rule. The neutral architecture page will not carry it; **#2223 takes it** into the Hotwire doctrine. It has two parts, judged differently:

- **Our design choice** (CRUD opens in a shared modal, in page; the purchase flow is the full-page exception, `crud-modal-pattern.md:216`): the authority is the maintainer's recorded decision, not a citation. Phase 2 links the decision and states it as ours.
- **The Turbo mechanics it relies on** (a shared `turbo-frame` the modal loads into, a form response that closes it, `422` re-render inside the frame): external claims, candidates H25 and H26 below, to be verified like the rest.

| id | layer | kind | claim | failure it causes | fix |
|---|---|---|---|---|---|
| H25 | 3 | P | A modal opened by a link with `data-turbo-frame="modal"` loads the response's matching `<turbo-frame id="modal">` into the shared frame without navigating the page | the whole page navigates, or "Content missing" if the response has no `modal` frame | the edit/new views render inside `turbo_frame_tag "modal"` |
| H26 | 3 | P | A form inside the modal frame that fails validation re-renders with 422 inside the same frame; a success redirect with a Turbo Stream (or a `_top` visit) closes it | a success leaves the modal open, or a failure replaces the page | 422 re-render; success responds with a stream that clears the frame or a redirect with `data-turbo-frame="_top"` |

### Verdicts for H25 and H26 (`doctrine-verifier`, Turbo 8.0.23 source and handbook; turbo-rails and the Rails guides not needed for these)

| id | verdict | source | wording change required | Brakeman / erb_lint |
|---|---|---|---|---|
| H25 | CONFIRMED | turbo-site `handbook/04_frames.md` (a link or form with `data-turbo-frame` drives the named frame); turbo v8.0.23 `src/core/frames/frame_controller.js:446-450`; the literal "Content missing" is at `src/core/frames/frame_view.js:6` (checked directly: the second verifier could not find it, the first did) | "Content missing" is the frame's default text; Turbo also raises `TurboFrameMissingError` and fires a cancelable `turbo:frame-missing`, which an app can handle or turn into a visit. The frame is matched by id | no / no |
| H26 | CONFIRMED with corrections | turbo `form_submission.js:140-153`, `frame_controller.js:246-260,489` (`_top` is not frame-handled), `stream_observer.js:44-50` | (1) a 422 re-renders in the frame only if the response contains a matching `<turbo-frame id="modal">`; without one it is the frame-missing error, not a whole-page replace. (2) a successful non-GET submit must redirect or return a stream; a plain 200 HTML raises "Form responses must redirect to another location". (3) a redirect inside a frame loads into the frame and needs a matching frame, so to leave the modal use `data-turbo-frame="_top"` or respond with a stream. (4) a stream `update` of `modal` clears it; the handbook does not state this for frame-targeted forms, it is confirmed from source | no / no |

**Final tally for phase 1: 20 CONFIRMED (H1-3, H6-10, H13-18, H20, H21, H23-26), 1 REFUTED as worded and restated (H22), 5 INCONCLUSIVE (H4, H5, H11, H12, H19)**, of 26 claims. The modal-CRUD design choice itself (section D) stays a maintainer decision.

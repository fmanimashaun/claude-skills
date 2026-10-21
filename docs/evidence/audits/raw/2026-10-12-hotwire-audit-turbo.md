# Hotwire Turbo audit — plugins/rails-stack/skills/hotwire/references/turbo.md + SKILL.md (2026-10-12, doctrine-verifier)

Versions verified: @hotwired/turbo 8.0.23 (npm latest, published 2026-01-29; dist/turbo.es2017-esm.js, "T:" = line in that file),
plus 8.0.0 / 8.0.13 / 8.0.14 tarballs for boundaries; turbo-rails 2.0.23 gem source ("R:"); GitHub release notes hotwired/turbo.
Read-only audit; nothing edited.

| # | Claim (file:line) | Verdict | Source + quote | Version boundary |
|---|---|---|---|---|
| 1 | SKILL.md:44 Turbo 8.0.23 current | CONFIRMED | `npm view @hotwired/turbo versions` ends "8.0.23", 2026-01-29 | 8.0.23 latest |
| 2 | turbo.md:46 prefetch on hover ON by default; meta false disables whole page, nearest `[data-turbo-prefetch]` incl. link decides (50-55) | CONFIRMED | T:4670 `if (getMetaContent("turbo-prefetch") === "false") return`; T:4774-4778 link attr then `findClosestRecursively(link,"[data-turbo-prefetch]")` | 8.0 |
| 3 | turbo.md:56-59 svg `<a>` throws, issue #1510, fixed on main, unreleased in 8.0.23 | CONFIRMED | T:460 `if (link.href.startsWith("#"))`; gh issue 1510 CLOSED/COMPLETED 2026-06-27, after 8.0.23 | unfixed in 8.0.23 |
| 4 | turbo.md:61-67 `Turbo.config.forms.submitter` "disabled" default / "aria-disabled" | CONFIRMED | T:516 `submitter: "disabled"`; T:480-487 `"aria-disabled": { ... setAttribute("aria-disabled","true")` | 8.0.x config API |
| 5 | turbo.md:68-69 progress bar 500ms, `Turbo.config.drive.progressBarDelay` | CONFIRMED | T:201 `progressBarDelay: 500`; T:6268 deprecation pointing to `Turbo.config.drive.progressBarDelay` | |
| 6 | turbo.md:75-76/114 Drive permanence needs id | CONFIRMED | T:1407 `querySelectorAll("[id][data-turbo-permanent]")` | |
| 7 | turbo.md:115-122 morph skip = bare hasAttribute; beforeNodeAdded expression | CONFIRMED | T:3451 `!currentElement.hasAttribute("data-turbo-permanent")`; T:3446 exact quoted expression (file line cited as morphing.js:62 is src, not checked) | 8.0.23 |
| 8 | turbo.md:80-85 `data-turbo-track="dynamic"` removes only stylesheets (style / link rel=stylesheet) | CONFIRMED | T:5470 `=== "dynamic"` over `oldHeadStylesheetElements`; T:3732-3734 `tagName == "style" \|\| (link && rel == "stylesheet")` | |
| 9 | turbo.md:86-91 `turbo-view-transition` meta from 8.0.14, old `view-transition same-origin` still accepted, reduced-motion skip since 8.0.14 | CONFIRMED | T:3826-3827 `getSetting("view-transition") === "true" \|\| getMetaValue("view-transition") === "same-origin"` + `matchMedia("(prefers-reduced-motion: reduce)")`; 8.0.13 tarball has 0 matches, 8.0.14 has them; PR #1380/#1409 | 8.0.14 (release notes list them under v8.0.18 too) |
| 10 | turbo.md:92-96 `data-turbo-visit-direction` 8.0.0+, not set for stream-accepting visits | CONFIRMED | T:1573; T:5958 `if (!visit.acceptsStreamResponse) { ... markVisitDirection`; 8.0.0 tarball contains it | 8.0.0 |
| 11 | turbo.md:104-105 refresh-method default replace, scroll default reset | CONFIRMED | R: drive_helper.rb:70 `def turbo_refreshes_with(method: :replace, scroll: :reset)`; T:5552/5596 morph/preserve only on explicit value | |
| 12 | turbo.md:148-152 request-id echo, own-tab skip, last 20 | CONFIRMED | T:660 `new LimitedSet(20)`; T:5790 `isRecentRequest = requestId && this.recentRequests.has(requestId)`; R: broadcasts.rb:70 `request_id: Turbo.current_request_id` | |
| 13 | turbo.md:184-188 `_parent` ≥8.0.21, `parentElement.closest("turbo-frame")`, falls back to page visit | CONFIRMED | T:6898-6899; T:6808 `else if (id == "_parent") return false`; v8.0.21 notes "Add support for data-turbo-frame=\"_parent\"" (#1446) | 8.0.21 |
| 14 | turbo.md:193-194 frame requests get minimal layout automatically | CONFIRMED | R: frame_request.rb:24 `layout -> { "turbo_rails/frame" if turbo_frame_request? }` | |
| 15 | turbo.md:217/227-232 `method="morph"` only on replace/update (morphElements/morphChildren), ≥8.0.5; append etc. take no `method:` | CONFIRMED | T:6950-6970; R: tag_builder.rb:81/161 `method: nil` on replace/update only, append:189 none; v8.0.5 notes "Add Turbo stream morph action" (#1185) | 8.0.5 |
| 16 | turbo.md:216/245-261 before/after de-dup via siblings (incl. target) ≥8.0.21; append/prepend direct children | CONFIRMED | T:7045-7075 `[...e.children]` vs `[...e.parentElement.children]`; v8.0.21 "Remove duplicate siblings when using before/after actions" (#1290) | 8.0.21 |
| 17 | turbo.md:236-242 refresh stream `method`/`scroll` ≥8.0.21 win over meta (text says "not independently traced") | CONFIRMED | T:6976-6981 reads attrs; T:5552 `(visit?.refresh?.method \|\| this.snapshot.refreshMethod) === "morph"`; v8.0.21 notes (#1208). Hedge in line 240 can be removed | 8.0.21 |
| 18 | turbo.md:308 `broadcasts_to` append on create, replace on update, remove on destroy | CONFIRMED | R: broadcastable.rb:183-187 | |
| 19 | turbo.md:327 `remove` needs no `_later` | CONFIRMED | R: broadcastable.rb:186 destroy uses `broadcast_remove_to` (sync) | |
| 20 | turbo.md:379-381 `turbo:before-frame-morph` not cancelable | CONFIRMED | T:3491 dispatch without `cancelable`; T:242 `cancelable` undefined → false | |
| 21 | turbo.md:395/403-405 Content missing text; fetch-request-error cancelable detail {request,error}; frame-missing {response,visit} cancelable; submit-end fetchResponse xor error | CONFIRMED | T:1591; T:869-873; T:6730-6733; T:1212-1239 result shapes | |
| 22 | turbo.md:392-393 `requestFinished` restores text, clears busy | CONFIRMED | T:1243-1247 (`resetSubmitterText(); clearBusyState`) — "in a finally" not checked | |
| 23 | turbo.md:472 `turbo_frame_tag(record_or_id, src:, loading:, target:)` | CONFIRMED (approx.) | R: frames_helper.rb:41 `def turbo_frame_tag(*ids, src: nil, target: nil, **attributes, &block)` — `loading:` passes via **attributes | |
| 24 | turbo.md:474-475 `_all` variants | CONFIRMED | R: tag_builder.rb:121 `before_all`, :203 `append_all` | |
| 25 | turbo.md:479 request predicate `turbo_stream_request?` | REFUTED | `grep -rn stream_request` over turbo-rails 2.0.23: no match. Only `turbo_frame_request?` (frame_request.rb:27). Use `request.format.turbo_stream?` | turbo-rails 2.0.23 |
| 26 | turbo.md:480 `assert_turbo_stream`, `assert_turbo_stream_broadcasts` | CONFIRMED | R: lib/turbo/test_assertions.rb:48; lib/turbo/broadcastable/test_helper.rb:58 | |

Counts: CONFIRMED 25, REFUTED 1, INCONCLUSIVE 0.
Not audited: Rack/Rails status-symbol matrix (SKILL.md:57-61; a Rails/Rack claim, not Turbo), Solid Queue ordering (turbo.md:328-332), production.md cross-references.

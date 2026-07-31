# Turbo (v8) — Drive, Page Refreshes, Frames, Streams

## Contents
1. Turbo Drive — navigation and forms
2. Drive attributes and caching
3. Morphing page refreshes (Turbo 8)
4. Turbo Frames
5. Turbo Streams — the actions
6. Delivering streams: form responses and broadcasts
7. Custom stream actions
8. Events reference
9. turbo-rails helper cheat sheet

---

## 1. Turbo Drive — navigation and forms

Active by default once Turbo is installed: same-origin link clicks and form
submissions become `fetch` requests; Turbo swaps `<body>` (merging `<head>`)
and updates history. You write nothing.

What the server must do:

- **Successful form submission → redirect** (`303 See Other` for
  PATCH/PUT/DELETE so the follow-up is a GET).
- **Failed validation → re-render the form with `422 Unprocessable Entity`.**
- **Server errors → `500`** (Turbo shows the response). A `200` containing a
  form response without redirect is the classic "my form does nothing" bug.

Programmatic navigation: `Turbo.visit(location)`,
`Turbo.visit(location, { action: "replace" })` (no new history entry),
`Turbo.visit(location, { frame: "modal" })` (drive a frame). Two visit types
exist: *application visits* (clicks/`Turbo.visit`, actions `advance`/
`replace`) and *restoration visits* (back/forward, action `restore`,
instant from cache).

## 2. Drive attributes and caching

```html
<a href="/edit" data-turbo-method="delete" data-turbo-confirm="Sure?">Delete</a>
<a href="/big-report" data-turbo="false">Full reload</a>          <!-- opt out (self + descendants) -->
<a href="/settings" data-turbo-action="replace">No history entry</a>
<a href="/slow" data-turbo-prefetch="false">Don't prefetch</a>    <!-- prefetch-on-hover is ON by default -->
<form data-turbo-disable-submitter>…</form>                        <!-- button disabled during submit (default) -->
```

- Progress bar appears for visits >500ms
  (`Turbo.config.drive.progressBarDelay` to tune; style `.turbo-progress-bar`).
- **Cache & previews**: Turbo snapshots pages before leaving and shows the
  snapshot as an instant *preview* on revisit while fetching fresh content.
  Control per page via
  `<meta name="turbo-cache-control" content="no-preview | no-cache">`.
  Clean up before snapshotting in a `turbo:before-cache` listener (close
  dropdowns, reset forms). `<html>` elements marked `data-turbo-permanent`
  (with an `id`) persist across visits — players, chat widgets.
- **Assets**: mark bundles
  `<link rel="stylesheet" href="..." data-turbo-track="reload">` — when the
  fingerprint changes mid-session, Turbo does a full reload so users get new
  code. `data-turbo-track="dynamic"` instead updates the element in place
  without a reload (good for non-critical CSS).
- **View transitions**: add
  `<meta name="view-transition" content="same-origin">` and Turbo uses the
  browser View Transitions API for animated page changes where supported.

## 3. Morphing page refreshes (Turbo 8)

A *refresh* is a visit to the same URL. Two knobs, set as meta tags (or via
the Rails helper below):

```html
<meta name="turbo-refresh-method" content="morph">     <!-- or "replace" (default) -->
<meta name="turbo-refresh-scroll" content="preserve">  <!-- or "reset" (default) -->
```

With `morph`, Turbo diffs the new HTML into the live DOM instead of swapping
`<body>` — scroll position, focus, and unchanged subtrees survive. Shield
client-side-mutated regions from morphing with `data-turbo-permanent`.

**The `id` requirement differs between the two things `data-turbo-permanent`
does, and the difference is useful.** Drive's cross-visit persistence selects
`[id][data-turbo-permanent]`, so **an `id` is mandatory** there. Morphing's
skip is a bare `hasAttribute("data-turbo-permanent")` check with **no `id`
involved** — which is what makes it safe to *add the attribute at runtime*
to shield a region only while it needs shielding (an edit in progress), and
remove it after. Worked example in `references/production.md` §2.4.

The payoff is **broadcasted refreshes**: instead of authoring per-change
streams, the server broadcasts a tiny "reload yourself" signal and every
subscribed page re-fetches + morphs:

```ruby
# Rails: model
class Calendar < ApplicationRecord
  broadcasts_refreshes   # after commits, sends a refresh stream signal
end
```

```erb
<%# view %>
<%= turbo_stream_from @calendar %>
<% turbo_refreshes_with method: :morph, scroll: :preserve %>
```

Frames marked `<turbo-frame id="..." refresh="morph">` reload themselves as
part of a morph — use for frame content that a plain morph can't reconcile.
Choose broadcasted refreshes over hand-written stream actions whenever "just
re-render the page" is acceptable — it deletes code.

**The tab that caused the change does not refresh itself.** Turbo stamps each
of its fetches with an `X-Turbo-Request-Id`, the server echoes it onto the
broadcast as `request-id`, and a tab skips a refresh carrying an id it
recognises as its own. The recognition set holds only the **last 20**
requests per page load, so a chatty tab can refresh itself anyway — harmless
under morphing, which is one more reason `method: :morph` is the right
default here. Mechanism and its other two conditions:
`references/production.md` §2.2.

## 4. Turbo Frames

A frame scopes navigation: links and form submissions **inside** a
`<turbo-frame>` replace only that frame, extracted from the response by
matching `id`.

```html
<turbo-frame id="message_1">
  <h2>Subject</h2>
  <a href="/messages/1/edit">Edit</a>   <!-- response's frame #message_1 replaces this one -->
</turbo-frame>
```

Key mechanics:

- **Matching ids on both ends** — the navigated-to page must contain
  `<turbo-frame id="message_1">`; otherwise the frame errors ("content
  missing"). In Rails, `turbo_frame_tag @message` generates `dom_id` on both
  pages automatically.
- **Lazy loading** — `<turbo-frame id="notes" src="/notes" loading="lazy">`
  fetches when scrolled into view (`loading="eager"` = on page load). Put a
  spinner inside as placeholder content.
- **Targeting other frames** — `target="frame_id"` on the frame, or
  `data-turbo-frame="frame_id"` on a specific link/form (a search form
  outside a results frame targets it this way).
- **Breaking out** — `target="_top"` (or `data-turbo-frame="_top"` per link)
  promotes navigation to a full page visit. Anchors with
  `data-turbo-frame="_self"` stay put.
- **Promoting to history** — frames don't touch the URL by default; add
  `data-turbo-action="advance"` to the frame to make its navigations push
  history (tabbed interfaces with shareable URLs).
- Frame responses render the full layout server-side unless optimized;
  detect frame requests to skip layout (Rails: `turbo_frame_request?`,
  automatic layout minimization for frame requests).
- The frame element exposes `element.src` and `element.reload()` from JS.

Gotcha list: a link inside a frame that should do a full-page nav (show
pages!) needs `_top`; forms inside frames still need 303/422 statuses;
redirect responses navigate the *frame* unless broken out.

## 5. Turbo Streams — the actions

A stream is HTML that mutates named elements:

```html
<turbo-stream action="append" target="messages">
  <template>
    <div id="message_5">New message</div>
  </template>
</turbo-stream>
```

| Action | Effect on `target` element |
|---|---|
| `append` / `prepend` | Insert template inside, at end / start — **id-de-duplicated**, see below |
| `before` / `after` | Insert template as sibling |
| `replace` | Replace the whole element — accepts `method="morph"` |
| `update` | Replace only the element's inner content — accepts `method="morph"` |
| `remove` | Delete the element (no template needed) |
| `refresh` | Trigger a page refresh (morphing — §3) |

`target="id"` addresses one element; `targets=".css-selector"` (plural)
addresses many. Streams intentionally have **no client logic** beyond these
mutations — if you need behavior, attach a Stimulus controller to the
arriving HTML.

**`method="morph"` (Turbo ≥ 8.0.5) morphs one stream action** instead of
swapping outright: `replace` calls `morphElements` on the target, `update`
calls `morphChildren`. In Rails:
`turbo_stream.replace(dom_id(x), partial: "…", method: :morph, locals: {…})`.
**Only `replace` and `update` honour it** — `append`, `prepend`, `before` and
`after` do not accept `method:` at all. Reach for it when a stream must land
on a region the user is interacting with (open `<details>`, scroll position,
focus) and a wholesale swap would reset it.

**How `append`/`prepend` de-duplicate — the precision matters.** Turbo calls
`removeDuplicateTargetChildren()` first: it collects the **direct children**
of the target that carry an `id` matching an `id` on any top-level element of
the incoming `<template>`, and **removes** them. Then it appends (or
prepends) the new content. So:

- The guarantee is **id uniqueness, not position.** The new element lands at
  the container's end (`append`) or start (`prepend`) — *not* where the old
  one sat. Do not read "replaced" as "replaced in place"; for that you want
  `replace` with `method="morph"`.
- The scope is **direct children of the target only** — not a document-wide
  or descendant search.
- It matches **every** top-level template child with an `id`, not just the
  first.

This is the mechanism that makes optimistic UI safe: render the pending
element client-side with the same `id` the server will emit, and the arriving
broadcast collapses the two instead of doubling them. Worked example in
`references/production.md` §1.2.

## 6. Delivering streams: form responses and broadcasts

**Form responses** — when a form submits with Turbo, the request advertises
`Accept: text/vnd.turbo-stream.html`; respond with one or more streams
instead of redirecting *only when* multiple regions must change:

```ruby
# Rails controller
def create
  @message = @room.messages.create!(message_params)
  respond_to do |format|
    format.turbo_stream    # renders create.turbo_stream.erb
    format.html { redirect_to @room, status: :see_other }  # non-Turbo fallback
  end
end
```

```erb
<%# create.turbo_stream.erb %>
<%= turbo_stream.append "messages", @message %>
<%= turbo_stream.update "message_count", @room.messages.size %>
<%= turbo_stream.replace "new_message" do %><%= render "form", room: @room %><% end %>
```

**Broadcasts** (WebSocket/SSE) — subscribe the page, then send streams from
models or jobs:

```erb
<%= turbo_stream_from @room %>   <%# signed channel subscription %>
```

```ruby
class Message < ApplicationRecord
  belongs_to :room
  broadcasts_to :room   # append on create, replace on update, remove on destroy
  # granular alternative inside jobs/callbacks:
  # broadcast_append_later_to room, target: "messages"
end
```

Broadcast rules: broadcasts render partials with **no controller context**
(no `current_user` — design partials to take everything as locals); broadcast
after commit only; never trust user-supplied stream names —
`turbo_stream_from` signs them for you. First consider §3 refreshes;
hand-authored broadcasts are for high-frequency or surgical updates where
re-rendering the page is too heavy.

**`_later` by default, with two exceptions — the flat "always prefer
`_later`" rule was wrong.** turbo-rails recommends `_later` for anything that
renders, because rendering inline slows the request (and, from an
`after_create` rather than `after_create_commit`, renders with the
transaction still open). But:

- **`remove` needs no `_later`** — it renders nothing, only a `dom_id`.
- **`_later` gives up ordering.** Nothing in ActiveJob, Solid Queue or
  turbo-rails guarantees that two `_later` broadcasts to the same stream
  arrive in enqueue order — no priority, no concurrency key, and Solid
  Queue's own docs disclaim it. With the default multi-threaded worker they
  routinely won't. **When order is observable — a transcript, a feed, an
  append-only log — broadcast synchronously.** See
  `references/production.md` §1.1.

## 7. Custom stream actions

Extend the vocabulary in JS:

```javascript
import { StreamActions } from "@hotwired/turbo"

StreamActions.log = function () {
  console.log(this.getAttribute("message"))
}
// <turbo-stream action="log" message="Hello"></turbo-stream>
```

Inside the function, `this` is the `<turbo-stream>` element (`this.target`,
`this.templateContent` available). Use for cross-cutting behaviors like
toasts or dispatching events; keep them as dumb as the built-ins.

## 8. Events reference

All bubble to `document`; the most-used, in lifecycle order:

- `turbo:click`, `turbo:before-visit` (cancelable — block navigation),
  `turbo:visit`
- `turbo:submit-start` / `turbo:submit-end` (form lifecycle — disable/enable
  UI), `turbo:before-fetch-request` (mutate headers — auth tokens),
  `turbo:before-fetch-response`
- `turbo:before-cache` (clean the page before snapshot),
  `turbo:before-render` (cancelable/resumable — custom transitions),
  `turbo:render`, `turbo:load` (fires on first load + every visit — the
  "DOMContentLoaded of Turbo", though Stimulus usually removes the need)
- Morphing hooks, and **the page-level and per-element ones are different
  events** — don't pair them by name:
  `turbo:morph` fires **once per morphed page refresh**
  (`detail: { currentElement, newElement }`); `turbo:before-morph-element`
  (cancelable) / `turbo:morph-element` fire **per element**, including for a
  `method="morph"` stream action; `turbo:before-morph-attribute` (cancelable,
  `detail: { attributeName, mutationType }`) fires per attribute — cancel it
  to keep morph from touching one attribute (§3)
- `turbo:before-frame-render` / `turbo:frame-load` /
  `turbo:frame-missing` (handle mismatched frames gracefully),
  `turbo:before-stream-render` (wrap/intercept stream application — its
  `detail.render` is **writable**, see `references/production.md` §1.5)
- `turbo:fetch-request-error`, `turbo:reload`

Idiom: prefer Stimulus `connect()` on the elements themselves over global
`turbo:load` listeners — it survives frames, streams, and morphs for free.

## 9. turbo-rails helper cheat sheet

`turbo_frame_tag(record_or_id, src:, loading:, target:)` ·
`turbo_stream_from(*streamables)` · `turbo_stream.append/prepend/replace/
update/remove/before/after(target, content = nil, &block)` (also
`_all` variants for `targets=`) · model macros `broadcasts_to`,
`broadcasts`, `broadcasts_refreshes` (+ `broadcast_*_later_to` instance
methods) · `turbo_refreshes_with(method:, scroll:)` ·
`provide meta tags via yield` · request predicates `turbo_frame_request?`,
`turbo_stream_request?` · test matchers via `assert_turbo_stream` /
`assert_turbo_stream_broadcasts`. Everything renders through normal
partials — there is no special template language to learn.

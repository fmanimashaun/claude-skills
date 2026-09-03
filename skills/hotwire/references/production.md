# Hotwire in production — two 37signals apps under real load

The rest of this skill is the official handbooks: what the APIs *are*. This file is what two
shipped apps by the people who make Hotwire actually *do* with them — which rungs of the
escalation ladder they pick, and the half-dozen production problems the handbooks never mention.

**Sources and attribution.** Everything here is read from two 37signals apps:

| App | What it is | Licence | Why it is the interesting case |
|---|---|---|---|
| [basecamp/once-campfire][cf] | group chat | **MIT** | the hardest Turbo Streams case — many small updates per second, ordering matters, and the socket *will* drop |
| [basecamp/fizzy][fz] | Kanban board | **O'Saasy** (MIT + no-competing-SaaS) | the hardest Stimulus case — drag-and-drop, dialogs, hotkeys, 69 controllers |

Both licences permit quoting and adapting; **attribute 37signals** wherever a pattern is lifted,
as this file does. Nothing here is clean-room — the citations are the point.

[cf]: https://github.com/basecamp/once-campfire
[fz]: https://github.com/basecamp/fizzy

**How to read the labels.** Three kinds of statement, never mixed:

- **Framework fact** — verified against Turbo 8.0.23 / Stimulus 3.2.2 / turbo-rails 2.0.23 /
  Rails 8 source or official docs. Version boundaries are stated where they bite.
- **What they do** — an observation about the cited file. Verifiable by opening it.
- **OURS** — our prescription drawn from the observation. An app doing something is not by
  itself a reason to do it; the reason is given.

---

## 0. The two apps disagree about real-time, and the disagreement *is* the doctrine

This is the most useful single finding, and it would be invisible from either app alone:

| | Campfire (chat) | Fizzy (Kanban) |
|---|---|---|
| Application Action Cable channels | **6** | **0** |
| How the server pushes DOM changes | hand-written `broadcast_append_to` / `broadcast_replace_to` | `broadcasts_refreshes` only |
| How the server pushes non-DOM signals | raw `ActionCable.server.broadcast` JSON | none |
| Stimulus controllers | 35 | 69 (61 + 8 under `bridge/`) |

Counts are from the repository trees; re-check with
`gh api "repos/basecamp/fizzy/git/trees/main?recursive=1" --jq '.tree[].path' | grep -cE '^app/javascript/controllers/.*_controller\.js$'`
and the equivalent for `app/channels/` (excluding `application_cable/`).

Fizzy is the **bigger** app and has **no channels at all**. So the choice is not driven by app
size or sophistication — it is driven by **update rate and payload granularity**:

- A Kanban card changes a few times an hour per viewer. Re-render the page and morph: one line
  in the model, no channel, no partial to keep in sync. Fizzy's entire real-time story is
  `broadcasts_refreshes` ([`app/models/card/broadcastable.rb`][fz-card-bc],
  [`app/models/board/broadcastable.rb`][fz-board-bc]).
- A chat room changes several times a second, and the changed thing is one message at the end of
  a list that may hold thousands. Re-rendering the page per message is absurd, so Campfire writes
  the stream by hand.

**OURS — the rule this yields.** Start at `broadcasts_refreshes`. Escalate to a hand-written
broadcast only when you can name which of these is true:

1. the update rate makes a full re-render wasteful (chat, tickers, presence);
2. the page is too expensive to re-render (a long paginated list, a heavy dashboard);
3. the client must keep state a re-render would destroy (scroll position in an infinite list,
   an in-flight optimistic element).

If none of the three applies, a hand-written broadcast is code you are choosing to maintain.
`turbo.md` §3 already said to prefer refreshes; this is the escalation test it lacked.

[fz-card-bc]: https://github.com/basecamp/fizzy/blob/main/app/models/card/broadcastable.rb
[fz-board-bc]: https://github.com/basecamp/fizzy/blob/main/app/models/board/broadcastable.rb

---

## 1. Turbo Streams at chat scale (Campfire)

### 1.1 They broadcast from the controller, not from a model callback

`turbo.md` §6 shows `broadcasts_to :room` — the macro that hangs broadcasts off commit callbacks.
Campfire does **not** use it. Its `Message::Broadcasts` concern is two plain methods, called
explicitly from the controller ([`app/models/message/broadcasts.rb`][cf-bc],
[`app/controllers/messages_controller.rb`][cf-mc]):

```ruby
module Message::Broadcasts
  def broadcast_create
    broadcast_append_to room, :messages, target: [ room, :messages ]
    ActionCable.server.broadcast("unread_rooms", { roomId: room.id })
  end

  def broadcast_remove
    broadcast_remove_to room, :messages
  end
end
```

```ruby
def create
  set_room
  @message = @room.messages.create_with_attachment!(message_params)

  @message.broadcast_create        # explicit, synchronous, in the request
  deliver_webhooks_to_bots
end
```

Note what is *still* on a callback: `after_create_commit -> { room.receive(self) }`
([`app/models/message.rb`][cf-msg]) fans out unread flags and queues push notifications. So the
split is deliberate rather than an aversion to callbacks — **the stream is controller-driven,
the side effects are callback-and-job driven.**

**Note the second deliberate choice: `broadcast_append_to`, not `broadcast_append_later_to`.** Our
`turbo.md` §6 said flatly "prefer the `_later` (job-backed) variants", which is what turbo-rails'
own `Turbo::Broadcastable` docs recommend — *"you should use the `_later` versions of everything
except for remove when broadcasting within a real-time path, like a controller or model, since all
those updates require a rendering step, which can slow down execution."* Campfire ignores it here,
and the reason is decisive:

**Framework fact — verified, and it is the missing half of our rule: nothing in ActiveJob, Solid
Queue, or turbo-rails guarantees the delivery order of two `_later` broadcasts to the same
stream.** turbo-rails' broadcast jobs set no priority and no concurrency controls; Solid Queue's
own README says of its concurrency primitive *"there's no guarantee about the order of execution"*
and that retried jobs re-enter with no positional privilege. With `threads: 3` — the default — two
messages enqueued a millisecond apart can render and broadcast in either order. In a chat
transcript that is a visible, user-reported bug.

**OURS — the sharpened rule.** Prefer `_later`, with two exceptions, both now stated because a
flat preference was wrong:

- **`remove` never needs `_later`** — it renders nothing, only a `dom_id`. turbo-rails says so.
- **When the order of two broadcasts to the same stream is observable, broadcast
  synchronously.** Ordered feeds, transcripts, append-only logs. The cost is the render time
  inside the request; the benefit is the only ordering guarantee available. If the render is too
  expensive to hold the request open, the answer is a cheaper partial or a
  `broadcasts_refreshes`-style re-render, **not** `_later` — `_later` does not make it ordered, it
  makes it unordered *and* asynchronous.

One further caution from the same source, worth carrying: turbo-rails warns that synchronous
rendering *"is usually not desireable for model callbacks, **certainly not if those callbacks are
inside of a transaction**"* — a synchronous broadcast from an `after_create` (not
`after_create_commit`) renders with the transaction still open. Campfire's controller call sites
are outside any transaction, which is part of why the pattern is safe there.

### 1.2 The optimistic-UI de-duplication trick, and it is one line of Ruby

This is the sharpest thing in either codebase. `Message` overrides `to_key`
([`app/models/message.rb`][cf-msg]):

```ruby
before_create -> { self.client_message_id ||= Random.uuid } # Bots don't care

def to_key
  [ client_message_id ]
end
```

**Framework fact:** `ActionView::RecordIdentifier#dom_id` builds its id from `record.to_key` via
the private `record_key_for_dom_id`. Overriding `to_key` therefore changes every id that
`dom_id`, `turbo_frame_tag` and the `turbo_stream.*` helpers generate for that model.

So the server's rendered message gets `id="message_<client_message_id>"` — and the client, which
minted that id before submitting, renders its pending message into the same id
([`app/views/messages/_template.html.erb`][cf-tpl]):

```erb
<script type="text/template" data-messages-target="template">
  <div class="message message--me $messageClasses$"
      id="message_$clientMessageId$"
      …>
```

When the broadcast lands, `turbo_stream.append` finds a direct child of the container already
carrying that id, removes it, and appends the server-rendered one. **No duplicate, no client-side
reconciliation, no diffing library.** The de-duplication is Turbo's, documented in `turbo.md` §5 —
including the caveat that it is an *id* guarantee, not a *position* guarantee, which is why
Campfire re-sorts the tail by `data-sort-value` afterwards
(`#positionLastMessage` in [`messages_controller.js`][cf-msgs-js]).

**OURS.** This is the pattern to reach for whenever a form submit must feel instant: mint the id
on the client, render the pending element with it, let the append collapse the pair. The cost is
one `to_key` override and a `client_message_id` column with a unique index. Do **not** hand-roll a
reconciliation pass; the id contract already does it.

Three details worth copying with it:

- **When the request can't go through Turbo, apply the stream by hand.** File uploads use an
  `XMLHttpRequest` (Turbo's fetch gives no progress events), so the response has to be applied
  explicitly ([`composer_controller.js`][cf-comp]):

  ```javascript
  const resp = await uploader.upload()
  Turbo.renderStreamMessage(resp)
  ```

  **Framework fact:** `Turbo.renderStreamMessage(html)` is a documented public API for exactly
  this — *"If you need to process stream actions from different source than something producing
  MessageEvents"*. The same id-de-duplication then collapses the upload's pending placeholder.

- **The pending element is rendered from a `<script type="text/template">` in the page**, not from
  a string built in JS. The server still owns the markup — it interpolates `$placeholder$` tokens
  ([`app/javascript/models/client_message.js`][cf-cm]). This keeps `stimulus.md` §10's "don't
  render HTML strings in controllers" true even for optimistic UI.
- **Failure is a CSS class, not a rollback.** `submitEnd` checks `event.detail.success` and adds
  `message--failed` to the pending element ([`composer_controller.js`][cf-comp]); the element
  stays on screen. A user who loses connectivity keeps their text.

### 1.3 What they push vs what they re-render

Consistent, and worth stating as a rule: **Campfire pushes the smallest element that is
self-contained, and never smaller.**

- new message → `append` the whole message partial to the room's message list;
- edited message → `broadcast_replace_to … target: [ @message, :presentation ], partial:
  "messages/presentation"` — the *presentation* fragment, not the whole message, so the
  surrounding boosts and action menu are untouched ([`messages_controller.rb`][cf-mc]);
- deleted message → `remove`.

The partials are fragment-cached (`<% cache message do %>` in
[`_message.html.erb`][cf-msg-partial]) and collection renders pass `cached: true`, so the
broadcast path and the page-load path share one cache.

**OURS.** Pick the broadcast target by asking *"what is the smallest element that can be rendered
from the record alone, with no controller context?"* — `turbo.md` §6's no-`current_user` rule makes
that the real constraint, not aesthetics.

### 1.4 Catch-up after a dropped socket — the gap in our doctrine, and their answer

Our doctrine had nothing to say about the case that dominates real WebSocket apps: **the socket
was down for 40 seconds and the client missed three broadcasts.** Streams are fire-and-forget;
nothing replays them.

Campfire's answer is a plain REST resource, and it is deliberately unglamorous
([`app/controllers/rooms/refreshes_controller.rb`][cf-refresh],
[`app/views/rooms/refreshes/show.turbo_stream.erb`][cf-refresh-view]):

```ruby
class Rooms::RefreshesController < ApplicationController
  include RoomScoped
  before_action :set_last_updated_at

  def show
    @new_messages     = @room.messages.with_creator.page_created_since(@last_updated_at)
    @updated_messages = @room.messages.without(@new_messages).with_creator.page_updated_since(@last_updated_at)
  end

  private
    def set_last_updated_at
      @last_updated_at = Time.at(0, params[:since].to_i, :millisecond)
    end
end
```

```erb
<%= turbo_stream.append dom_id(@room, :messages) do %>
  <%= render partial: "messages/message", collection: @new_messages, cached: true %>
<% end if @new_messages.any? %>

<% @updated_messages.each do |message| %>
  <%= turbo_stream.replace dom_id(message), partial: "messages/message", locals: { message: message } %>
<% end %>
```

The trigger is an **empty channel used purely as a connectivity signal** — `HeartbeatChannel` has
no body at all ([`app/channels/heartbeat_channel.rb`][cf-hb]) — and a controller that refetches
whenever the cable *reconnects* ([`refresh_room_controller.js`][cf-refresh-js]):

```javascript
export default class extends Controller {
  static values = { loadedAt: Number, url: String }

  #lastLoadedAt
  #offlineTimer = null
  #hiddenAt = null

  async connect() {
    if (!pageIsTurboPreview()) {
      this.#lastLoadedAt = this.loadedAtValue
      this.#channelDisconnected()

      this.channel = await cable.subscribeTo({ channel: "HeartbeatChannel" }, {
        connected: this.#channelConnected.bind(this),
        disconnected: this.#channelDisconnected.bind(this)
      })
    }
  }

  #channelConnected() { … }
  #channelDisconnected() { … }

  #refresh(reason) {
    get(this.urlValue, { query: { since: this.#lastLoadedAt, reason: reason }, responseKind: "turbo-stream" })
  }
}
```

Four things this design gets right, all of which we should adopt:

- **The high-water mark is read from the DOM, not from a JS variable.** `messageTargetConnected`
  raises `#lastLoadedAt` to the newest `data-message-updated-at` it sees, so it is correct after a
  Turbo restoration visit, after a stream insert, and after a morph — the state lives in the
  document, exactly as `stimulus.md` §10 prescribes.
- **Reconnect is not the only trigger.** A tab hidden for more than 60 s also refetches on
  becoming visible, because a backgrounded tab's socket may be alive but throttled.
- **Disconnect is debounced into an "offline" signal after 5 s**, dispatched on `window`; the
  composer listens and disables its fields ([`composer_controller.js`][cf-comp]). Brief blips do
  not flash the UI.
- **The catch-up endpoint is a resource** (`Rooms::RefreshesController#show`), not a custom action
  on the rooms controller — the rails-8 skill's `style.md` §6 rule, applied where it is least
  obvious.

**OURS.** Any page that depends on broadcasts for correctness needs a catch-up path. State it as
a requirement, not a nicety: a broadcast-only page is silently wrong after every network blip.
The minimum shape is *(a)* a monotonic high-water mark held in the DOM, *(b)* a `GET`
`…/refreshes?since=…` resource returning streams, *(c)* a call to it on cable reconnect **and** on
regaining visibility after a long hide.

### 1.5 Intercepting stream rendering to protect scroll position

**Framework fact** (Turbo ≥ 7.2): `turbo:before-stream-render` carries
`detail.newStream` (the incoming `<turbo-stream>`) and `detail.render` — and `detail.render` is
**writable**. Turbo dispatches the event, then calls `event.detail.render(this)`, so a synchronous
listener can substitute its own renderer.

Campfire uses it to keep a chat window from jumping ([`messages_controller.js`][cf-msgs-js]):

```javascript
export default class extends Controller {
  #paginator
  #scrollManager

  // <div data-action="turbo:before-stream-render@document->messages#beforeStreamRender">
  async beforeStreamRender(event) {
    const target = event.detail.newStream.getAttribute("target")

    if (target === this.messagesTarget.id) {
      const render = event.detail.render
      const upToDate = this.#paginator.upToDate

      if (upToDate) {
        event.detail.render = async (streamElement) => {
          const didScroll = await this.#scrollManager.autoscroll(false, async () => {
            await render(streamElement)
            …
          })
          if (!didScroll) { this.latestTarget.hidden = false }
        }
      } else {
        this.latestTarget.hidden = false
      }
    }
  }
}
```

Three points: it **captures and calls the original `render`** rather than reimplementing it; it
**filters by target id** so it only wraps its own container; and when the user has scrolled away
it declines to render-and-scroll at all, revealing a "jump to latest" affordance instead.

**OURS.** Wrapping `detail.render` is the correct hook for "apply this stream, but preserve
something the DOM knows and the server doesn't" — scroll, an open menu, an in-flight animation.
Always capture and invoke the original; never replace it wholesale.

### 1.6 Unsubscribing a container from streams, on purpose

An 11-line controller worth knowing about ([`turbo_streaming_controller.js`][cf-ts-js]):

```javascript
// Unsubscribe a container from turbo streaming actions (by removing its id) can address timing jank
// when turbo streaming updates race against a full controller response.
export default class extends Controller {
  static targets = [ "container" ]

  unsubscribe() {
    this.containerTarget.removeAttribute("id")
  }
}
```

Because stream actions address elements by `id`, **removing the id makes a container
unaddressable** — arriving streams silently find nothing. It is the escape hatch for the race
where a full-page response and a broadcast both want the same region.

**OURS.** Use it knowingly and briefly; it is a *mute*, and a muted region misses updates it will
never be told about. Prefer §1.4's catch-up path over leaving anything muted across a navigation.

[cf-bc]: https://github.com/basecamp/once-campfire/blob/main/app/models/message/broadcasts.rb
[cf-mc]: https://github.com/basecamp/once-campfire/blob/main/app/controllers/messages_controller.rb
[cf-msg]: https://github.com/basecamp/once-campfire/blob/main/app/models/message.rb
[cf-tpl]: https://github.com/basecamp/once-campfire/blob/main/app/views/messages/_template.html.erb
[cf-cm]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/models/client_message.js
[cf-comp]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/composer_controller.js
[cf-msgs-js]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/messages_controller.js
[cf-msg-partial]: https://github.com/basecamp/once-campfire/blob/main/app/views/messages/_message.html.erb
[cf-refresh]: https://github.com/basecamp/once-campfire/blob/main/app/controllers/rooms/refreshes_controller.rb
[cf-refresh-view]: https://github.com/basecamp/once-campfire/blob/main/app/views/rooms/refreshes/show.turbo_stream.erb
[cf-refresh-js]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/refresh_room_controller.js
[cf-hb]: https://github.com/basecamp/once-campfire/blob/main/app/channels/heartbeat_channel.rb
[cf-ts-js]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/turbo_streaming_controller.js

---

## 2. Morphing in production (Fizzy)

### 2.1 `broadcasts_refreshes` is the whole real-time layer

```ruby
module Board::Broadcastable
  extend ActiveSupport::Concern

  included do
    broadcasts_refreshes
    broadcasts_refreshes_to ->(board) { [ board.account, :all_boards ] }
  end
end
```

**Framework fact.** `broadcasts_refreshes` broadcasts a bare
`<turbo-stream action="refresh" request-id="…">` — no partial is rendered — and the two macros
differ in target: `broadcasts_refreshes_to(stream)` sends everything to the given stream (a lambda
is accepted, as above), while `broadcasts_refreshes` sends **creates to `model_name.plural`** and
**updates/destroys to the record itself**. That asymmetry is not cosmetic: a record that does not
exist yet has no per-record subscribers, so a create has to go to the collection stream. Get it
wrong and creates appear to "not broadcast".

The second line above is how Fizzy gets both: per-board subscribers see their board refresh, and
anyone on the board *index* sees the list refresh, from one commit.

**Framework fact — the debounce.** `broadcast_refresh_later_to` runs through
`Turbo::ThreadDebouncer`, keyed on **stream name + `Turbo.current_request_id`** with a 0.5 s
default delay, cancelling and rescheduling on each call — so the job is not enqueued until the
window closes. A loop touching 500 records in one request emits one refresh per stream, not 500.
Two limits on that: the debouncer is stored in `Thread.current`, so it coalesces **within one
thread only** — two worker threads touching the same stream do not coalesce with each other — and
`Turbo.current_request_id` comes from the `X-Turbo-Request-Id` header via
`Turbo::RequestIdTracking`'s `around_action`, so "per request" is the practical effect of a
thread-local timer, not a guarantee.

### 2.2 Why a refresh doesn't bounce back at the tab that caused it

The half of `broadcasts_refreshes` that makes it usable, and it is worth knowing the exact
numbers because they bound it.

**Framework fact (Turbo 8.0+; none of this exists in Turbo 7).** Every fetch Turbo issues mints a
UUID, stores it client-side, and sends it as `X-Turbo-Request-Id`. `Turbo::RequestIdTracking`
puts it in a thread-local; `turbo_stream_refresh_tag` stamps it onto the broadcast as
`request-id`. On arrival, `Session#refresh` skips the visit when the id is one the tab
itself sent:

```javascript
const isRecentRequest = requestId && this.recentRequests.has(requestId)
if (!isRecentRequest && !this.navigator.currentVisit && isCurrentUrl) { this.visit(…) }
```

So the acting tab already has the fresh page from its own response and does not re-fetch, while
every other subscriber does.

**The bound to know: `recentRequests` is a `LimitedSet(20)` — twenty ids, FIFO eviction, per page
load.** The comparison is exact string equality. Two consequences worth designing around:

- A tab that fires more than twenty Turbo requests between causing a change and receiving its
  broadcast **loses the suppression** and refreshes itself. Harmless with morphing (it re-renders
  to the same DOM), which is part of why morph is the right refresh method.
- The other two conditions matter too: a refresh is also skipped while a visit is already in
  flight, and it only fires when the broadcast's URL **is the current URL**.

### 2.3 Per-stream morphing where a refresh is too blunt

Fizzy is not purely refresh-driven; where it writes streams by hand, it morphs them
([`app/views/columns/cards/drops/columns/create.turbo_stream.erb`][fz-drop-view]):

```erb
<%= turbo_stream.replace(dom_id(@column), partial: "boards/show/column", method: :morph, locals: { column: @column }) %>
```

That is the `method="morph"` attribute from `turbo.md` §5. A Kanban column holds scroll position
and possibly an open card; a plain `replace` would reset both.

**OURS.** When a stream targets a region the user can be interacting with, `method: :morph` is the
default and a plain `replace` is the exception. It costs nothing and removes a whole class of
"why did my scroll jump" bug.

### 2.4 The two morph hazards they hit — and neither is in the handbook

**Hazard one: morph closes an open `<dialog>`.** A `<dialog>` opened with `showModal()` has an
`open` attribute the server never rendered. Morph sees an attribute the new HTML lacks and removes
it — the dialog vanishes mid-interaction. Fizzy cancels exactly that one attribute
([`dialog_controller.js`][fz-dialog]):

```javascript
preventCloseOnMorphing(event) {
  if (event.detail?.attributeName === "open") {
    event.preventDefault()
    event.stopPropagation()
  }
}
```

**Framework fact:** `turbo:before-morph-attribute` is cancelable and its `detail` carries
`attributeName` (and `mutationType`); `preventDefault()` makes Idiomorph skip that attribute.
Turbo 8.0+.

**Hazard two: a broadcast refresh morphs away an edit in progress.** Fizzy's fix is 16 lines and
the comment is the doctrine ([`morph_guard_controller.js`][fz-morph-guard]):

```javascript
// Marks the enclosing turbo-frame permanent while connected, so that a
// broadcasted page refresh can't morph away an edit in progress. The attribute
// is never in the server-rendered markup, so display mode stays morphable and
// page replacements never transplant the frame.
export default class extends Controller {
  connect() {
    this.frame = this.element.closest("turbo-frame")
    this.frame?.setAttribute("data-turbo-permanent", "")
  }

  disconnect() {
    this.frame?.removeAttribute("data-turbo-permanent")
  }
}
```

**Why this is sound and not a hack** — verified in Turbo 8.0.23 `src/core/morphing.js`: the morph
skip is a bare `!currentElement.hasAttribute("data-turbo-permanent")` check with **no `id`
involved**, whereas Drive's cross-visit persistence selects `[id][data-turbo-permanent]`. Applying
the attribute at runtime therefore buys the morph exemption for the lifetime of the edit form
without opting the element into Drive's element-transplanting behaviour, and removing it on
`disconnect` restores normal morphing. `turbo.md` §3 now records the distinction.

**OURS.** Adopt both. Any client-only attribute state (`open`, `aria-expanded`, a `data-state`
your controller toggles) is a morph hazard, and the two tools are: cancel
`turbo:before-morph-attribute` for a single attribute, or set `data-turbo-permanent` from
`connect()`/`disconnect()` for a whole region that is temporarily uncontrollable by the server.
Never leave `data-turbo-permanent` in server-rendered markup for this purpose — it changes Drive
behaviour too.

[fz-drop-view]: https://github.com/basecamp/fizzy/blob/main/app/views/columns/cards/drops/columns/create.turbo_stream.erb
[fz-dialog]: https://github.com/basecamp/fizzy/blob/main/app/javascript/controllers/dialog_controller.js
[fz-morph-guard]: https://github.com/basecamp/fizzy/blob/main/app/javascript/controllers/morph_guard_controller.js

---

## 3. Action Cable vs Turbo Streams — our doctrine holds, sharpened

Our existing posture is "Streams first, ActionCable only for justified cases". **Campfire agrees,
and gives the rule a testable edge.** Both mechanisms appear in the same six-line method
([`message/broadcasts.rb`][cf-bc]): `broadcast_append_to` for the message, and
`ActionCable.server.broadcast("unread_rooms", { roomId: room.id })` for the badge.

The line they draw:

| Use | Mechanism |
|---|---|
| The server knows exactly what the DOM should become | **Turbo Stream** |
| The server has a *fact*; the client decides what it means | **raw Action Cable JSON** |

Every one of Campfire's six channels is on the second side: unread-room ids, read receipts, typing
start/stop, presence, and a bodiless heartbeat. None of them carries HTML. That is the honest
justification our doctrine was missing — not "ActionCable when Streams are hard", but **"Action
Cable when the payload is a fact, not a fragment"**, because a fact means something different to
each recipient (a badge, a sound, a scroll decision) and the server cannot render all of them.

### 3.1 Channels compose by inheritance, and the callbacks are real Rails

```ruby
class RoomChannel < ApplicationCable::Channel
  def subscribed
    if @room = find_room
      stream_for @room
    else
      reject
    end
  end

  private
    def find_room
      current_user.rooms.find_by(id: params[:room_id])
    end
end
```

```ruby
class PresenceChannel < RoomChannel
  on_subscribe   :present, unless: :subscription_rejected?
  on_unsubscribe :absent,  unless: :subscription_rejected?
  …
end
```

Two things here are load-bearing:

- **Authorisation is association traversal, exactly as `multi-tenancy.md` §2 prescribes.**
  `current_user.rooms.find_by(id: params[:room_id])` cannot resolve a room the user is not in, so
  `reject` is reached structurally rather than by remembering a check. `TypingNotificationsChannel`
  and `PresenceChannel` inherit that for free by subclassing.
- **Framework fact:** `after_subscribe` / `after_unsubscribe` are real `ActionCable::Channel`
  class-level callbacks, **aliased `on_subscribe` / `on_unsubscribe`**, and they accept standard
  ActiveSupport callback options such as `unless:`. `subscription_rejected?` is a real predicate —
  but it is **private**, which is fine as a callback condition (conditions are invoked via `send`)
  and not fine if you try to call it from outside. `on_unsubscribe` fires on an ungraceful client
  disconnect as well as an explicit unsubscribe (`Connection#handle_close` →
  `unsubscribe_from_all`), which is what makes presence teardown reliable.

### 3.2 Presence is connection-counted with a TTL, not a boolean

`Membership::Connectable` ([source][cf-conn]) keeps a `connections` counter and a `connected_at`
timestamp with a 60-second TTL:

```ruby
CONNECTION_TTL = 60.seconds

scope :connected,    -> { where(connected_at: CONNECTION_TTL.ago..) }
scope :disconnected, -> { where(connected_at: [ nil, ...CONNECTION_TTL.ago ]) }
```

The client refreshes every 50 s ([`presence_controller.js`][cf-presence]) — comfortably inside the
60 s TTL — and **delays visibility transitions by 5 s** so alt-tabbing does not churn presence.

**OURS.** Presence is a counter with an expiry, never a boolean. A boolean is wrong the moment a
user opens a second tab (leaving one marks them away) or the moment a process dies without running
teardown (they stay online forever). The counter handles the tabs; the TTL handles the crash.
Size the client refresh interval strictly *inside* the TTL, and debounce visibility changes.

### 3.3 One honest cost, recorded rather than glossed

`ActionCable.server.broadcast("unread_rooms", { roomId: room.id })` is a **global** stream: every
connected user in the installation receives every message's room id, and each client decides
whether it cares. For a single-team Campfire install that is a sound trade — one broadcast instead
of per-user fan-out. It does **not** generalise to a multi-tenant SaaS, where it would leak the
existence and activity rate of other tenants' rooms to every connected client.

**OURS.** Scope signal channels per tenant (or per user, as Campfire's own
`"user_#{current_user.id}_reads"` stream does). A global `stream_from` in a multi-tenant app is a
cross-tenant information leak even when the payload looks harmless — an id and a timestamp are a
volume-and-activity oracle. `multi-tenancy.md` §2's "scope through associations" applies to
streams too.

[cf-conn]: https://github.com/basecamp/once-campfire/blob/main/app/models/membership/connectable.rb
[cf-presence]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/presence_controller.js

---

## 4. Stimulus organisation at 35 and 69 controllers

### 4.1 The shape

Neither app has a `mixins/` directory, a base-controller hierarchy, or any `Object.assign`
composition. Both use flat `controllers/` plus **plain ES modules that are not controllers**:

| | Campfire | Fizzy |
|---|---|---|
| `controllers/` | 35 | 69 (8 under `bridge/`) |
| `helpers/` (exported functions) | 5 | 10 |
| `models/` (plain classes) | 6 | — |
| `lib/` | 18 | 2 |
| `initializers/` | 5 | 5 |

**Naming is by behaviour, never by page** — `auto_submit`, `toggle_class`, `copy_to_clipboard`,
`element_removal`, `local_time`, `soft_keyboard` appear in *both* apps under the same names. That
is `stimulus.md` §10's rule confirmed by two independent codebases, and it is the reason 69
controllers stay navigable.

**Non-trivial logic leaves the controller.** Campfire's `messages_controller.js` is 190 lines and
delegates to four plain classes — `ClientMessage`, `MessageFormatter`, `MessagePaginator`,
`ScrollManager` — each constructed in `connect()`. The controller stays an adapter between DOM
events and objects that know nothing about Stimulus.

**OURS.** Extract to a plain class (not another controller) as soon as a controller holds
algorithmic state — a paginator, a scroll manager, a tracker. Controllers are wiring; plain
objects are logic, and they are testable without a DOM.

### 4.2 Verdict on our four-mixin doctrine — **not contradicted, but not corroborated either**

The `design-system` skill prescribes four reusable Stimulus mixins (list-navigation, focus-trap +
restore, dismissable-layer, anchored-position) composed into components. #99 asks whether real
usage validates that. Read honestly:

- **Neither app uses JS mixins at all — and neither uses controller inheritance either.** Checked
  against the source rather than a code-search index: across all **161** JS files in the two
  `app/javascript` trees there is **not one** `Object.assign`-style composition or mixin module, and
  of the **104** Stimulus controllers, **96 extend the bare `Controller` imported straight from
  `@hotwired/stimulus`** — the other 8 are Hotwire Native `BridgeComponent`s. Zero intermediate base
  classes. So there is **no upstream corroboration** for the mixin *mechanism*, and none for a
  base-class alternative either.

  (Re-check: `gh api repos/basecamp/fizzy/tarball/main`, untar, then
  `grep -rhoE '^export default class[^{]*' --include='*_controller.js' app/javascript | sort | uniq -c`.
  This was done by tarball on purpose — `gh search code` returning nothing is not evidence that
  nothing is there.)
- **But both solve the same problem the mixins solve, by a different mechanism.** Fizzy's
  `navigable_list_controller.js` is a single generic controller carrying **eleven** boolean/string
  `values` (`reverseOrder`, `selectionAttribute`, `focusOnSelection`, `actionableItems`,
  `supportsHorizontalNavigation`, `hasNestedNavigation`, `autoSelect`, `autoScroll`, …). That is
  our list-navigation mixin's job, delivered as **one parameterised controller reused by
  configuration** rather than a behaviour mixed into many controllers.
- Fizzy likewise has one `dialog_controller`, one `tooltip_controller`, one `combobox_controller` —
  generic, reused, configured by `values`.

**Verdict: our four-mixin doctrine is a design decision of ours, and this evidence neither
confirms nor refutes it.** Recording that plainly is the point — dressing "37signals build one
generic controller" as validation of "build four mixins" would be exactly the kind of citation
that does not survive being checked. What the evidence *does* support is the shared premise:
**shared interaction behaviour is built once and reused, never re-solved per component.** Both
mechanisms honour that; ours composes, theirs parameterises.

What the evidence **does** refute, for anyone tempted by it, is a third option we have never
proposed and now should not: **a base-controller hierarchy.** 104 controllers, zero intermediate
base classes, in two apps by the framework's authors. Reuse in Stimulus goes through
configuration, outlets, and plain modules — not through `extends`.

One caution the comparison earns: a controller with eleven configuration values is what the
parameterised approach costs at scale, and it is a real cost. If a mixin ever grows that many
knobs, the mixin has stopped being a mixin.

### 4.3 Three techniques worth stealing outright

**Skip registration instead of bailing out of `connect()`.** `navigable_list_controller.js`:

```javascript
// Don't load for mobile devices
static get shouldLoad() {
  return !isMobile()
}
```

**Framework fact:** `static get shouldLoad()` (Stimulus 3.0+) prevents registration entirely; the
companion `static afterLoad(identifier, application)` (Stimulus 3.2+) runs once at registration.
Now recorded in `stimulus.md` §1.

**Do not start timers or sockets while a cached preview is on screen.** Campfire guards every
expensive `connect()` with:

```javascript
if (!pageIsTurboPreview()) { … }
```

```javascript
export function pageIsTurboPreview() {
  return document.documentElement.hasAttribute("data-turbo-preview")
}
```

**Framework fact:** Turbo sets `data-turbo-preview` on `<html>` while displaying a cached snapshot
as a preview, and removes it when the fresh page renders (`View#markAsPreview`). Without this
guard a back-button visit opens a WebSocket and starts a refresh timer for a page that is about to
be thrown away — twice, once for the preview and once for the real render.

**OURS.** Guard on `data-turbo-preview` in `connect()` for anything that costs a network
connection, a timer, or a third-party widget instantiation. Cheap DOM setup does not need it.

**Ignore disconnects that are really re-renders.** A stream or morph can remove and re-add an
element within a frame, firing `disconnect()`/`connect()` for what the user experiences as nothing.
Campfire's helper defers the teardown by one frame and checks whether the element really left
([`dom_helpers.js`][cf-dom]):

```javascript
export function ignoringBriefDisconnects(element, fn) {
  requestAnimationFrame(() => {
    if (!element.isConnected) fn()
  })
}
```

Used to avoid tearing down and re-establishing an Action Cable subscription on every re-render
([`read_rooms_controller.js`][cf-read]). **OURS:** apply it to teardown that is *expensive to
redo* — sockets, observers, third-party widgets — not to cheap listener cleanup, which should stay
unconditional per `stimulus.md` §2.

[cf-dom]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/helpers/dom_helpers.js
[cf-read]: https://github.com/basecamp/once-campfire/blob/main/app/javascript/controllers/read_rooms_controller.js

---

## 5. Drag-and-drop without a JS framework (Fizzy)

150 lines, native HTML5 drag events, **no library**
([`drag_and_drop_controller.js`][fz-dnd]). The shape of `drop()` is the whole lesson:

```javascript
export default class extends Controller {
  async drop(event) {
    const targetContainer = this.#containerContaining(event.target)

    if (!targetContainer || targetContainer === this.sourceContainer) { return }

    this.wasDropped = true
    this.#increaseCounter(targetContainer)          // 1. optimistic: adjust counts
    this.#decreaseCounter(this.sourceContainer)

    const sourceContainer = this.sourceContainer
    this.#insertDraggedItem(targetContainer, this.dragItem)   // 2. optimistic: move the node
    await this.#submitDropRequest(this.dragItem, targetContainer)  // 3. POST, streams come back
    this.#reloadSourceFrame(sourceContainer)                       // 4. reconcile the source
  }

  #containerContaining(element) { … }
  #increaseCounter(container) { … }
  #decreaseCounter(container) { … }
  #insertDraggedItem(container, item) { … }
  #submitDropRequest(item, container) { … }
  #reloadSourceFrame(sourceContainer) { … }
}
```

Five things to take:

1. **Move the real DOM node; do not re-render it.** `#insertDraggedItem` calls
   `referenceItem.before(item)` / `.after(item)` on the element the user was dragging, so there is
   no flash and no lost state.
2. **The drop is a POST to a nested resource, not a custom action.** The URL comes from
   `container.dataset.dragAndDropUrl` with an `__id__` placeholder, and it resolves to routes like
   `columns/cards/drops/columns` and `columns/cards/drops/closures` — one resource per *meaning* of
   a drop. This is `style.md` §6 ("introduce a new resource rather than adding custom actions")
   holding up in the least likely place.
3. **The server response is a Turbo Stream** (`Accept: text/vnd.turbo-stream.html`) that morphs the
   destination column (§2.3). The optimistic DOM move and the authoritative render agree because
   they target the same `dom_id`.
4. **The source container reloads its own frame** rather than being patched by the response —
   `frame.reload()`. Two regions changed; the response owns one and the client asks for the other.
5. **Optimistic counters are validated before being touched:**
   `if (!/^\d+$/.test(currentValue)) return`. If the DOM does not hold what the controller expects,
   it does nothing rather than writing `NaN`.

**OURS.** For drag-and-drop, adopt this shape: optimistic node move → POST to a resource named for
the *meaning* of the drop → morphing stream for the destination → `frame.reload()` for anything
else that changed. Do not reach for a drag library; do not re-render the dragged element.

**One thing we do NOT take.** The controller cleans up in `dragEnd`, which the browser fires after
a cancelled drag as well as a completed one — adequate for pointer-driven HTML5 drag. It is not the
full gesture-abandonment contract the `design-system` skill requires for custom pointer gestures
(window `blur`, `visibilitychange`, `pointercancel`, and the rest), because native `dragend` covers
cases a hand-rolled pointer gesture must handle itself. Use this pattern for HTML5 drag; do not
read it as licence to skip that contract when you build a gesture from raw pointer events.

[fz-dnd]: https://github.com/basecamp/fizzy/blob/main/app/javascript/controllers/drag_and_drop_controller.js

---

## 6. Offline — what Fizzy's Gemfile pin actually means (do NOT copy it)

Fizzy's Gemfile carries:

```ruby
gem "turbo-rails", github: "hotwired/turbo-rails", branch: "offline-cache"
```

and the app calls a `Turbo.offline` API ([`initializers/offline.js`][fz-offline],
[`clear_offline_cache_controller.js`][fz-clear]):

```javascript
Turbo.offline.start("/service-worker.js", { scope: "/", native: true, preload: /\/assets\// })
```

**Verified verdict: this API exists in no released version of Turbo or turbo-rails.** It lives only
on the `hotwired/turbo-rails` `offline-cache` branch, which re-exports from `@hotwired/turbo/offline`
— code that is itself an **open, unmerged** pull request, [hotwired/turbo#1427][turbo-1427]. The
matching turbo-rails PR (#751) was **closed unmerged** by its own author with "the code this uses is
still not merged". Neither `@hotwired/turbo@8.0.23` nor `turbo-rails` v2.0.23 ships an `offline`
export.

**OURS — do not use it, and do not pin a branch to get it.** A git-branch gem pin has no release
cadence, no changelog, no deprecation policy, and no guarantee the branch survives; 37signals can
absorb that because they employ the people who write it. What this *does* tell us is directional:
offline Turbo is being built, by Basecamp, against a real app. Track #1427; adopt when it ships in
a release. Until then, if a project genuinely needs offline reads, that is a deliberate
service-worker decision made and owned by the project, not something Hotwire provides.

This is the most valuable finding in the file precisely because it is negative. Reading Fizzy's
Gemfile as "37signals do offline Hotwire, so we can" would have put an unreleasable dependency into
our doctrine.

[fz-offline]: https://github.com/basecamp/fizzy/blob/main/app/javascript/initializers/offline.js
[fz-clear]: https://github.com/basecamp/fizzy/blob/main/app/javascript/controllers/clear_offline_cache_controller.js
[turbo-1427]: https://github.com/hotwired/turbo/pull/1427

---

## 7. What we did not take, and what stays contested

- **`Turbo.offline`** — rejected outright (§6): unreleased, unmerged, branch-only.
- **A global signal stream** — rejected for multi-tenant apps (§3.3), while recording why it is
  reasonable in Campfire's single-installation context.
- **Campfire's `#generateClientId()`** uses `Math.random().toString(36).slice(2)` where the server
  uses `Random.uuid`. Copy the *pattern*, not that generator: use `crypto.randomUUID()`. This is
  ours — the collision risk is small but there is no reason to accept it when the platform ships a
  UUID generator.
- **The four-mixin doctrine stays ours** (§4.2), explicitly neither confirmed nor refuted.
- **Testing and CSS divergences are out of scope here** — 37signals use Minitest + Capybara and
  hand-written CSS where we mandate RSpec and Tailwind. Those are recorded decisions belonging to
  the rails-8 skill (see `style.md` and EPIC #96 Phase E), not to Hotwire.

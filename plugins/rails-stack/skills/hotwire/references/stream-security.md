# Authorizing Turbo Streams — what the signature does not do

Versions in scope: Turbo 8.0.23, turbo-rails 2.0.23, Rails 8.0.x. Every claim below was verified on 2026-10-21 by `doctrine-verifier` against the
turbo-rails and Turbo sources at those versions, with the quoted phrases matched to the raw files (`app/channels/turbo/streams_channel.rb`,
`app/channels/turbo/streams/broadcasts.rb`). Re-verify before relying on it past a major version of turbo-rails.

## Contents
1. What a signed stream name protects
2. Where the access control actually is
3. A broadcast renders with no request: no viewer
4. What the checks enforce (`check_turbo_streams.py`)

---

## 1. What a signed stream name protects

`turbo_stream_from @room` embeds a **signed** stream name in the page, and `Turbo::StreamsChannel#subscribed` accepts a subscription only if that name
verifies. turbo-rails says so in its own header: "If the signed stream name cannot be verified, the subscription is rejected." (`streams_channel.rb`).

That signature is **integrity**, not authorization:

- A client cannot forge a stream name or change one it was given.
- `Turbo::StreamsChannel#subscribed` does not look at `current_user`. **Anyone who holds a valid signed name can subscribe to it.**
- The signed name does not expire (the verifier is built without `expires_in`, `lib/turbo-rails.rb`).

So "the name is signed, so only the right people can listen" is false. Whoever can see the page that embeds the name — or whoever was ever handed the
signed string — can listen, from any session, indefinitely.

## 2. Where the access control actually is

There are three, and a stream that relies on none of them is public:

1. **Which pages embed the name.** `turbo_stream_from @project` belongs only in a view the viewer was authorized to see: the controller that renders it
   authorizes the record first (`authorize @project`, a scoped `find`). A shared page with a literal name (`turbo_stream_from "announcements"`) is a
   public stream by construction.
2. **Action Cable connection authentication.** `ApplicationCable::Connection` identifies the connection (the session cookie) and rejects an unknown or
   expired one (`reject_unauthorized_connection`). It decides who may connect at all, not who may subscribe to what.
3. **A custom channel that checks the subscription.** turbo-rails documents it in the header of `streams_channel.rb`: a channel on
   `ActionCable::Channel::Base` that extends `Turbo::Streams::Broadcasts, Turbo::Streams::StreamName`, includes `Turbo::Streams::StreamName::ClassMethods`,
   and whose **own `subscribed`** opens with the guard: `if (stream_name = verified_stream_name_from_params).present? && subscription_allowed?` then `stream_from stream_name`, `else reject` (a guard clause, `reject unless subscription_allowed?`, is the same check); pass `channel: CustomChannel` to `turbo_stream_from`.
   **Defining `subscription_allowed?` in a subclass of `Turbo::StreamsChannel` checks nothing**: its `subscribed` (lines 38-44) only verifies the signed
   name and never calls the method, so such a channel is as open as the default. Use a custom channel when two viewers can hold the same signed name but
   only one may listen.

**Per-user or per-tenant stream names** (`turbo_stream_from [current_user, :notifications]`) are name hygiene: a viewer is never handed another
viewer's name. They help with 1, and they do not replace it.

## 3. A broadcast renders with no request: no viewer

A broadcast renders its partial through `ApplicationController.render` (`broadcasts.rb`), from a model callback or a job: **there is no request, session or
cookies**. `current_user`, `current_*` helpers, `session`, `cookies` and `Current.*` are undefined or nil there, so a partial that uses them raises, or
renders unauthenticated output into a stream that many subscribers receive.

- Pass everything the partial needs as locals.
- Never put per-viewer data in a partial that goes to a shared stream. Per-viewer parts travel on that viewer's own stream.

## 4. What the checks enforce

`scripts/check_turbo_streams.py` (the `turbo-streams` row of `checks.json`) reads the project's source, never runs it:

| rule | finding |
|---|---|
| a `turbo_stream_from` whose **only stream argument** is a literal name (a string without interpolation, or a symbol; `turbo_stream_from "x", current_user` is scoped to a viewer, so it is not one) | a shared public stream, unless the name is declared in `.rails-flow/public-streams.json` with a reason |
| a declared public stream nothing uses, or one with no reason | stale or unexplained declaration |
| `turbo_stream_from ... channel: Name` | `app/channels/name.rb` must exist and its **own `subscribed` must open with the guard** (`reject unless subscription_allowed?`, or turbo-rails' own `if ... && subscription_allowed? ... else reject`); a subclass that only defines the method or inherits `subscribed`, a `super` inside `subscribed` on a `Turbo::StreamsChannel` subclass, a `stream_from` before the check, or the name only in a comment, is a finding; so is an ambiguous file (a second `subscribed` as `def` or `define_method`, a `=begin` block, or anything after `def subscribed` on its line), which is refused rather than parsed |
| a partial reached by a broadcast (`partial:` of a `broadcast_*` call, or the default partial of `broadcasts_to`) that mentions `current_user`, `current_*`, `session`, `cookies` or `Current.` | the line, with the partial's path |

The declaration is JSON: `{"public": [{"stream": "announcements", "reason": "release notes every signed-in and signed-out visitor may read"}]}`.

**Limits, stated plainly:** this is a static read of names and partials. A broadcast partial is read as **one file**: a helper it calls, or a partial it
renders, is not followed, so `current_user` hidden one level down is not found. **The channel check enforces the shape of the guard, not its logic**: `subscription_allowed? || true`, or a `subscription_allowed?` that returns `true`, passes, and whether the boolean is right is a review judgement. And it cannot tell whether the controller that renders a page with
`turbo_stream_from @project` authorized `@project` (rule 1 of §2): that stays a review judgement, covered by the code-review skill, not by this check.

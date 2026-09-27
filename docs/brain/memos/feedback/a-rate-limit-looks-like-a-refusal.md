---
name: feedback-a-rate-limit-looks-like-a-refusal
description: A sign-in spec failed every other run because the app rate-limits sign-in; five hypotheses chased the symptom before one logged the POST.
type: feedback
---

`SessionsController` rate-limits `create` to **ten posts in three minutes** and answers the
eleventh with a redirect and "Try again later." On a sign-in card that is **indistinguishable from
a refused password** — same URL, same reopened form — so a browser spec that signs in five times
failed every other run, and every diagnosis downstream was chasing a symptom of it.

Hypotheses tested and discarded first, each costing a round of edits: a blank form submission, a
turbo-frame race, a slow server, a lost route table, and mail blocking a Puma thread (that last one
**measured** on a branch with the mail fix merged — the failure still happened, so it was not mail).

One run with a request listener settled it:

```ts
page.once("request",  r => console.log("POST:", r.postData()?.slice(0, 160)));
page.once("response", r => console.log("RESP:", r.status(), r.headers()["location"]));
```

`302 → /login` is the rate limiter's redirect and nothing else's.

**Why:** an app's own protections are part of the environment a test runs in, and the ones designed
to be indistinguishable from a failure — rate limits, lockouts, generic sign-in errors — are exactly
the ones a test cannot tell from the bug it is looking for.

**How to apply:** when a spec that repeats an authenticated action fails **intermittently and in
groups**, read the controller for `rate_limit`, lockout counters and throttles BEFORE theorising
about timing. Then spend fewer of the rationed action rather than asking for more: reuse a session
for the cases that are not about signing in, and drop retry loops, which double the cost of exactly
the runs already at the limit. And log the request and response once — it is cheaper than three
rounds of hypothesis. Related: [[repeat-before-blaming-your-change]],
[[a-stale-server-fails-as-a-behaviour-bug]], [[a-check-that-cannot-tell-the-two-apart]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-rate-limit-looks-like-a-refusal.md._

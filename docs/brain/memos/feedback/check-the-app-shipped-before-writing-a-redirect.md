---
name: feedback-check-the-app-shipped-before-writing-a-redirect
description: I wrote 10 permanent 301s to protect users of an app that had never been deployed; check git tag and the deploy config first.
type: feedback
---

Moving Retask's routes, I shipped ten permanent 301s and defended them in code comments,
specs, a decision record, the CHANGELOG and two PR bodies with: *"these paths are in
people's history, in mail this app has already sent, and in the spec documents."*

The maintainer: **"it is a fresh application, we do not have any route history anywhere."**
`git tag` was empty and `.kamal/` held only `deploy.env.example`. The app had never been
deployed — I had written a rule for a live product and applied it to one with no users.

**Why:** a compatibility redirect exists for a path a REAL user can still reach. In a
pre-deploy app it protects nobody, and a *permanent* 301 is actively harmful: browsers
cache it hard, so it must later be fought in every browser that hit it. Mine redirected
away from `/account` while my own decision record said `/account` should one day mean the
organisation's record.

**How to apply:** before writing any compatibility redirect, check `git tag` and whether a
deploy has actually run. Pre-deploy, move the route and update every reference — the only
true reason left ("it is in the spec documents") is fixed by editing the documents.
The same test applies to any "for backwards compatibility" affordance: name the user it
protects, then check that user exists. See [[verify-counts-before-stating-them]] and
[[a-transcription-cannot-check-itself]] — a justification is a claim, and needs measuring
like any other.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, check-the-app-shipped-before-writing-a-redirect.md._

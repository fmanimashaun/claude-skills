---
name: feedback-a-stale-server-fails-as-a-behaviour-bug
description: After a migration, a browser-test failure is probably the running server's cached schema, not the change.
type: feedback
---

Rails caches each model's column list at boot. A server started **before** a migration keeps
answering and **silently drops the new column from every write** — no exception, no log line at the
call site. The browser suite then fails on behaviour while the code is correct, and the message
names something innocent: `unknown attribute 'round'` buried in a 500 page, or nothing at all — a
toast that never appears, an element "not found".

**Why:** it looks exactly like a defect in the change just made, so the instinct is to debug the
diff. It cost three separate debugging passes in one day on Retask (F-11's `exclusion_reason`,
F-12's schema, F-13's `round`), and the third time the culprit was a *second* server: `bin/e2e`
reuses whatever is answering on its port, so a long-lived process from an earlier run carried a
pre-migration schema into a suite I thought was fresh.

**GEMFILE.LOCK IS THE SAME CLASS.** Adding a gem and re-running the browser suite reused a server
whose Bundler setup predated the install: every page requiring the new library answered 500, and the
failure read as "the form field is missing" on a screen that was correct. Retask's
`bin/assert-fresh-server` now compares the listener's start time against `Gemfile.lock` as well as
`db/schema.rb`, with a separate message — a gem off the load path is a different problem from a
cached column list. And when proving such a check fires, **make sure a server is actually
listening**: the first attempt exercised the exit-0 "nothing to be stale" path and demonstrated
nothing (a stale `tmp/pids/server.pid` from a long-lived dev server had blocked the boot; use
`--pid`).

**How to apply:** after any migration, restart every running server before believing a browser
failure — including ones started by tooling on other ports (`lsof -ti tcp:PORT -sTCP:LISTEN`).
Better, make the tool refuse: compare the listening process's start time against `db/schema.rb`'s
mtime. Retask's `bin/e2e` does this now. Note `ps -o etimes=` is a GNU extension macOS lacks — it
errors to stderr and the arithmetic swallows the empty value as zero, giving a guard that can never
fire; use `/proc/<pid>` mtime on Linux and `ps -o lstart=` on macOS, and prove the check in **both**
directions. Related: [[verify-in-the-environment-it-runs-in]], [[a-diagnostic-object-is-not-a-pass]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-stale-server-fails-as-a-behaviour-bug.md._

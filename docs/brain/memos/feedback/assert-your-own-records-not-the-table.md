---
name: feedback-assert-your-own-records-not-the-table
description: A spec that asserts a whole table's contents fails whenever the dev/test DB is seeded; six of them in one day.
type: feedback
---

`expect(Client.listed.map(&:code)).to eq(["SLH"])` and `expect(Request.queueable.pluck(:id)).to
eq([scanned.id])` are claims about **every row in the table**, not about what the example made.
They pass on an empty database and fail on a seeded one — and in Retask the test database
**alternates** between the two, because `spec/models/task_concurrency_spec.rb` must run with
`use_transactional_tests = false` (its threads need committed rows) and hand-cleans with
`delete_all`, which cannot tell seeded rows from its own. So `bin/ci` was red on roughly every
other run.

**Why:** the failing spec looks like a regression in the code under test. I chased three of these
into the model before noticing the pattern, and the same shape appeared six times in one day —
`root_admin_spec` creating the seeded root's own email address, `client_spec`, `request_routing_spec`,
and three Admin-fallback examples that created an admin and asserted it was the one chosen.

**How to apply:** assert `include(mine)` and `not_to include(theirs)`, never `eq([...])`, over any
scope that reads a whole table. Where a spec needs a specific seeded singleton (a root account, a
sole config row), **adopt and reset it** rather than creating a second one — `find_or_initialize_by`
plus explicitly named field resets, because deleting it hits a foreign key from its own audit trail.
Then prove it by running the suite on an empty **and** a seeded database; one green run proves
nothing. See [[a-number-two-sessions-agree-on-can-still-be-wrong]] and
[[repeat-before-blaming-your-change]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, assert-your-own-records-not-the-table.md._

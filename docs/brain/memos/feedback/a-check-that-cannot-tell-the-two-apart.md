---
name: feedback-a-check-that-cannot-tell-the-two-apart
description: A negative marker must be grepped against the thing it is meant to exclude — twice I picked one the alternative also contained.
type: feedback
---

When a check distinguishes A from B — live data from a demo illustration, a real record from a
fixture, a new rendering from the old one — the marker it keys on has to be **measured against B**,
not assumed absent from it. Both times I skipped that step the check passed with the feature deleted.

- `"from stamped records"` as proof a report read real records: the DESIGN'S OWN COPY says it too.
- `"Per client short code"` on the second attempt: it is the **prefix** of the canvas note
  `"Per client short code. The one report with a consumer outside Retask."`

And both were "verified" by grepping `canvas/screens.json` — **the wrong file**. Those particular
illustrations live in Ruby, in the canvas half of `admin_shell/reports.rb`.

**Why:** a discriminator is the entire content of such a check. If B contains the marker, the check
is green in both worlds and the mutation that deletes the feature survives — which is exactly what
happened, and the harness said so.

**How to apply:** before writing the assertion, `grep` the marker against the alternative's source
and confirm it is **absent** — and confirm you are grepping the file the alternative actually comes
from, since the same content often has two homes. Prefer a whole sentence only the live builder
writes over a phrase that could be a prefix. Related:
[[a-harness-that-cannot-see-a-broken-mutation]], [[coverage-counts-assertions-not-properties]],
[[a-default-for-missing-data-hides-present-data]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-check-that-cannot-tell-the-two-apart.md._

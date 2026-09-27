---
name: feedback-a-new-failure-branch-silences-old-fixtures
description: Adding a second way to fail can make untouched guards stop discriminating; re-run every guard on the file and read the ones that CHANGED VERDICT, including ones that still pass.
type: feedback
---

A peer added a second way for a script to return 1. Three **pre-existing** mutation fixtures stopped
discriminating: two began reporting "caught by the wrong fixture" and one **survived outright** —
all because they asserted `code == 1`, and a second route to 1 had appeared underneath them. Nobody
edited those fixtures. The harness found it; review did not.

**Why:** the obvious check — *is my new failure branch guarded?* — is the wrong question, and a
comfortable one, because the new branch is usually fine. The damage lands on guards that still
**pass**, now for a reason they were never written to assert. A passing guard is invisible to any
check phrased around the change you just made.

**How to apply:** after adding any second way to fail, **re-run every guard on that file and read
the ones whose verdict changed — including the ones that still pass.** Then ask what each fixture
actually asserts: an exit code, or the *reason*. A fixture asserting `code == 1` cannot tell two
failure paths apart, which is [[a-check-that-cannot-tell-the-two-apart]] and
[[a-value-two-causes-both-produce]].

Checked against my own case rather than assumed, which is the other half of this: the repo had no
mutation harness at all, so no fixtures existed to go quiet; the caller already collapsed every
failure to `exit 1`, so my `abort` was a second reason for an existing branch rather than a new one;
and since the caller runs the task with `>/dev/null`, I ran `ruby -e 'abort "X"' >/dev/null` to
confirm the diagnosis still reaches stderr rather than reasoning about it
([[a-mutation-caught-by-the-wrong-fixture]], [[a-harness-that-cannot-see-a-broken-mutation]]).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-new-failure-branch-silences-old-fixtures.md._

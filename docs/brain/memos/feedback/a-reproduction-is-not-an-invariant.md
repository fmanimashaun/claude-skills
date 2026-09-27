---
name: feedback-a-reproduction-is-not-an-invariant
description: Rejecting a reproduction test is not a reason to add no test; an invariant asserts a relationship between two live expressions and cannot pass for the wrong reason.
type: feedback
---

I argued against writing a spec for a fixture-mint bug, and I was right about the spec: a
reproduction would have to re-express the buggy query in its own arrangement, so it would pass for
the wrong reason the moment that query changed shape. I then wrongly concluded **no test was
needed**. A peer separated the two and the distinction is the lesson.

- A **reproduction** stages the failing input and asserts the failure is gone. It duplicates the
  thing under test ([[proving-the-helper-is-not-proving-the-caller]]).
- An **invariant** asserts a relationship between two live expressions — here, *the anchor is never
  a member of the set this task destroys*. It duplicates nothing, needs no fixture, and holds
  however either side is rewritten.

**Why:** the decisive question was not *is the bug detected* but **when**. The existing gate did
catch it — on the SECOND run after the regression, with a foreign key violation three layers from
its cause. A defect invisible for one whole run costs a day. Detection was never the gap; timely
detection was.

**How to apply:** when you reject a test as circular, say what the rule is in one sentence, then ask
whether that sentence can be asserted against live state instead of a fixture. Put it **in the code
path**, not in a spec, when the spec would have to rebuild the inputs. Then
[[a-rule-without-a-trigger-changes-nothing]] — remove the fix and confirm the guard fires with the
cause named, not the symptom ([[a-harness-that-cannot-see-a-broken-mutation]]).

Also: I wrote that the wedge lasted "until somebody deleted the row by hand". Nobody ever did — the
deletion was proposed and never authorised. A throwaway clause invented a manual recovery path that
did not exist, and would have sent the next reader hunting the row instead of the cause.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-reproduction-is-not-an-invariant.md._

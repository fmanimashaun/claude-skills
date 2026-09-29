---
name: feedback-outside-my-diff-is-a-claim
description: A PR author's 'doctrine reds are outside my diff' is a claim to check against the base, not a reason to merge — the gate's headline named the wrong file.
type: feedback
---

2026-09-25, Retask: a6 reported #948 as "bin/doctrine 30/2, both reds outside my diff" and I merged. Both reds came FROM #948 (two `<%# #899` comments, a hand-rolled cluster). The rails-flow erb-lint FAIL row quotes the first line herb printed, in no fixed order, so it named tasks/index:179 while the errors were in the new files; layout-composition's headline named a file sitting at its floor. Same thing had already happened once that day (#937 ← #929). Filed #950 to repair.

**Why:** a gate headline is not a location, and "not mine" was never measured — nobody ran doctrine at the base.

**How to apply:** before merging a PR whose author reports gate reds as pre-existing, require the same gate's row counts at the merge base (or run it), and check the reds' count doesn't grow. For erb-lint, ask for herb's own error list, not the gate headline. Related: [[a-check-that-cannot-tell-the-two-apart]], [[a-true-result-about-the-wrong-file]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, outside-my-diff-is-a-claim.md._

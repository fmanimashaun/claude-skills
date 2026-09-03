---
name: feedback-proving-the-helper-is-not-proving-the-caller
description: A fixture that proves a shared helper works does not prove the call site uses it — only running the real entry point does.
type: feedback
---

Two fixtures asserted `doctrine_path.find()` resolves an installed-plugin layout, and both passed.
A mutation putting the old hand-rolled `HERE.parents[3]` back into `main()` **survived them both** —
because nothing exercised `main`. The bug being fixed was precisely that the call site bypassed the
shared resolver. Only copying the script into an installed-shaped tree and running it as a
subprocess caught it.

**Why:** a helper's suite and a caller's suite are different claims. "The resolver works" and "this
script resolves" share no code path, so a green helper suite reads as coverage the caller never had.
This is how #617's fix reached four scripts and missed a fifth for two releases.

**How to apply:** when a fix is *route this call site through the shared thing*, the fixture must
drive the **entry point**, not the shared thing. Then mutate the call site back to the old code and
confirm the suite goes red. Related: [[downstream-runs-beat-code-review]],
[[verify-in-the-environment-it-runs-in]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, proving-the-helper-is-not-proving-the-caller.md._

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

**A mutation example can also miss the BRANCH.** Fixing Retask's audit-log addressing (2026-09-08)
I wrote three examples for defects I had reasoned out, mutated the fix away, and only one went red.
Two of my claimed defects did not exist — the positional arithmetic cancels under a prepend and
under a negative offset — and my example for the one that *was* real used a three-entry log, which
takes the `d<i>` branch where index and size never interact. It passed on the broken code. Fixed by
computing the index from `seeded_from` and asserting the id shape, so the example cannot drift back
into the branch that proves nothing.

**And read the MUTATION before believing the survivor.** Twelve F-16 mutations were scripted as
literal string replacements; one survived, and the reason was the edit, not the suite: `unless
@run.card_only?` became `unless false`, which makes the guard **unconditional** rather than absent.
The behaviour was never removed, so nothing could go red. A mutation that does not delete the
behaviour is not evidence of a coverage gap — check the mutated source reads the way you intended
before hunting for a missing example.

**A SURVIVOR CAN ALSO MEAN THE GUARD IS DEAD CODE.** `Cards::Open` carried a hand-written
`return if card.photograph.attached? && blob_id == life.photograph.blob.id` for the batch that
reaches QA pass twice. Deleting it killed nothing — because Active Storage already keeps the same
attachment row when the blob matches, so the guard could never fire. The right repair was to delete
the guard and write an example holding the property the framework provides, not to hunt for a
missing test. Before assuming a survivor means thin coverage, ask whether the framework or the
database already guarantees the behaviour.

**How to apply:** when a fix is *route this call site through the shared thing*, the fixture must
drive the **entry point**, not the shared thing. Then mutate the code back and confirm the suite
goes red — and check that the examples which fail are the ones you *meant* to fail. An example that
stays green under the mutation was never evidence for the fix, and if none of them go red, the
defect you described may not be the defect you have. Related: [[downstream-runs-beat-code-review]],
[[verify-in-the-environment-it-runs-in]], [[chase-an-off-by-a-constant-tally]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, proving-the-helper-is-not-proving-the-caller.md._

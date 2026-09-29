---
name: feedback-a-transcription-cannot-check-itself
description: When code transcribes a spec's constants, the test must hold the spec's literal numbers — asking the code moves the expectation with the bug.
type: feedback
---

`Cards::Geometry` transcribed §4.5's card layout (positions in mm, sizes in pt). The spec asserted
positions by reading those same constants — `be_within(3).of(Geometry::TEXT_X_MM * scale)` — so
**six mutations moving the geometry all survived**: the render moved and the expectation moved with
it.

**Why:** it looks like good practice (no magic numbers) and is the opposite here. The constant is
the thing under test. The same shape appeared twice more the same day: an example asserting a
setting inside the `around` hook that *sets* that setting, and a rule written in two places where
only the second copy was enforced.

**How to apply:** where code exists to transcribe an external authority — a spec table, a
protocol's field offsets, a wire format — put that authority's **literal numbers in the test**, with
a comment saying they are literal and why. Then mutate the transcription and confirm red.

**Two subtler traps from the same session:**
- *A coarser step passes a "multiple of" check.* Asserting a shrunk font size was a whole number of
  0.25 pt steps below 12.32 is also true of a 1.0 pt step. Assert the boundary instead: one step
  bigger must **not** fit.
- *Relative sampling.* Checking a box's centre and corner at coordinates derived from the box's own
  position lets the box move anywhere. Sample absolute coordinates.

**The sharpest case yet, 10 Sep 2026.** F-18 drew the ID card from §4.5's table. Four values were
wrong — the text anchored to the baseline where the template means the ascender line (every line
~4 mm high), a crop bias guessed at 0.1 instead of 0.08, a divider written as CMYK where the design
says use the RGB, and a flat bar where the design places a patterned asset. **All four agreed with
their own tests and the suite was green through every one**, because every example checked the
render against the table we had transcribed.

What broke the loop was **external artifacts**: the owner supplied two 300 dpi renders of real
cards plus the generator that made them. Those images are fixtures now — our render is compared
against them baseline by baseline. When a feature transcribes an external authority, ask whether
that authority can supply an ARTIFACT (a sample output, a golden file, a reference implementation)
rather than only numbers; a number you re-type is a number you cannot check, but an artifact you
did not make is.

Related: [[proving-the-helper-is-not-proving-the-caller]],
[[a-harness-that-cannot-see-a-broken-mutation]], [[a-number-two-sessions-agree-on-can-still-be-wrong]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-transcription-cannot-check-itself.md._

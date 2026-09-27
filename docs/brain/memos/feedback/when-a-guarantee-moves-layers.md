---
name: feedback-when-a-guarantee-moves-layers
description: Moving a guarantee from the model to the database leaves the old test green while proving nothing about the new mechanism.
type: feedback
---

I moved case-insensitive uniqueness out of a model validator and into a `lower(col)` unique index,
then wrote two examples for it — and RuboCop caught them as **byte-identical**. Both called
`valid?`, so both proved the validator and neither proved the index. Delete the index and both
still pass.

**Why:** the test kept asserting at the layer the guarantee just left. The behaviour is unchanged
from the outside, which is exactly what makes it invisible — the suite stays green through a change
that relocates the only thing enforcing it. Same shape as
[[proving-the-helper-is-not-proving-the-caller]], one layer lower.

**How to apply:** when a guarantee moves layers, write the example that **bypasses the old layer**,
and name the exception class exactly. Going around a validator with `save(validate: false)` also
skips `before_validation` callbacks — mine died on a NOT NULL violation on `public_id` and never
reached the index. It raised, so a loose `raise_error` would have been green while testing nothing
([[a-mutation-caught-by-the-wrong-fixture]]). In Postgres, wrap the expected violation in
`transaction(requires_new: true)` or it poisons the enclosing transaction
([[a-unique-violation-poisons-the-transaction]]).

And **pair every refusal example with a control that succeeds on the same input**. A test asserting
only a refusal passes just as well against a form that refuses everything — which is often the very
behaviour being removed ([[a-negative-assertion-its-fixture-never-reaches]]).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, when-a-guarantee-moves-layers.md._

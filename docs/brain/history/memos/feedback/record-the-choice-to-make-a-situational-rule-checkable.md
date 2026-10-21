---
name: feedback-record-the-choice-to-make-a-situational-rule-checkable
description: A situational rule can only gate everyone or nobody until the project records its choice; then the check gets a real not-applicable.
type: feedback
---

i18n and brand packs are both situational — most projects are monolingual, most use one pack — so
demanding the setup everywhere is the false positive that gets a rule ignored, and demanding nothing
lets a real multi-locale app ship silently monolingual.

**Recording the choice is what makes the rule checkable at all.** `config.x.brand.pack` (#788) and
`config.x.locales` (#799) give the check three honest states instead of two: conforming, drifted,
and *not applicable because this project declared otherwise*.

**Why:** without a declaration there are only two possible gates and both are wrong. A check that
cannot tell what a project chose has not measured anything, and guessing produces confident, wrong
remediation — #788's drift check compared every project against the fidara baseline and would have
reverted a measured WCAG palette.

**How to apply:** have setup ASK, and write the answer into config. Keep "undeclared" and "declared
minimal" as **different** answers with a fixture pinning it — `None` and `["en"]` mean "nobody
decided" and "we chose one", and collapsing them turns the not-applicable state back into a guess.
And do not infer the value from a nearby field: `default_variant` is not the pack slug.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, record-the-choice-to-make-a-situational-rule-checkable.md._

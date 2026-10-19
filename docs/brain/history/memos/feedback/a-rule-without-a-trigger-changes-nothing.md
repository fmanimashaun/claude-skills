---
name: feedback-a-rule-without-a-trigger-changes-nothing
description: Prose rules I wrote myself stopped none of my failures; every rule with a hook stopped me instantly.
type: feedback
---

In one day I hit five grep/regex failures — a repo-wide rename missed by a per-file grep, a probe
regex that matched nothing and was read as "no rows exist", an unquoted zsh glob, a rule's own
pattern too narrow, fixtures that never reached the code they guarded. **The prose rule for exactly
this already existed and I wrote it**: `unverified-negative` in `skills/code-review/SKILL.md`, whose
text says *"the same applies to 'no matches' — confirm the search actually ran over the intended
input."* It stopped none of them.

What stopped me, instantly and every time: `guard-claims.sh` (blocked a PR body with 8 unverified
claims), `duplicate-unreleased`, `claude-md-growth` (refused 263 lines twice), and
`changelog-bullet-unplaceable`. **Every rule with a mechanical trigger held. The one that was prose
did not.**

**Why:** the rule lives where it is *read* (a review skill, consulted when reviewing a diff), not
where it *fires* (typing a shell command mid-investigation). And an empty grep is usually correct, so
the rule asks for a control on every query to catch the rare broken one — which I skip exactly when
moving fast, which is when I typo.

**How to apply:** when a rule keeps being violated, do not sharpen its wording — that produces a
better sentence with the same zero triggers. Ask what *can* carry a trigger. Often the cause is
unmechanizable (no hook can tell a broken query from a true negative, because an empty result is a
valid answer), so **gate the consequence instead**: the moment that output becomes a durable claim
someone else reads. That is why `guard-claims.sh` grew `gh issue comment` rather than the skill
growing a paragraph.

Corollary for my own commands: prefer the tool that *throws*. `import x` fails loudly on a typo; a
regex with a typo returns `[]`. Use the parser for structural questions, not the pattern.

Related: [[a-negative-assertion-its-fixture-never-reaches]], [[gate-the-commit-on-the-check]],
[[a-count-of-a-string-is-not-a-count-of-the-thing]], [[a-true-result-about-the-wrong-file]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-rule-without-a-trigger-changes-nothing.md._

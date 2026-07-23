---
description: Institutionalize a lesson or decision as a docs/brain memo, indexed in MEMORY.md
argument-hint: <the lesson, correction, or decision to record>
---

# /rails-flow:brain — $ARGUMENTS

Turn the lesson above into permanent project memory.

1. Classify it: `feedback` (a correction — something an agent or human got wrong) or
   `decision` (a choice with alternatives and rationale).
2. Write `docs/brain/<type>_<kebab-slug>.md`:

```markdown
---
name: <type>-<slug>
description: <one line — the rule itself, stated imperatively>
type: <feedback|decision>
---

<The rule, stated plainly in 1-3 sentences.>

**Why:** <the concrete incident or tradeoff — PR numbers, what broke, what it cost.
Specific beats general; this is the part future agents believe.>

**How to apply:** <3-5 concrete bullets: the exact behaviors that follow from the rule.>
```

3. Add one line at the TOP of `docs/brain/MEMORY.md`:
   `- [<Title>](<file>.md) — <8-15 word summary>`
   (create the file if this is the first memo).
4. If the lesson contradicts CLAUDE.md or GUARDRAILS.md, update those too — memory and law
   must not disagree.

Confirm to the user: memo path, index line, and any doc updates made.

**Provenance:** where a memo cites evidence, tag it `[observed]` / `[decided]` / `[assumed]` /
`[reported]` (per the `docs/brain/README.md` convention) so its weight is legible later.
Related: `/rails-flow:brain-review` (weekly maintenance sweep) keeps these honest;
`/rails-flow:brain-sync` publishes cross-project state to a shared brain repo.

---
description: Turn an idea or a brief into a technical spec before anything is built — read what exists, grill only the gaps one question at a time, write terms and decisions down as they settle, and save docs/product/specs/<slug>.md for /rails-flow:feature to plan from.
argument-hint: "[the idea in a sentence | a brief section | an issue number]"
---

# /rails-flow:spec — $ARGUMENTS

`/rails-flow:brief` writes the **product** brief: what, for whom, scope and journeys.
`/rails-flow:feature` builds one slice. Between them, nothing wrote the **technical** spec: the
model, the interfaces, where it will be tested, and what was decided and why. So the plan lived
inside a session, and it left with the session. This command writes it down before any code, so a
fresh session, a second agent or a person can build from the document instead of the conversation.

Adapted from mattpocock/skills `grill-with-docs`, `to-spec` and `domain-modeling`, on the owner's
decision recorded on #1375.

## The rule that shapes everything else

> **Read before you ask. Ask one question at a time. Write it down the moment it settles.**

A question the repo already answers destroys trust in the whole interview. A wall of ten questions
gets one lazy answer. A decision reconstructed at the end has lost its reason.

## Run

**1. Read first.** `docs/brain/BRIEF.md` if it exists; the issue, if `$ARGUMENTS` names one
(`gh issue view <n> --comments`: the comments hold the corrections); `docs/brain/DECISIONS.md`;
the project's glossary (wherever `CONTEXT.md` or `docs/**/glossary*` lives); and the code the idea
touches: routes, models, `db/schema.rb`, and the specs around them. Tag what you inferred from code
`[inferred]`, so the owner can correct it.

**2. Show what is already known, and stop.** One short list: what the sources answer, each with its
citation, and the gaps. The owner can point at a document instead of answering, which is why this
comes before any question.

**3. Grill the gaps, one question at a time.** This part is advice, not enforcement: it leaves no
trace in the artifact, so nothing mechanical can check it.
- **Every question carries your recommendation and its reason**, so the owner can accept a default:
  *"I'd make it a dropdown, not a page, because the count is the whole point. Accept, or does it
  need filters?"*
- **Challenge the language.** When a term conflicts with the glossary, say so at once: *"the
  glossary defines a Return as X, but you seem to mean Y. Which is it?"* When a term is fuzzy,
  propose a precise one.
- **Stress-test with a concrete scenario** at the boundary: *"a reviewer is on leave when the
  return arrives. Who is notified?"*
- **Check the code against what you are told.** When they disagree, surface it: *"the code cancels
  whole orders, but you just said partial cancellation is possible."*
- **Agree the test seam before any code**: the highest point the behaviour can be tested at,
  preferring one that already exists. Fewer seams are better; one is ideal.
- **Stop when the first slice is buildable**, not when the spec is exhaustive. Record the rest as
  open questions with owners.

**4. Write terms and decisions as they settle, not in a batch.**
- A resolved term goes into the project glossary at once: one or two sentences saying what it IS,
  with the words to avoid. Only terms specific to this project, never general programming terms.
- A decision goes to `docs/brain/DECISIONS.md` as the next `D-nnn`, with the alternative and its
  reason, **only when all three hold**: it is hard to reverse, it would surprise a reader without
  context, and it was a real trade-off. Otherwise it is a line in the spec, not a decision record.

**5. Write `docs/product/specs/<slug>.md`.** The headings are a contract (`check_spec.py`):

```markdown
# Spec — <feature>

## Problem
The problem from the user's side, in their words where you have them (a blockquote).

## Solution
The solution from the user's side, in a paragraph.

## Sources
- `docs/brain/BRIEF.md` § "Journeys"
- `app/models/notification.rb` § "class Notification"

## Terms
- **Notification**: one event a user is told about. _Avoid_: alert, message.

## User stories
1. As a reviewer, I want unread notifications in the header, so that I act on a return the same day.

## Implementation decisions
- Modules, their interfaces, schema changes, contracts, and the interactions between them.
  Never a file path: it goes stale in a week. A prototype's schema or state machine may go in a
  fenced block when it says a decision more precisely than prose.

## Testing decisions
- Seam: a system spec driving the header dropdown as a signed-in reviewer.
- What a good test asserts here (behaviour, not implementation), and the prior art to copy.

## Out of scope
- What this is NOT, each with why.

## Open questions
- The question. owner: <who answers it>

## Decisions
- D-004 — the choice, the alternative, and what would make us revisit it.
```

**6. Verify. This gate does not get skipped.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_spec.py" "docs/product/specs/<slug>.md" \
  --decisions docs/brain/DECISIONS.md
```

Exit `0` clean · `1` findings · `2` not a spec. It refuses:
- a Sources section citing nothing, and a citation or `D-nnn` that resolves to nothing;
- a story not in "As a …, I want …, so that …" form;
- a file path in Implementation decisions;
- Testing decisions with no `Seam:` line;
- an Out of scope of only "none", and an open question with no owner.

On findings, fix the spec, never the check.

**7. Commit** the spec, the glossary and `docs/brain/DECISIONS.md` by name. Never `git add -A`.

## What happens next

`/rails-flow:slice` breaks the spec into dependency-ordered vertical slices and files one issue per
slice, so the work proceeds in order (#1369). The spec's stories become each slice's acceptance criteria in `docs/product/acceptance/<slug>.md`,
and `/rails-flow:feature` plans from the spec rather than from the conversation. If the spec changes
what a user sees, the mock-up gate in `/rails-flow:feature` Phase 1 applies before any code (#1376).
At merge, `spec-reviewer` checks the diff against the criteria text (#1370).

## Report

What the sources already answered (count, with citations), which gaps were grilled, the terms and
`D-nnn` ids written, the questions left open and their owners, and the `check_spec.py` result.

---
description: Turn a vague ask into something buildable — ingest whatever documents or code already exist, interview only the genuine gaps, and write docs/brain/BRIEF.md as an index over the sources rather than a copy of them.
argument-hint: "[the idea in a sentence | a path to a PRD or notes | blank to detect]"
---

# /rails-flow:brief — $ARGUMENTS

`/rails-flow:setup-flow` scaffolds a project's conventions. `/rails-flow:feature` builds a thing
you can already describe. Neither turns **"we need a site for X"** into something buildable, so
today that conversion happens in chat: the requirements are never written down, the reasons behind
them are reconstructed after the fact, and on a fresh session the original intent is gone.

That bites hardest on **client work**, where the ask arrives as a sentence and the money depends on
what "done" means. This command is the front door for those engagements — run it **before**
`/rails-flow:setup-flow`.

## The one rule that shapes everything else

> **The brief is an index over your sources, never a copy of them.**

If a PRD exists, it stays authoritative. Copying it into `BRIEF.md` produces two documents that
will disagree within a week with no rule saying which wins — the exact doc-drift this toolchain
exists to prevent, and the copy reads *better* than the index right up until it rots.

So in document mode the brief is deliberately **thin**: a coverage map that links into the sources,
plus only what they lack — the gaps that intake resolved, the decisions taken, and the questions
still open. That is enforced, not requested: `check_brief.py` reads every cited source and reports
a brief that reproduces one.

**Distilling documents into project-local skills is `/rails-flow:curate`'s job.** Intake indexes;
curate distils. Do not do curate's work here.

## Three entry modes — interview LAST, not first

Most projects are not greenfield. Detect the situation before asking anything:

| Mode | When | What you do |
|---|---|---|
| **A — documents** | a PRD, spec or notes exist (`docs/**.md`, or a path in `$ARGUMENTS`) | **Ingest first.** Extract what they already answer, show the extraction for correction, then interview only the genuine gaps. |
| **B — codebase** | code exists but little written intent | Read routes, models, schema and specs. State what you **inferred** so it can be corrected. Interview the gaps. |
| **C — greenfield** | an idea and nothing else | Full interview. |

**Mode A is the common case and the one to get right.** A detailed PRD must not trigger an
interrogation about things it already covers; that is the fastest way to make the tool feel stupid
and get abandoned.

## The coverage map, and how a source is cited

Before asking a single question, report where each brief section stands. Four states:

| State | Means | Must carry |
|---|---|---|
| `answered` | a source already decides it | a source reference (below) |
| `decided` | intake decided it, and the reason is recorded | a `D-nnn` id from `docs/brain/DECISIONS.md` |
| `thin` | a source touches it but is not decidable | the reference, and why it is not enough |
| `missing` | nobody has it | a matching open question |

A **source reference** is a real path plus a string that literally occurs in that file:

```text
`docs/prd.md` § "Pricing tiers"
`app/models/booking.rb` § "class Booking"
```

The checker opens the file and looks for the locator, so a reference that resolves to nothing is a
finding. That matters more than it sounds: **an id that resolves to nothing is worse than no
citation, because it reads as traceable.** The same syntax carries code, which is what lets Mode B
cite what it inferred instead of asserting it.

`#130` asked for `PRD S7.2`-style references "matching the citation convention already used in
`docs/brain/`". There is no such convention — the brain uses `D-nnn` ids and the provenance tags —
and `PRD S7.2` names no file, so it could never resolve. This syntax is ours, decided on
[#130](https://github.com/fmanimashaun/claude-skills/issues/130#issuecomment-5152551963).

## Interview discipline

**This section is advice, not enforcement.** It is behaviour during the conversation, and it leaves
no trace in the artifact, so nothing mechanical can check it — per
[`docs/doctrine/harness-doctrine.md`](../../../docs/doctrine/harness-doctrine.md) §1, that makes it tier 1 and it is
labelled as tier 1 rather than left to look like a guarantee.

- **One question at a time.** Ten questions in a wall get one lazy answer; one question gets a
  considered one.
- **Every question carries a recommendation and its reason**, so the user can accept a default
  rather than invent an answer: *"I'd default to email+password over OAuth here because the
  audience is internal staff — accept, or do they need Google sign-in?"*
- **Never ask what the repo or the documents already answer.** One such question destroys trust in
  the whole interview.
- **Stop when the first slice is decidable, not when the brief is exhaustive.** Record what is
  still open; do not force it. The goal is enough to plan a slice, not a specification.

## The shape (the headings are a contract)

`check_brief.py` requires all ten `##` sections. Write `docs/brain/BRIEF.md`:

```markdown
# Product brief — <project>

## Coverage map

**Mode: A — documents.** Read `docs/prd.md`; interviewed the gaps below.

| Brief section | State | Source |
|---|---|---|
| What and for whom | answered | `docs/prd.md` § "Who this is for" |
| Problem | answered | `docs/prd.md` § "The problem" |
| Scope | thin | `docs/prd.md` § "Milestones" — three nouns, not a boundary |
| Non-goals | decided | D-016 |
| Constraints | decided | D-014 |
| Journeys | decided | D-015 |
| Success | answered | `docs/prd.md` § "What good looks like" |

## What and for whom
One paragraph, or a reference. Do not restate a source that already says it.

## Problem
The problem in the user's own words, as a blockquote — quotation is the one place borrowing is
right, and the checker exempts blockquotes for exactly that reason.

## Scope
The first slice, as a boundary someone can hold a diff against.

## Non-goals
- What this is NOT, each with why. "None" is rejected: non-goals are what stop
  "add a booking form" becoming a CRM mid-build, so an empty list is scope creep with a heading.

## Constraints
Stack, budget, deadline, compliance. Anything that is already decided for you.

## Journeys
The primary user journeys, in the order they matter.

## Success
What changes for the user when this works. Direction, not acceptance criteria —
`docs/product/acceptance/<slug>.md` is where those become falsifiable.

## Open questions
- The question. owner: <who answers it>

## Decisions
- D-014 — the choice, the alternative, and what would make us revisit it.
```

Each decision taken during intake goes to `docs/brain/DECISIONS.md` as a `D-nnn` **with its
rationale, at the time** — the whole point is that reasoning is captured while it is still true,
not reconstructed later. The brief cites the id; the rationale lives once.

## Run

**1. Detect the mode.** `$ARGUMENTS` naming a path is Mode A. Otherwise look for `docs/**.md`
(excluding `docs/brain/` and `docs/reviews/`); then for `app/`, `config/routes.rb`, `db/schema.rb`.
Say which mode you chose and why, before doing anything else.

**2. Ingest.** Mode A: read the documents and extract what they answer. Mode B: read routes,
models, schema and specs, and tag every inference `[inferred]` so the human can correct it — the
brain's provenance vocabulary (`[observed] [decided] [assumed] [reported]`) applies here too.
Mode C: skip to 4.

**3. Show the extraction for correction.** Present the coverage map and *stop*. The human can point
at a document instead of answering, which is the whole reason the map comes first.

**4. Interview the gaps only**, under the discipline above.

**5. Write `docs/brain/BRIEF.md`** and append any new `D-nnn` to `docs/brain/DECISIONS.md`.

**6. Verify — this gate does not get skipped.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_brief.py" docs/brain/BRIEF.md \
  --decisions docs/brain/DECISIONS.md
```

Exit `0` clean · `1` findings · `2` unusable (no file, or not a brief). On findings, fix the brief.
Never soften the check: an under-specified brief does not fail loudly, it produces a confidently
built product nobody asked for.

What the checker cannot do: judge whether the questions were good, whether one was asked at a time,
or whether you stopped at the right point. It checks that every citation resolves, that no source
is duplicated, that gaps are recorded rather than dropped, and that nothing points at a
conversation. The judgement stays yours.

**7. Commit** `docs/brain/BRIEF.md` and `docs/brain/DECISIONS.md` by name. Never `git add -A`.

## What happens next

The brief feeds the phase plan, and its non-goals are load-bearing there: they are what a scope
question gets measured against mid-build. Then `/rails-flow:setup-flow` to scaffold the project,
`/rails-flow:curate` to turn the source documents into project-local skills, and
`/rails-flow:feature` for the first slice — whose `docs/product/acceptance/<slug>.md` is where "what
success looks like" finally becomes falsifiable.

## Report

The mode and why, what the sources already answered (as counts by state), which gaps were
interviewed, which were left open and to whom, the `D-nnn` ids written, and the `check_brief.py`
result. If you skipped a question because a document answered it, say which document — that is the
evidence the interview was not busywork.

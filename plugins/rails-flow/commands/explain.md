---
description: Explain the built system back to its human owner — plain-language docs/GUIDE.md with mermaid diagrams, section-scoped and idempotent. Also explains a PLAN before the build, so a wrong plan is rejected before it costs a build cycle.
argument-hint: "[blank for all | <area> | plan]"
---

# /rails-flow:explain — $ARGUMENTS

Everything else this toolchain writes is aimed at an agent: CLAUDE.md, GUARDRAILS.md, the
skills, `docs/brain`, the acceptance criteria. This is the one artefact aimed at the **human
who owns the product**.

That direction matters more as the flow gets better, not less. Agents now produce more code
per day than the owner can read, so the bottleneck moves from writing to **understanding** —
and an owner who cannot understand their own system either becomes the blocker on every
decision or hands their judgement to the agent. `/rails-flow:curate` runs the other way
(human docs → agent skills). Nothing ran this way until now.

## What the guide holds — and what it must never duplicate

`docs/GUIDE.md` is committed and human-facing. It is **deliberately thin**, because the two
things it could pad itself with are already owned elsewhere and are better there:

| Question | Lives in | Why not in the guide |
|---|---|---|
| What calls what, exhaustively | `docs/architecture/graph.md` + `graph.json` | Generated and digest-guarded by `/rails-flow:graph` — it **cannot** rot. Hand-copied structure can, and does. |
| What we decided and why | `docs/brain/DECISIONS.md` (`D-nnn`) | One decision, one home. Two prose accounts of one decision will disagree, and nothing says which wins. |
| What "done" means | `docs/product/acceptance/<slug>.md` | The criteria grade the work; the guide teaches the owner to check it. |
| **What it all means, in plain language** | **the guide** | Nothing else carries it. A call graph cannot say what a word means in this business. |

So the guide **links** — `see D-004`, "the full graph is in `docs/architecture/graph.md`" —
and spends its own words only on what neither can express. Three consequences:

- **No class names as explanation.** "It uses a Service Object" explains nothing; say what it
  buys and what it costs. Write for an intelligent non-specialist, not for a junior Rails dev.
- **Decisions are stated as trade-offs, not conclusions.** "We bill on completion (D-004) —
  that costs us upfront cash flow and buys never refunding a no-show." A conclusion without its
  cost cannot be re-examined later, which is the whole reason the owner is reading.
- **Bounded on purpose.** 37signals shipped a 166-line `AGENTS.md` and cut it to 70 by deleting
  four claims that had drifted into being false ([fizzy #2999][f-2999], 2026-07-28 — the
  reasoning behind the same cap in `setup-flow` §2). A hand-written overview that drifts does
  not merely go stale, it actively misleads. Keep each area to what stays true for months.

[f-2999]: https://github.com/basecamp/fizzy/pull/2999

## File shape (and why the markers are load-bearing)

The guide follows the same **idempotency contract** as `CLAUDE.md` (see
`/rails-flow:setup-flow`): rails-flow owns only what sits between its markers, and the owner's
own prose outside them is never rewritten. One marked block per area is what makes
`/rails-flow:explain billing` rewrite billing **and nothing else**:

```markdown
# <Product> — a guide for whoever owns this

<!-- rails-flow:begin guide:overview -->
## What this is
<2-3 paragraphs: what the product does, for whom, and the two or three rules that hold
system-wide — "an appointment can only be billed once it is finished".>
<!-- rails-flow:end guide:overview -->

<!-- rails-flow:begin guide:area:billing -->
### Billing

#### What it does
<plain language, no class names>

#### How it flows
<one mermaid diagram — see below — plus 2-4 sentences it cannot express>

#### Check it yourself
1. Run `bin/rails runner 'puts Invoice.draft.count'` and note the number.
2. Open /appointments, mark one finished; the number goes up by one.
<!-- rails-flow:end guide:area:billing -->

<!-- rails-flow:begin guide:decisions -->
## Why it is built this way
<each decision as a trade-off, citing its D-nnn>
<!-- rails-flow:end guide:decisions -->
```

The three `####` headings are a **contract, not a suggestion** — `check_guide.py` requires all
three per area. Two of the three is a tour, not an explanation, and the one that gets dropped
under time pressure is always *Check it yourself*, which is the only part that gives the owner
independence.

**"Check it yourself" is the human-runnable form of the acceptance criteria** — the same
observables as `docs/product/acceptance/<slug>.md`, expressed as something the owner can do without an
agent. Every step names a command, a route or a path; a step that says "confirm billing works"
is a reassurance, and the checker rejects it for the same reason `check_criteria.py` rejects
that phrasing in a criterion.

## Diagrams: mermaid only, and the traps are documented

GitHub renders mermaid where the code lives — *"Diagram rendering is available in GitHub Issues,
GitHub Discussions, pull requests, wikis, and Markdown files"* ([GitHub docs][gh-diagrams]),
gists included ([changelog][gh-gists]). That is why the guide gets diagrams at all: they render
for the owner in the browser, they diff as text, and an agent can read them.

Use the smallest set that covers what prose does badly:

| Shape | Type |
|---|---|
| Request flow, job topology, deploy path | `flowchart LR` |
| Model relationships | `erDiagram` |
| The state machine of a multi-step process | `stateDiagram-v2` |
| A conversation between parts (controller → job → mailer) | `sequenceDiagram` |

**Five rules, each because it silently produces an error box instead of a picture:**

1. **Quote every label.** *"It is possible to put text within quotes in order to render more
   troublesome characters"* ([mermaid][mm-flow]). `n1["Invoice (draft)"]` renders;
   `n1[Invoice (draft)]` kills the whole diagram, because `)` ends the shape.
2. **Never use a bare lowercase `end`.** *"Typing 'end' in all lowercase letters will break the
   Flowchart"* ([mermaid][mm-flow]). It is legal **only** as the closer of an open `subgraph`.
   Capitalize it (`End`) or put it inside a quoted label.
3. **No `%%{init: ...}%%`.** *"Directives are deprecated from v10.5.0"*
   ([mermaid][mm-directives]). Diagrams here must render under default config.
4. **No `---` frontmatter inside the block.** It is mermaid's replacement for directives, but
   GitHub neither documents supporting it nor publishes which mermaid version it ships — so it
   may render nothing. Put the title in a markdown heading above the block instead.
5. **Stay on the four types above.** Same reason: the bundled version is unpublished (GitHub's
   docs offer a self-check — render a block containing `info` — and never state the number), so
   a diagram type added upstream recently can render nothing. `check_guide.py` holds the
   allowlist; if you verify a new type renders, add it there with the date.

Two things deliberately **not** claimed, because checking them said otherwise:

- **`graph` is not deprecated.** *"Instead of `flowchart` one can also use `graph`"*
  ([mermaid][mm-flow]) — no deprecation notice anywhere. Prefer `flowchart` because
  `architecture_graph.py` and this repo's README already use it, which is a house convention and
  nothing stronger. Both pass the checker.
- **GitHub documents no size cap**, and nothing about what triggers "Unable to render rich
  display". The 60-node cap in `architecture_graph.py` is **our** choice, not an upstream limit —
  do not repeat it as one. For the guide the real cap is human: a diagram nobody can hold in
  their head has failed even if it renders. Keep it to roughly a dozen nodes and link
  `docs/architecture/graph.md` for the exhaustive view.

If `stateDiagram-v2` does not render, try `stateDiagram` — mermaid's own page documents an
older renderer, and which spelling a given version prefers is not something to guess at.

[gh-diagrams]: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams
[gh-gists]: https://github.blog/changelog/2022-02-28-gists-now-support-mermaid-diagrams/
[mm-flow]: https://mermaid.js.org/syntax/flowchart.html
[mm-directives]: https://mermaid.js.org/config/directives.html

## Run

**1. Scope it.** Blank → every area. `<area>` → that area's block only. `plan` → see below.

**2. Gather, and do not guess.** Read `docs/architecture/graph.json` (its `flows` are already
the named, ordered paths a human wants — do not re-derive them by reading controllers),
`docs/brain/DECISIONS.md`, `docs/brain/STATUS.md`, and the acceptance criteria for the area.
Delegate any wide code reading to a subagent so raw files stay out of context. If
`graph.json` is missing, say so and offer `/rails-flow:graph` — the guide is much weaker
without it, and inventing structure from a partial read is how a guide starts lying.

**3. Write, inside the markers only.** Replace the body of each targeted block; leave every
other byte alone, including any prose the owner added outside the markers.

**4. Verify — this gate does not get skipped.**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_guide.py" docs/GUIDE.md --decisions docs/brain/DECISIONS.md
```

Exit `0` clean · `1` findings · `2` unusable (no file, or markers so broken a re-run is unsafe).
On findings, fix the guide. Never soften the check: **a diagram that does not render is worse
than no diagram**, because the owner sees an error box and concludes the system is broken.

What the checker cannot do, and does not claim to: it cannot tell whether the prose is **true**
or any good. It checks the markers, the coverage, and the documented mermaid traps. The only
proof a diagram renders is opening the file on GitHub — do that once after the first run, and
say in your report that you did.

**5. Commit** `docs/GUIDE.md` by name. Never `git add -A`.

## Plan mode — `/rails-flow:explain plan`

Explain the *plan* like the owner has never seen the codebase: what you are about to build, the
order, what it will and will not do, and the one or two decisions that would be expensive to
reverse. Rejecting a wrong plan here costs a paragraph; rejecting the result costs a build cycle.

**Plan mode never writes to `docs/GUIDE.md`.** It renders the explanation in the conversation
for a go/no-go. The guide describes a system that exists; a planned area written into it is an
aspiration presented as fact, which is exactly what `doc-updater` is forbidden to do. Once the
work lands, a normal `/rails-flow:explain <area>` writes the section — from what was built,
which is often not quite what was planned.

## Keeping it true

`doc-updater` re-runs the affected area at session end when behaviour the guide describes has
changed, so the guide moves with the code instead of decaying between deliberate passes. It is
the same division of labour as everywhere else in this flow: the **generated** artefacts
(`graph.json`, `graph.md`) cannot rot, the guide's prose can, so the guide is bounded, dated,
and re-checked rather than trusted.

## Report

Sections written or updated (by slug), diagrams added by type, what you linked rather than
restated, the `check_guide.py` result, and whether you confirmed the diagrams render on GitHub.
If an area was skipped because `graph.json` had nothing for it, say which and why — a guide with
a silently missing area reads as a complete guide.

# Agent-instruction conventions — 37signals vs the rails-flow scaffold

This is the decision record behind how `/rails-flow:setup-flow` briefs coding agents — what it
scaffolds, what it deliberately does not, and why. It is **Phase D of EPIC #96** (`Refs #100`): the
same "read the people who make Rails, then decide deliberately" method the rest of the epic applied to
Rails *code*, applied here to how they brief *agents*.

**Source and attribution.** 37signals ship agent instructions inside their production Rails apps. We
compare against two, read directly from source on **2026-07-31 (`main`)**:

- [basecamp/fizzy][fizzy] — Kanban, licensed "O'Saasy" (MIT + a no-competing-hosted-SaaS clause):
  [`AGENTS.md`][f-agents], [`STYLE.md`][f-style], [`.claude/CLAUDE.md`][f-claude],
  [`saas/AGENTS.md`][f-saas].
- [basecamp/writebook][writebook] — book publishing, **MIT**: [`AGENTS.md`][w-agents],
  [`.claude/CLAUDE.md`][w-claude].

Both licences permit quoting and adapting; **attribute 37signals** wherever a pattern is lifted. Every
adopt / adapt / reject decision below is recorded with its reason, because inheriting someone else's
agent-briefing shape silently is how a scaffold ends up carrying conventions it never chose.

The other authority here is **Claude Code's own memory documentation** — because Phase D is about how
*our* generated files are read by *our* tool, and that behaviour is externally verifiable. It is cited
as [claude-md][ccmem] throughout.

[fizzy]: https://github.com/basecamp/fizzy
[f-agents]: https://github.com/basecamp/fizzy/blob/main/AGENTS.md
[f-style]: https://github.com/basecamp/fizzy/blob/main/STYLE.md
[f-claude]: https://github.com/basecamp/fizzy/blob/main/.claude/CLAUDE.md
[f-saas]: https://github.com/basecamp/fizzy/blob/main/saas/AGENTS.md
[writebook]: https://github.com/basecamp/writebook
[w-agents]: https://github.com/basecamp/writebook/blob/main/AGENTS.md
[w-claude]: https://github.com/basecamp/writebook/blob/main/.claude/CLAUDE.md
[f-2999]: https://github.com/basecamp/fizzy/pull/2999
[ccmem]: https://code.claude.com/docs/en/memory

---

## The framing decision: we are Claude-native (ours)

This has **no upstream** — it is our own decision, recorded on **#159** (declined as *not planned*): the
flow ships for Claude Code only, no Cursor / Codex / Copilot adapters. It sets the whole comparison,
because 37signals' shape is built for the opposite constraint. Their split exists to feed **many**
tools from **one** source of truth: [`AGENTS.md`][f-agents] is the tool-neutral canonical file, and
[`.claude/CLAUDE.md`][f-claude] is a single line —

> `@../AGENTS.md`

— so Claude Code reads the same file every other agent does. writebook does the identical thing:
[its `.claude/CLAUDE.md`][w-claude] is also just `@../AGENTS.md`. That indirection is the *point* of a
neutral AGENTS.md; it is not decoration.

Because we chose Claude-native, **`CLAUDE.md` is already our native canonical file** and the indirection
buys us nothing on a greenfield repo — Claude Code reads `CLAUDE.md` directly ([claude-md][ccmem]:
*"Claude Code reads `CLAUDE.md`, not `AGENTS.md`"*). So most of what follows is not "adopt their file
layout" but "adopt the *discipline* their layout encodes, using the Claude-native mechanism for it."
Twice, that mechanism turns out to be one 37signals' tool-neutral shape can't assume — path-scoped
`.claude/rules/` — which is where we are genuinely ahead, not behind.

## How the two shapes line up

| Their concern | 37signals mechanism | Our scaffold today | Decision |
|---|---|---|---|
| One source of truth across tools | `AGENTS.md` + `.claude/CLAUDE.md` → `@../AGENTS.md` | `CLAUDE.md`, sole entry, marker-wrapped | **A — adopt the import, only when an AGENTS.md already exists** |
| How code should read | separate [`STYLE.md`][f-style], AGENTS.md says *"read STYLE.md"* | `skills/rails-8/references/style.md` (Phase A) + Project Overrides | **B — point at the skill; never copy a STYLE.md; offer a path-scoped rule** |
| Orient an agent to the domain | AGENTS.md "Architecture Overview" prose | Patterns (code shapes) + `docs/architecture/graph.json` | **C — adopt a short, non-derivable overview** |
| Mode / area-specific instructions | conditional [`saas/AGENTS.md`][f-saas] | none | **D — reject by default; document `.claude/rules/` for it** |
| Test / controller micro-conventions | [writebook `AGENTS.md`][w-agents] | rails-8 skill doctrine | **E — noted, not scaffold material (and mostly Minitest)** |
| Local-dev tooling ("Chrome MCP") | *asserted by #100/#96* | qa-flow wires Playwright MCP | **F — absent from source; recorded, not scaffolded** |

---

## A. Coexist with an existing `AGENTS.md` by importing it (ADOPTED)

fizzy and writebook both make Claude Code read their canonical `AGENTS.md` through a one-line
[`.claude/CLAUDE.md`][f-claude] import. Claude Code's docs prescribe this exact move:

> *"Claude Code reads `CLAUDE.md`, not `AGENTS.md`. If your repository already uses `AGENTS.md` for
> other coding agents, create a `CLAUDE.md` that imports it so both tools read the same instructions
> without duplicating them."* — [claude-md][ccmem]

with the documented shape:

```markdown
@AGENTS.md

## Claude Code
<Claude-specific instructions below the import>
```

**Our gap.** The scaffold assumed a greenfield repo and created `CLAUDE.md` as the *sole* entry point.
It only ever mentioned `AGENTS.md` defensively (setup-flow §5 knowledge-graph: *"Never gitignore an
authored AGENTS.md"*). But Rails 8 apps — and anything derived from a 37signals template — increasingly
**ship an `AGENTS.md` already**. Scaffolding a second orientation file next to it produces exactly the
two-entry-point drift Claude Code warns about: *"if two rules contradict each other, Claude may pick
one arbitrarily."*

**ADOPTED**, scoped to the case that warrants it. When setup-flow detects an existing `AGENTS.md`, it
keeps **one** source of truth: `CLAUDE.md` opens with `@AGENTS.md`, and the rails-flow-managed sections
(still marker-wrapped) go *below* the import — Claude loads the imported file first, then appends ours
([claude-md][ccmem]). We do **not** generate an `AGENTS.md` where none exists (Claude-native, #159):
`CLAUDE.md` is the native file. The import is a coexistence tool, not a default layout.

- **Distinct from agent routing.** setup-flow's "See Also" line *"AGENTS routing → the rails-flow
  plugin agents"* is about the plugin's subagents, not an `AGENTS.md` file. Keep the two senses apart.
- **Context cost is real and worth stating.** An `@`-import *"still load[s] and enter[s] the context
  window at launch"* ([claude-md][ccmem]); it organises, it does not save tokens. Folding a thin or
  stale `AGENTS.md` into `CLAUDE.md`'s marked sections is the better move when the file isn't earning
  its keep — the import is for a live, other-tool-owned `AGENTS.md`.

## B. A separate STYLE.md — point at the skill, never copy (ADAPTED)

fizzy keeps [`STYLE.md`][f-style] separate and its [`AGENTS.md`][f-agents] ends with *"Before editing
or reviewing code, read STYLE.md."* The question #100 poses is whether we should scaffold a per-project
`STYLE.md` too.

**No — and the reason is that we already did it once, better.** Phase A extracted fizzy's `STYLE.md`
into `skills/rails-8/references/style.md`: shipped doctrine, version-pinned, every rule quoted and
cited, available in **every** rails-flow project (the scaffold already presumes the rails-8 skill —
setup-flow §1 measures deviations *"from the rails-8 skill's vanilla doctrine"*). A per-project
`STYLE.md` would either copy that skill — duplicating shipped doctrine and inviting drift, and directly
violating the acceptance criterion *"generated from Phase A's decisions, not copied"* — or hold only
project-specific deviations, which **already have a home**: the Project Overrides section.

So what we adopt is fizzy's *discipline*, not its file:

- **The pointer.** The generated `CLAUDE.md` now tells agents to read the rails-8 skill's style
  reference before writing Ruby — the Claude-native equivalent of *"read STYLE.md"*, aimed at the
  Phase-A source rather than a copy.
- **The Claude-native mechanism for a genuine per-project style file**, if one is ever warranted, is a
  **path-scoped rule** — `.claude/rules/style.md` with `paths: ["**/*.rb"]` — which *"only apply when
  Claude is working with files matching the specified patterns"* ([claude-md][ccmem]). That beats a
  root `STYLE.md`, which loads its full weight **every session** ([claude-md][ccmem]: CLAUDE.md and
  its imports *"load at launch"*), for content that only matters while editing Ruby. This is the
  "we may be ahead" case #100 anticipated: 37signals' tool-neutral split can't assume this mechanism;
  Claude Code has it.

## C. A short, non-derivable Architecture Overview (ADOPTED)

fizzy's [`AGENTS.md`][f-agents] leads with an **Architecture Overview**: URL-based multi-tenancy via an
`AccountSlug::Extractor` middleware, the passwordless-identity auth model, the "entropy" auto-postpone
system, UUIDv7 base36 primary keys, Solid Queue jobs that capture `Current.account`, sharded full-text
search. None of that is *"it uses a Service Object"* boilerplate — it is the set of non-obvious,
cross-cutting mechanisms an agent must know before touching anything, and it is the single most useful
part of their file.

**Our gap.** The scaffold had two structural aids and neither carries this. `Patterns` gives *code
shapes to copy*; `docs/architecture/graph.json` gives *exhaustive structure* (what calls what). Neither
tells an agent what "entropy" **means** here, or that every query is tenant-scoped, or that a PK is a
25-char string — the conceptual layer a call graph cannot express.

**ADOPTED** as a short `## Architecture Overview` section in the generated `CLAUDE.md`, with one hard
constraint that makes it earn its context budget: it holds **only the non-obvious, non-derivable**
mechanisms and domain vocabulary — never a directory tour. That constraint is doctrine, not taste:
Claude Code's `/doctor` *"cuts content Claude can derive from the codebase, such as directory layouts,
dependency lists, and architecture overviews, and keeps pitfalls, rationale, and conventions that
differ from tool defaults"* ([claude-md][ccmem]). A generic overview gets trimmed; the fizzy-shaped one
— tenancy model, entropy, UUID PKs — is exactly the "conventions that differ from defaults" it keeps.
It **points to** the graph for structure, so Patterns and the graph are preserved, not diluted.

**The upstream file's own history is the strongest argument for that constraint, and it is three days
old.** On **2026-07-28**, fizzy shipped *"Fix wrong login, search, and tenancy claims in AGENTS.md"*
([#2999][f-2999]) — 37signals correcting **their own agent instructions** against **their own code**:

| Wrong claim | Reality |
|---|---|
| the login code appears in the browser/Rails console | in development it renders inline on the page |
| search is "16-shard CRC32" | MySQL-only; SQLite is a single FTS5 index |
| *"All models include `account_id`"* | `Identity` and `Session` are **global** exceptions |
| deploy destinations `beta2`–`beta4` | only `beta1` exists |

and the file went from **166 lines to 70**. Three things follow, and all three are load-bearing here:

1. **A hand-written overview drifts, and when it drifts it actively misleads** — the PR's own reasoning
   for the search fix is that documenting the sharded shape universally would have agents *reasoning
   about code paths that do not exist*. That is worse than an absent section.
2. **So the cap is not stylistic.** They arrived at ~70 lines by deleting; we start there by rule.
3. **It vindicates the division of labour we already had.** Structure comes from
   `docs/architecture/graph.json`, which is **generated and CI-drift-guarded** (setup-flow §8) — it
   cannot rot the way prose does. Only the genuinely non-derivable concepts are hand-written, which is
   the smallest possible surface for exactly this failure. Two of their four wrong claims (`account_id`
   everywhere, the deploy destinations) are the kind a generated artefact or a live command would never
   get wrong.

Worth stating plainly for anyone reading their `AGENTS.md` as gospel: the version quoted throughout this
document is the **corrected** one (72 lines as fetched, post-#2999). Its *"global identity, session, and
authentication records are exceptions"* and *"Don't assume the sharded shape when working under SQLite"*
sentences **are** those fixes.

## D. Mode / area-specific instructions → `.claude/rules/`, not a default (REJECTED as default)

fizzy conditionally loads [`saas/AGENTS.md`][f-saas]: its root `AGENTS.md` says *"When present, read
`saas/AGENTS.md` before continuing. Otherwise, do not apply its instructions."* — a second instruction
layer that only applies in SaaS mode.

**REJECTED as a default scaffold element.** It solves a problem — one codebase, two deploy identities
(OSS vs hosted) — that almost no project has, and adding it by default is machinery for a rare case.
But the *need* it represents (instructions that apply only to part of a codebase, or only in a mode)
is real, and Claude Code has a first-class mechanism for it that we should name rather than leave
teams to reinvent: **path-scoped `.claude/rules/`**, whose rules *"only apply when Claude is working
with files matching the specified patterns"* ([claude-md][ccmem]). setup-flow now records this as the
Claude-native home for area/mode-specific instructions, so a project that genuinely needs fizzy's
`saas/AGENTS.md` shape has a sanctioned path instead of a bespoke conditional import.

## E. writebook's test/controller micro-conventions (NOTED — not scaffold material)

[writebook `AGENTS.md`][w-agents] is a different animal from fizzy's: no architecture, just four narrow
conventions — *"Prefer using existing fixtures over creating new records in tests"*, `_path` over
`_url` helpers in tests, `assert_in_body` / `assert_not_in_body`, and omitting an implied `{ render }`
in a `respond_to` block.

These are **not scaffold material**, and mostly not even ours to hold:

- `assert_in_body` and fixtures are **Minitest/Capybara** idioms. We mandate pure **RSpec** — the
  Phase E divergence (EPIC #96) — so they don't translate.
- `_path` over `_url` in tests is framework-neutral and sound, but it is **rails-8 skill doctrine**,
  not scaffold content, and `skills/**` is out of this phase's lane. Recorded here for whoever owns
  Phase A/E; not acted on in rails-flow.

The useful meta-observation: writebook folds a little style into `AGENTS.md` and ships **no**
`STYLE.md` (a `STYLE.md` fetch 404s), while fizzy separates them. Two 37signals apps, two shapes —
which is exactly why we anchor style in one shipped skill (B) rather than inheriting a per-app file
layout that isn't even consistent across their own repos.

## F. "Chrome MCP for local dev" — absent from source (RECORDED, not scaffolded)

Both #100 and #96 assert fizzy's `AGENTS.md` wires *"Chrome MCP for local dev"*, offered for
comparison against qa-flow's Playwright MCP. **It is not there.** As of 2026-07-31 (`main`), a
case-insensitive search for `mcp|chrome` over all **six** convention files — fizzy's
[`AGENTS.md`][f-agents], [`STYLE.md`][f-style], [`saas/AGENTS.md`][f-saas],
[`.claude/CLAUDE.md`][f-claude], and writebook's [`AGENTS.md`][w-agents] and
[`.claude/CLAUDE.md`][w-claude], 11,367 bytes in total — returns **zero matches**, with the pattern
verified against a positive control so the "no matches" is a real negative and not a broken search.

Nor is it configured anywhere else: fizzy has **no `.mcp.json`, no `.mcp.example.json`, and no
`.claude/settings.json`** (all 404), and its `README.md` never mentions MCP or Chrome. The 13 commits
that have ever touched `AGENTS.md` include none adding or removing MCP tooling. So this is not a stale
citation to something since deleted — the tools section the issue describes does not appear to have
existed.

This is the **#142 pattern** the maintainer doctrine warns about: a claim that reads as sourced —
attributed to a specific file — but is not in that file. An issue body is a hypothesis, not a
specification, and the most valuable output of checking one is sometimes negative. **No MCP tooling is
scaffolded on this basis.** qa-flow's Playwright-MCP choice is a qa-flow decision, in another plugin and
another lane, and is untouched — with the comparand absent from source, there is nothing here to weigh
it against, and inventing one to fill the gap is exactly what the gate forbids.

---

## What we did NOT take

- **An `AGENTS.md` where none exists** — Claude-native (#159); `CLAUDE.md` is the native canonical file.
- **A per-project `STYLE.md`** — the style doctrine is the Phase-A rails-8 skill; a copy would drift.
- **`saas/AGENTS.md`-style conditional layers by default** — a rare-case mechanism; `.claude/rules/`
  covers the real need.
- **writebook's Minitest test idioms** — we mandate RSpec (Phase E).
- **Chrome MCP tooling** — absent from source (F).

## Two findings that validate existing doctrine

Recorded because a convention that survives contact with production apps by Rails' own authors — and
with Claude Code's own docs — deserves the citation:

1. **Single source of truth via import is the sanctioned pattern.** 37signals' `.claude/CLAUDE.md` →
   `@../AGENTS.md` is precisely what [claude-md][ccmem] recommends. Our marker-based single-source
   discipline (rails-flow owns only content between its markers) is the same instinct, and Claude Code
   strips block-level HTML comments before injection ([claude-md][ccmem]) — so our
   `<!-- rails-flow:begin … -->` markers cost **zero** context tokens. The idempotency machinery is
   free to run.
2. **Keep the entry file short.** Claude Code targets *"under 200 lines per CLAUDE.md file"*
   ([claude-md][ccmem]) — the reason C is capped at non-derivable mechanisms and B points at a skill
   instead of inlining style. Every adoption here is additive by a few lines and deliberately so.

## Where each decision landed

All in `plugins/rails-flow/commands/setup-flow.md`:

- **A** — new subsection *"Coexist with an existing `AGENTS.md`"* + a detection note in §1.
- **B** — a style-doctrine pointer in the generated `CLAUDE.md` (*When Working in This Repo*) and the
  path-scoped-rule option noted alongside it.
- **C** — an `## Architecture Overview` element in the `CLAUDE.md` structure block, constrained to
  non-derivable mechanisms.
- **D** — `.claude/rules/` recorded as the home for area/mode-specific instructions.
- **E, F** — no scaffold change; recorded here as the decision record for both.

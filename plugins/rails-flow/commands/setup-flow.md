---
description: Scaffold, update, or repair the rails-flow conventions in this project — CLAUDE.md, GUARDRAILS.md, docs/brain. Idempotent and safe on customized repos; can diagnose and propose fixes for a defective CLAUDE.md (fact contradictions, broken safety rules) as approved diffs, never touching deliberate customizations.
---

# /rails-flow:setup-flow

Install, update, or repair the flow's project scaffolding. **This command is idempotent
and safe to re-run on any project, including one with a heavily customized CLAUDE.md — it
can never destroy hand-authored content.** Safety is structural, not a matter of care:

## Idempotency contract (how re-runs stay safe)

rails-flow owns only the content between its managed markers. Everything outside them —
your prose, your operating manual, your customizations — is never rewritten.

- rails-flow-authored blocks are delimited:
  `<!-- rails-flow:begin <section> -->` … `<!-- rails-flow:end <section> -->`.
- **First run** (no CLAUDE.md): create it, wrapping rails-flow sections in markers.
- **Re-run, markers present**: replace ONLY content between each marker pair; leave
  out-of-marker content byte-for-byte untouched (this is how re-runs pick up doctrine
  updates without disturbing customizations).
- **Re-run, CLAUDE.md exists but has NO markers** (hand-authored, like Fidara's): never
  restructure it; detect what the user's prose already covers, and for anything missing
  propose an additive marked block appended at the end, shown as a diff.
- Stage only files setup-flow authored; never `git add -A`; run `git status` so the
  user sees exactly what changed. GUARDRAILS.md, loop.md, docs/brain/* follow the same
  discipline.

## Audit & repair (existing CLAUDE.md)

Beyond coexisting, setup-flow can REPAIR a defective CLAUDE.md — but repair is always
**diagnose → propose diff → wait for approval**, never an autonomous rewrite. Nothing
is applied without the user seeing the exact change and accepting it.

Classify every finding into exactly one bucket; act only on the first two:

1. **Missing** — a required section is absent → propose ADDING it (additive marked
   block; not a "defect").
2. **Defective** — present but demonstrably broken against ground truth. Repair scope
   is deliberately limited to two objective classes:
   - **Contradicts fact**: the App Identity/stack table disagrees with the Gemfile or
     config (says Postgres when the adapter is sqlite3; names Devise when the app uses
     the Rails 8 generator; wrong Ruby/Rails version); a pointer references a path that
     doesn't exist (`docs/brain/` absent); AGENTS.md routing names an agent the plugin
     doesn't provide.
   - **Broken safety rule**: a Delegation Rules block missing the anti-recursion role
     check (executors that can spawn executors → runaway subagents); a rule that
     bypasses a documented gate; guidance that contradicts GUARDRAILS.md.
   For each: state WHAT is wrong, WHY it breaks (cite the Gemfile line / the missing
   path / the recursion path), and propose the corrected text as a diff. Wait for
   approval per fix — batch related ones, but never apply silently.
3. **Divergent but valid** — differs from rails-flow's vanilla defaults but isn't
   wrong: a documented Project Override (simple_form, a custom `app/services` layout,
   a bespoke branching model), custom prose, domain-specific rules. **Leave it
   untouched. Never "repair" a deliberate choice into vanilla.** When unsure whether
   something is defective or a deliberate override, treat it as an override and ask,
   rather than proposing a fix.

Explicitly OUT of repair scope: style, wording, ordering, or "missing best-practice"
sections (those are the additive path, not defects) — and anything inside the user's
own marked overrides. Repair fixes what is broken, not what is merely unlike the
default.

## 1. Inspect the project first

Fill the templates from reality, not assumptions: read the Gemfile (Rails version, DB
adapter, auth/authz gems, form builder, test stack, deployment), `config/application.rb`,
`db/schema.rb` header, directory shape (`app/services`? `spec/`? `mobile/`?), and existing
docs. Note every place the project deviates from the rails-8 skill's vanilla doctrine —
those become **Project Overrides**.

Also detect **existing agent-instruction files** — `AGENTS.md`, `.claude/CLAUDE.md`,
`.claude/rules/` — before writing anything. An `AGENTS.md` is increasingly present in Rails 8
apps and anything derived from a 37signals template, and scaffolding a second orientation file
beside it creates two entry points that can contradict each other. Handle it per §1b.

## 1b. Coexist with an existing `AGENTS.md` (one source of truth)

Claude Code reads `CLAUDE.md`, **not** `AGENTS.md`. When a repo already has an `AGENTS.md`
(kept for other coding agents), do NOT duplicate its content into `CLAUDE.md` and do NOT leave
two competing orientation files — **import it**, which is the pattern Claude Code's own memory
docs prescribe and the one 37signals use in fizzy and writebook (their `.claude/CLAUDE.md` is a
single line, `@../AGENTS.md`):

```markdown
@AGENTS.md

<!-- rails-flow:begin app-identity -->
...rails-flow-managed sections go BELOW the import...
<!-- rails-flow:end app-identity -->
```

The imported file loads first, then rails-flow's marked sections append after it — so the
existing file stays the source of truth for what it already covers, and rails-flow adds only
what is missing. Rules:

- **Never generate an `AGENTS.md` where none exists.** `CLAUDE.md` is the native file; a
  greenfield project gets `CLAUDE.md` alone (the flow is Claude-native by decision).
- The import is a **coexistence** tool, not the default layout. If the `AGENTS.md` is thin or
  stale, propose folding it into `CLAUDE.md`'s marked sections instead — as an approved diff —
  and say why: an `@`-import still loads fully into context at launch, so it organises without
  saving tokens. Reserve it for a live `AGENTS.md` another tool owns.
- Relative paths resolve **relative to the importing file**: `@AGENTS.md` from a root
  `CLAUDE.md`, `@../AGENTS.md` from `.claude/CLAUDE.md`. Pick one location for `CLAUDE.md` and
  state which; do not create both.
- Treat an authored `AGENTS.md` as hand-authored content under the idempotency contract —
  never rewrite or gitignore it (see also §5, which guards it against the graph installer).

## 2. CLAUDE.md — create or update within markers

First run: create CLAUDE.md with this structure, wrapping each rails-flow section in
`<!-- rails-flow:begin X -->`/`<!-- rails-flow:end X -->`. Re-run: follow the
idempotency contract and audit/repair pass above. The structure rails-flow contributes:

```markdown
# CLAUDE.md — <project>

**Product**: <one line> · **Stack**: Rails <x>, <DB>, Hotwire, <CSS>, Solid Queue, Kamal 2
This file is the AI agent entry point. Read it before starting any task.

## App Identity
<table of framework, database, jobs, cache, websockets, storage, auth, authorization,
asset pipeline, CSS, deployment, test suite — filled from the Gemfile/config inspection>

## Architecture Overview
<the NON-OBVIOUS, cross-cutting mechanisms and domain vocabulary an agent must know before
touching anything — 5-10 lines, prose. Include ONLY what cannot be derived by reading the
code: the tenancy model and how scope is set (middleware? Current.*?), the auth model, any
non-standard primary key, domain terms whose meaning is not their English meaning, and any
rule that holds app-wide ("every query is tenant-scoped"). NOT a directory tour, NOT a
dependency list, NOT "it uses Service Objects" — Claude Code's own /doctor trims derivable
overviews, and an agent can read the tree. Structure lives in the graph; point there:
"for what-calls-what, query docs/architecture/graph.json". An empty section is a valid
answer for a simple CRUD app — say so rather than padding it.>

## Common Commands
<dev server, console, migrate, targeted + full rspec, rubocop on changed files, brakeman,
bundler-audit, deploy — the project's real commands>

## Project Overrides (beats general doctrine)
<explicit list of deliberate deviations from the rails-8/hotwire skills, e.g.:
- Forms: simple_form mandatory — never raw form_with (styling lives in the initializer)
- Authorization: CanCanCan, hash conditions only
- Tenancy: all queries scoped through Current.<scope>; public ids in URLs, never DB ids
- N+1 detection: prosopite raises in test
Keep this section honest — an empty list is a valid answer.>

## Patterns
<the 3-6 patterns agents must copy: controller shape, service invocation + result object,
job shape (idempotent `perform`; the argument convention THIS codebase actually uses — record or id, do not impose one), key concerns — short code snippets from THIS codebase>

## Verification Commands
<grep one-liners that mechanically check the overrides, e.g. no raw form_with in views,
no unguarded .unscoped, no raw palette colors>

## Delegation Rules
You are the coordinator: design, decide, review, land. Delegate hands-on
execution to subagents; keep judgment here.
- Role check first: if your prompt starts with `ROLE: EXECUTOR` — or you were
  spawned by another agent — you are an executor: do the work order yourself,
  NEVER spawn subagents; if blocked, report back instead of delegating.
- Coordinator starts every executor prompt with
  `ROLE: EXECUTOR — do the work yourself; do not spawn subagents.`
- Delegate: implementation from a frozen plan, fixes, spec-writing to order,
  read-heavy exploration (fan out, each returns a distilled summary).
- Keep: design/architecture/naming, the land decision and all gates,
  releases/version bumps, tiny edits (<~20 lines — delegation overhead loses).
- Executor prompts are self-contained; subagents never see this conversation.

## When Working in This Repo
<numbered ALWAYS-rules distilled from the above — always include:>
- Defects reported mid-session get **FILED as issues first**, then worked one at a time via
  `/rails-flow:fix` (own branch → PR → spec). Never hot-fix inline, and never stack several
  unrelated fixes on the checked-out branch.
- Before writing or reviewing Ruby, read the **rails-8 skill's `skills/rails-8/references/style.md`** — how
  code should read here (conditional returns, method + invocation ordering, bang methods,
  visibility modifiers, `_later`/`_now` job naming). Project Overrides above win where they
  conflict; everything else follows the skill.

## Structural map (read before grepping)
`docs/architecture/graph.json` — `{nodes, edges, flows}` for this app: every controller,
model, job, mailer, service, component, Stimulus controller, route and table, plus named
request flows. To locate something or size a change, query the graph instead of reading
the tree; walk `edges` backwards from a node for its blast radius. Regenerate with
`/rails-flow:graph`; `index.html` is the human view. Generated — never hand-edit.

## See Also
AGENTS routing → the rails-flow plugin agents · GUARDRAILS.md · docs/brain/MEMORY.md
```

## 2b. Area- or mode-specific instructions belong in `.claude/rules/`

Keep `CLAUDE.md` short — Claude Code targets **under 200 lines**, and adherence drops as it
grows. So when instructions apply only to *part* of the codebase or only in a *mode*, do not
inline them here and do not invent a bespoke conditional import. Use a **path-scoped rule**:

```markdown
---
paths:
  - "app/models/**/*.rb"
---
# Model conventions for this app
- Every scope goes through `Current.account`; a bare `.unscoped` needs a comment saying why.
```

Rules live in `.claude/rules/*.md` (committed, team-shared) and a rule with `paths:` loads
**only when Claude reads a matching file** — so it costs nothing on sessions that never touch
that area. A rule with no `paths:` loads every session, same as `CLAUDE.md`; use that only for
genuinely global content.

Do **not** scaffold rules by default — most projects need none, and empty machinery is worse
than none. Surface the mechanism, and propose a rule only where the project actually shows the
need: a mode switch (an OSS/hosted split, as in fizzy's conditional `saas/AGENTS.md`), a
distinct area with its own conventions (`app/components`, an API namespace), or a per-project
style file, which belongs here scoped to `**/*.rb` rather than in a root `STYLE.md` that
loads in full every session.

## 3. Create `GUARDRAILS.md`

Sections: **Database migrations** (safe vs prohibited-without-approval, the migration
checklist with rollback proof, required patterns incl. money `decimal(15,2)`), **Git**
(branch model `main ← staging ← dev ← feature/*` adapted to this repo's real branches; no
force-push, no `git add -A`, no `--no-verify`, stage specific files, small logical commits),
**Secrets** (credentials only; never commit .env), **Deploys** (require explicit user
approval). Note at the top: *the rails-flow hooks enforce these mechanically; this document
is the human-readable law they implement.*

## 4. Seed the memory system (`docs/brain/`)

The brain is the repo-side mirror of session memory: open the repo and reconstruct where the
work is without re-reading every commit. Scaffold these (create only what's missing —
idempotent; never overwrite a populated file):

- **`README.md`** — the brain doctrine: the files + cadence table below, the provenance tags,
  the hypothesis lifecycle, and pointers to `/rails-flow:brain` · `:brain-review` · `:brain-sync`.
- **`STATUS.md`** — "where are we **right now**": current phase/slice, done, next, blockers.
  Edited in place every session; the single source of truth for current position. Header line
  `_Updated: <absolute date> · sha <short>_`.
- **`PROGRESS-LOG.md`** — append-only dated log of completed chunks. Only appended, never edited.
- **`DECISIONS.md`** — numbered ADR-lite (`D-001…`): the choice, alternatives, rationale, and a
  **reversal condition** (what would make us revisit it).
- **`HYPOTHESES.md`** — lifecycle `candidate → proposed → confirmed | refuted`, each with a
  dated evidence list and, on confirm, a pointer to the `DECISIONS` entry it produced.
- **`MEMORY.md`** — one-line index of `feedback_*` / `decision_*` memos (link + 8–15 word
  summary); the SessionStart hook injects its top into every session.

**Provenance** — tag every non-obvious claim in STATUS / PROGRESS / hypothesis-evidence with one:
`[observed]` (happened or measured), `[decided]` (backed by a DECISIONS entry), `[assumed]`
(working assumption, not verified), `[reported]` (a human/stakeholder asserted it). **Preserve
contradictions** — never average two conflicting `[reported]` claims into one; list both. That
audit trail is the point: the brain surfaces evidence and its provenance; the human still judges.

Then explain the commands: `/rails-flow:brain` (institutionalize a lesson/decision as a memo),
`/rails-flow:brain-review` (maintenance sweep — staleness, drift, contradictions; it stamps
`docs/brain/.last-review`, and the **SessionStart hook nudges when the sweep is overdue** —
default 7-day cadence, override `RAILS_FLOW_BRAIN_REVIEW_DAYS`, reminder-only/no auto-run),
`/rails-flow:brain-sync` (publish to / consume a cross-project shared brain repo). Memos and
STATUS are the repo side of memory, not lost in chat history.

## 5. Knowledge-graph integration (only if graph tools are present)

Detect with `command -v code-review-graph` and `command -v graphify`. Skip absent
tools silently. For code-review-graph, wire it to coexist with the rails-flow hooks:

1. **Protect authored files.** Its installer rewrites AGENTS.md/GEMINI.md/.cursorrules.
   Require a clean git state before `code-review-graph install`; afterwards run
   `git status` and restore any hand-authored file it clobbered
   (`git checkout -- AGENTS.md`). Never gitignore an authored AGENTS.md.
2. **Three-file settings pattern.** Keep `.claude/settings.json` permissions-only.
   Replace any installer-written PostToolUse graph hooks with a PID-guarded Stop hook in
   `.claude/settings.example.json` (committed; teammates copy to gitignored
   `.claude/settings.local.json`):

   ```json
   {"hooks": {"PostToolUse": [], "Stop": [{"hooks": [{"type": "command", "timeout": 5,
     "command": "command -v code-review-graph >/dev/null 2>&1 && [ -d .code-review-graph ] && { PF=/tmp/crg-claude.pid; if [ -f \"$PF\" ] && kill -0 \"$(cat \"$PF\")\" 2>/dev/null; then true; else { code-review-graph update --skip-flows 2>/dev/null && nohup code-review-graph embed >/dev/null 2>&1 & } & echo $! > \"$PF\"; fi; } || true"}]}]}}
   ```

   Rationale: per-edit PostToolUse updates pile up processes; Stop fires once per turn.
   rails-flow's own per-edit hook stays rubocop-only, so the two never contend.
   Also add a SessionStart hook to the same settings.example.json (same shape as the
   Stop hook: fire only when `.code-review-graph` exists) whose command prints a
   `hookSpecificOutput.additionalContext` JSON containing this static cheatsheet
   (~100 tokens, pre-empts reflexive grepping):
   `GRAPH FIRST — where is X → semantic_search_nodes_tool · who calls X →
   query_graph_tool(callers_of) · blast radius → get_impact_radius_tool · review
   context → get_review_context_tool · CRG 0 results → graphify query '<term>' →
   grep · skip graph for .md/.yml/configs.`
3. **Trim MCP schema.** In the project's mcp server config for code-review-graph, set
   `CRG_TOOLS` to the 8-tool working set (semantic_search_nodes_tool, query_graph_tool,
   get_impact_radius_tool, traverse_graph_tool, list_communities_tool, get_community_tool,
   get_review_context_tool, list_graph_stats_tool) — cuts ~70% schema overhead and makes
   the 33k-token architecture-overview tool uncallable.
4. **Close the terminal-commit gap.** The CLI ships no post-commit updater, so commits made
   outside Claude leave the graph stale. Append to `.git/hooks/post-commit`
   (or `.husky/post-commit`) and `chmod +x`:

   ```sh
   #!/bin/sh
   GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
   [ -d "$GIT_DIR/rebase-merge" ] || [ -d "$GIT_DIR/rebase-apply" ] && exit 0
   [ -f "$GIT_DIR/MERGE_HEAD" ] || [ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0
   if command -v code-review-graph >/dev/null 2>&1 && [ -d .code-review-graph ] \
      && ! pgrep -qf 'code-review-graph update' 2>/dev/null; then
     nohup timeout 300 sh -c \
       'code-review-graph update --skip-flows && code-review-graph embed' \
       > "$HOME/.cache/crg-update.log" 2>&1 < /dev/null &
   fi
   ```
   Also close the branch-switch gap with `.git/hooks/post-checkout` (branch changes
   rewrite the tree with no edit hook firing — the exact staleness the Stop hook
   cannot see). `chmod +x` after writing:

   ```sh
   #!/bin/sh
   [ "$3" = "1" ] || exit 0   # branch switches only, not file checkouts
   command -v code-review-graph >/dev/null 2>&1 && [ -d .code-review-graph ] || exit 0
   pgrep -f 'code-review-graph (update|build)' >/dev/null 2>&1 && exit 0
   N=$(git diff --name-only "$1" "$2" 2>/dev/null | wc -l | tr -d ' ')
   if [ "${N:-0}" -gt 5 ]; then CMD='code-review-graph build'
   else CMD='code-review-graph update --skip-flows && code-review-graph embed'; fi
   nohup timeout 300 sh -c "$CMD" > "$HOME/.cache/crg-checkout.log" 2>&1 < /dev/null &
   ```

      Portability: `timeout` is absent on stock macOS — install coreutils (`brew install
   coreutils`, giving `gtimeout`) or the hook silently runs without the time cap.

   (graphify's own `graphify hook install` already writes both post-commit and
   post-checkout — only CRG needs this manual one.)
5. **Gitignore hygiene.** Add `.code-review-graph/` and `.mcp.json` (commit
   `.mcp.example.json` instead) plus tool-generated IDE configs.
6. **Build once**: `code-review-graph build && code-review-graph embed`, then a FULL
   Claude Code restart (`.mcp.json` is read at startup only).
7. **graphify (if present)** — the exploration/cross-repo graph, complementary to CRG:
   - Create `.graphifyignore` (node_modules, vendor, tmp, log, coverage, public/assets,
     graphify-out/, .code-review-graph/) then build: `graphify update .`
   - Freshness via ITS OWN git hooks only: `graphify hook install` (post-commit +
     post-checkout). NEVER add graphify to Claude Stop/PostToolUse hooks — its ~10s
     update piles up per-turn and saturates CPU/RAM. Add a resource guard (skip when
     CPU >50% or free memory <2GB) to the installed git hooks.
   - Add the fallback chain to CLAUDE.md's knowledge-graph pointer:
     `CRG 0 results → graphify query '<term>' --graph graphify-out/graph.json → grep`
   - Ruby is first-class (dedicated extractor incl. singleton methods and a member-call
     resolver). Same AST caveat as CRG for Rails metaprogramming.

## 6. Default maintenance loop (`loop.md`)

Claude Code's bare `/loop` runs a built-in maintenance prompt unless a `loop.md` at the
project root replaces it. Scaffold one so bare `/loop` IS this project's health check
(never overwrite an existing loop.md — propose a merge):

```markdown
# loop.md — default maintenance pass for bare /loop

Run this pass and report ONLY deltas or problems; if everything is clean, reply
"all green" in one line. Guardrails and the stop gate apply as always. Never
deploy; never touch main.

1. Sync check: `git fetch`; report divergence from <base>. If behind and the
   working tree is clean, `git pull --ff-only`.
2. Suite health: `bundle exec rspec --fail-fast --no-color`. On red, delegate
   analysis to the test-runner agent; fix per /rails-flow:fix principles
   (failing spec first for behavioral bugs).
3. Lint drift: rubocop on Ruby files changed vs origin/<base>.
4. Security deltas: `bundle exec bundler-audit check --update` and
   `bundle exec brakeman -q` if installed — report NEW findings only.
5. Graph freshness (if code-review-graph is present): `code-review-graph status`;
   if Last updated lags the last commit, run `code-review-graph update --skip-flows`.
6. Curated-skills drift (if `.claude/skills/.manifest.tsv` exists): compare each
   source doc's hash against the manifest; report drift as "run
   /rails-flow:curate" — never regenerate skills inside the maintenance loop.
7. Architecture-graph freshness (if `docs/architecture/graph.json` exists): run the
   graph drift check; on exit 1 report the delta and say "run /rails-flow:graph" —
   regenerating a committed artefact is not the maintenance loop's job.
```

Fill `<base>` with the branch detected in CLAUDE.md setup. Tell the user: bare `/loop`
now runs this on an interval; pair with `--expires` for bounded sessions.

## 6b. Architecture graph (`docs/architecture/`)

Tell the user about `/rails-flow:graph`: it extracts `{nodes, edges, flows}` from
`config/routes.rb`, `app/**` and `db/schema.rb` into `docs/architecture/graph.json`, a
self-contained `index.html` (inline CSS/JS, zero external requests — opens from disk
offline) and a mermaid `graph.md` for GitHub. One artefact, three consumers: humans get a
picture, agents get structural context without reading the whole codebase, and qa-flow gets
reverse dependencies for a computed blast radius.

Offer to generate it now (it needs nothing installed beyond `python3`) and, if the project
has a hosted CI, propose the drift guard in §8. Don't force it — but do say plainly why it
beats a hand-drawn diagram: this one is regenerated at session end and at release, and CI
fails when the code moves and the graph does not.

## 7. Project skills (docs → skills)

If `docs/` contains PRDs, branding, architecture, or domain documentation, tell the
user about `/rails-flow:curate`: it distills those into project-local skills in
`.claude/skills/` (committed, team-shared) and keeps them synced via a manifest as
docs evolve. Don't run it unprompted during setup — just surface it.

## 7b. The human guide (`docs/GUIDE.md`)

§7 runs docs → agent skills. Tell the user about the direction nothing else covers:
`/rails-flow:explain` writes `docs/GUIDE.md`, a plain-language guide to their own system with
mermaid diagrams that render on GitHub, plus a *"check it yourself"* section per area — the
human-runnable form of the acceptance criteria.

Say why it exists rather than listing it: every other file this scaffold creates is written for
an agent, and agents now produce more code per day than an owner can read. The guide is bounded
on purpose — it links to `docs/architecture/graph.md` for structure and `docs/brain/DECISIONS.md`
for rationale instead of restating either, so the parts that can go stale stay small. Don't
generate it during setup; there is nothing to explain yet.

## 8. GitHub CI economy (`.github/workflows/ci.yml`)

If `.github/workflows/ci.yml` exists (the Rails 8 default), check its `on:` triggers. The scaffold
default runs the **full matrix on every push and PR** — which re-runs, on every `feature → dev` PR,
what the local `bin/ci` hooks + qa-flow already proved, and **burns Actions minutes** (on a private
repo this can exhaust the quota and block merges). Propose scoping the hosted CI to the
`dev → main` gate only — as an **approved diff, never a silent rewrite**:

```yaml
on:
  pull_request: { branches: [main] }   # the dev→main promotion PR (base=main)
  push:         { branches: [main] }    # the merge push onto main
  workflow_dispatch: {}                  # on-demand
```

Rationale: **Actions minutes.** On a private repo the scaffold default can exhaust the quota and
block merges, and `dev → main` is the gate that matters because it is what the project deploys from.

The rationale this used to give was *"local `bin/ci` hooks + qa-flow already proved it for
feature → dev"*. **That was an assumption, not a guarantee** — if the agent did not run qa-flow,
nothing proved anything. The minutes argument stands on its own; the "already proved" claim does
not, and it is exactly the claims-vs-enforcement shape this toolchain exists to remove. Idempotent —
if the triggers already match (or the user declined), leave `ci.yml` untouched and say so. (Doctrine:
rails-8 `testing.md` § *bin/ci*; if the `pipeline` plugin is installed, this aligns with its
main-only release/build workflows.)

### The `--skip-test` consequence — propose the `Tests:` steps as an approved diff (#779)

`project-setup.md` mandates `--skip-test` so the project gets RSpec instead of Minitest. Rails gates
the test steps in its own `config/ci.rb` template on **that same flag**, so a fresh scaffold has no
`Tests:` step and `bin/ci` — which this toolchain treats as the full gate — reports **green having
run zero specs**. #391 fixed the doctrine; nothing performed it, and it landed missing on two
unrelated greenfield apps from clean runs of the documented path.

**Detect the shape** — `config/ci.rb` exists, RSpec is present, and no step's *command* runs the
suite. The `ci-runs-tests` check answers exactly this and is the same question:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_ci_runs_tests.py"
```

Exit **1** means propose the steps; exit **3** means the project has no `config/ci.rb` and there is
nothing to offer. Take the block verbatim from `rails-8` `references/testing.md` — both steps, since
Rails drops `Tests: Seeds` on the same flag — and insert it **before** the Style and Security steps,
so a broken suite stops the run before the slower checks:

```ruby
  step "Tests: Seeds", "bin/rails db:test:prepare db:seed:replant"
  step "Tests", "bin/rspec"
```

**Propose the generators block in the same diff**, because it fails the same way. `project-setup.md`
§1 prescribes it "immediately after creation", and on both affected scaffolds `config/application.rb`
carried only Rails' own `config.generators.system_tests = nil`:

```ruby
config.generators do |g|
  g.test_framework :rspec, fixture: false
  g.fixture_replacement :factory_bot, dir: "spec/factories"
  g.system_tests nil
end
```

**And `factory_bot_rails` with it** — `fixture_replacement :factory_bot` is **inert** without the
gem, so `bin/rails generate` silently emits no factories. `bundle add factory_bot_rails --group
'development,test'`. The `mandated-gems` check refuses that combination by name.

Offer all three as one approved diff; do not write them unasked. Re-running is safe — every check
above is idempotent, and a project that already has the steps reports exit 0.

### Ask whether this project is monolingual, and RECORD the answer (#799)

**Ask.** *"Will this app serve more than one language?"* Most will not, and demanding locale files
everywhere is the false positive that gets a rule ignored — but demanding nothing leaves a
multi-locale app silently monolingual.

**Recording the answer is what makes a situational rule checkable at all.** Without a declaration
there are only two options and both are wrong: gate everyone, or gate nobody. With one, the check
gets three honest states — conforming, drifted, and *not applicable because this project declared
monolingual*. Same mechanism as `config.x.brand.pack` (#788).

```ruby
# config/initializers/locales.rb
Rails.application.configure do
  config.x.locales = %w[en]                 # monolingual — one element, still DECLARED
  # config.x.locales = %w[en ar fr]         # multi-locale
end
```

Write `%w[en]` even for a monolingual app. It is the difference between *"this project chose one
locale"* and *"nobody thought about it"*, and only the first can be checked.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_i18n_setup.py"
```

On a multi-locale answer, propose `skills/rails-8/references/i18n.md` §1–§2 — `available_locales`,
`rails-i18n`, and the `around_action` wrapper. **Never a `before_action`**: Rails' guide says
`I18n.locale` *"can leak into subsequent requests served by the same thread/process"*, and Puma is
threaded, so a locale set and never reset is served to whoever gets that thread next.

### Coverage that cannot catch a regression — propose the ratchet (#800)

`testing.md` used to ship `minimum_coverage 90` **commented out** with *"enable once realistic"*.
Nothing ever makes it realistic, so coverage goes unenforced from the first commit to the last.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_coverage_ratchet.py"
```

Exit **1** means propose the diff; exit **3** means no `simplecov` and nothing to offer.

**The ratchet** — in the SimpleCov block:

```ruby
refuse_coverage_drop :line, :branch
minimum_coverage_by_file line: 0     # inert at 0; raise deliberately
```

Today's number is the floor, so it is **never red on day one**, it **cannot slide**, and it **rises
by itself** as specs are written. Do **not** propose a fixed `minimum_coverage <n>` — below where the
repo sits it is inert, above it every run is red and it gets switched off.

**Its memory** — `.gitignore`, or the ratchet compares against nothing in CI:

```gitignore
/coverage/
!/coverage/.last_run.json
```

`coverage/.last_run.json` is the one file there that is not a build artifact. Committed, the diff
also shows coverage moving.

**Say plainly that this one gates.** A coverage *drop* is a measured regression against a recorded
baseline, not a judgement about whether 83% is good — which is why it can block a merge where a
threshold never could.

### The support directory nothing loads — propose the wiring as an approved diff (#803)

`testing.md` prescribes four files under `spec/support/` — `system.rb`, `authentication_helpers.rb`,
`webmock.rb`, `vcr.rb` — and **Rails generates the auto-loader commented out**. Left as generated,
every one of them is dead: no error, no output, and the specs that needed those helpers fail for
reasons that point somewhere else. `testing.md:99` says to uncomment it; nothing checked that anyone
had.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_spec_support.py"
```

Exit **1** means propose the wiring; exit **3** means no `spec/` and there is nothing to offer.

**The auto-loader**, in `spec/rails_helper.rb` — uncomment the generated line, or add it:

```ruby
Rails.root.glob("spec/support/**/*.rb").sort_by(&:to_s).each { |f| require f }
```

**The driver**, when `capybara` is present — `spec/support/system.rb`, verbatim from `testing.md` §8:

```ruby
RSpec.configure do |config|
  config.before(:each, type: :system) do
    driven_by :selenium, using: :headless_chrome, screen_size: [1400, 1400]
  end
  # For specs with zero JavaScript, rack_test is ~10x faster:
  config.before(:each, type: :system, js: false) { driven_by :rack_test }
end
```

**System specs are the developer testing workflow, and `qa-flow` is not a substitute** (#803). The
browser passes in `/qa-flow:crawl` and `/qa-flow:functional` are an **independent** layer — that
independence is the whole value, and folding one into the other destroys it. A developer with no
system specs has no browser feedback until QA runs; QA running the developer's specs is not
independent verification.

### The mandated gem nobody installs — propose `simple_form` as an approved diff (#778)

`ecosystem-gems.md` §2: *"simple_form is mandatory in this stack — no form, and no form element, is
built any other way."* It had **no installer and no gate**, and was missing on both scaffolds. Two of
the three "Always" gems already have checks; this one did not.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_mandated_gems.py"
```

On exit **1**, propose whatever it names. Two shapes come out of it:

**The prescribed testing stack** (#797). `skills/rails-8/references/testing.md` declares a complete
Gemfile block and that file is this stack's testing doctrine, not a menu — yet nothing installed it
and nothing checked it, so a scaffold could hold `rspec-rails` and no `simplecov`, `webmock` or
`vcr` and report clean everywhere. The check names each missing gem and the exact command:

```bash
bundle add rspec-rails factory_bot_rails faker --group 'development,test'
bundle add capybara selenium-webdriver simplecov webmock vcr rubocop-rspec --group test
```

Take the list from the **check's output**, not from this page — it is derived from `testing.md`, so
this block is illustrative and the check is authoritative. **`database_cleaner-active_record` is
deliberately not in it**: `testing.md` §2 says transactional fixtures already cover it.

**The mandated form gem:**

```bash
bundle add simple_form
bin/rails generate simple_form:install
```

The generator writes `config/initializers/simple_form.rb` and the wrappers this stack's form
partials assume. Do not hand-write that initializer — the generator's output is the version-correct
one, and `ecosystem-gems.md` §2 says to configure it once and never fight it per-form.

### Executable boundaries — propose `Archspec.rb` as an approved diff (#715)

The doctrine in `rails-8` `ecosystem-gems.md` §13 states two forbidden dependencies, and until a
project has an `Archspec.rb` **nothing checks either of them** — the `architecture-boundaries` check
reports *not-applicable*, forever. Offer the file; do not write it unasked.

Propose exactly this, adjusting the two component paths to what the project actually has, and skip
any rule whose paths are absent rather than inventing them:

```ruby
# Archspec.rb — at the project root, beside the Gemfile
source "app/**/*.rb", "db/**/*.rb"

component :models,             in: "app/models/**/*.rb"
component :migrations,         in: "db/migrate/**/*.rb"
component :tenant_concern,     in: "app/controllers/concerns/set_current_tenant.rb"
component :shared_controllers, in: "app/controllers/application_controller.rb"

# rails-8 models.md §1 — a migration that references a model breaks when the class evolves.
migrations.cannot_use :models

# rails-8 multi-tenancy.md §1 — the tenant concern must not reach ApplicationController, or the
# admin plane inherits it and "a tenant session grants zero admin access" stops being structural.
shared_controllers.cannot_use :tenant_concern
```

**No `architecture :preset` line.** `:vanilla_rails` requires `app/components` to stay empty and so
fails any project using ViewComponents; `:rails` passes but enforces none of the above. Presets also
make components **overlap**, and every rule applies to every component a file belongs to — which
turns one real finding into three. §13 has the measured detail.

Add the gem to the Gemfile's `:development, :test` group in the same diff, or the check reports a
missing binary rather than a verdict:

```ruby
gem "archspec", "~> 1.0"
gem "herb", "~> 0.10"
```

**Never offer `--update-todo`**, and if the project already has a todo file, say that it is a
suppression baseline rather than treating it as configuration.

### The doctrine gate — propose it as an approved diff (#334)

At that `dev → main` trigger the project runs **its own** matrix: tests, lint, Brakeman. **None of
the checks this toolchain ships run there**, so nothing verifies the doctrine before the deploy
branch moves. Propose one job that runs all of them:

```yaml
  doctrine:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # The toolchain is checked out BESIDE the repo. `$CLAUDE_PLUGIN_ROOT` does not exist in CI --
      # it is set only inside Claude Code's own plugin context -- so a job referencing it fails with
      # `can't open file '/scripts/project_gates.py'` on every run.
      - uses: actions/checkout@v4
        with:
          repository: fmanimashaun/claude-skills
          ref: <PIN THE CURRENT TAG>   # never `main`: your CI would change when we ship
          path: .claude-toolchain
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: python3 .claude-toolchain/plugins/rails-flow/scripts/project_gates.py
```

**Resolve `ref` before you write the file** — do not paste the placeholder:

```bash
gh release view --repo fmanimashaun/claude-skills --json tagName -q .tagName
```

Substitute that tag. If `gh` is unavailable, ask the user for a tag from
<https://github.com/fmanimashaun/claude-skills/releases> rather than guessing one, and never fall
back to `main`.

**Why a placeholder and not a real version here** (#713). This block used to carry a literal
`ref: v1.51.0`, and by the time anyone noticed it was **41 releases behind**. That is worse than an
obviously-broken placeholder, because a stale pin *works*: every project scaffolded from it silently
enforced v1.51.0's rules in CI while the same project's local session enforced current ones, and
nothing in either place said the two disagreed. A literal version inside shipped doctrine is a clock
nobody winds. `lint_self_consistency`'s `pinned-toolchain-ref` rule now refuses one.

The runner discovers every sibling plugin's `checks.json` from that one checkout, so a single step
covers all of them. **Pin the `ref`** — an unpinned `main` means our next release silently changes
what your CI enforces, which is the same drift this whole toolchain exists to remove. Bump it
deliberately, the way you bump any other dependency, and record which tag you pinned so the bump is
a decision rather than a discovery.

`project_gates.py` discovers which of the shipped checks apply to *this* repo and reports four
states — **pass / FAIL / not-applicable / ERROR**. A project with no `qa/` directory reports the
evidence checks as **not applicable**, loudly, and never as a pass: a repo with zero evidence must
not go the same green as a repo with complete evidence. Run `--list` first to show the user exactly
what will and will not run in their project, and why.

Each non-pass outcome also says **whose tracker it belongs to** (#485), because not every red line
is a defect in this project. A **FAIL** is theirs — a detector ran against their content and found
something. An **ERROR** is *ours*: a manifest of ours naming a script of ours that is not there,
which their code cannot cause, so it goes upstream with `/rails-flow:report` rather than into their
backlog. A missing `requires` binary is **neither** — install it. Not-applicable is routed nowhere
at all, which is the same rule as "not applicable is not a pass", one step later. Read the routing
before filing anything; `--json` emits the same run with the destination and its reason on every
non-pass row (a pass carries `null`), for an agent that has to act on it rather than read it.

**The deploy or release job must declare `needs: doctrine`.** This is the part to insist on. A
parallel job is *advisory* — it can go red after the deploy has already happened, which is a check
that reports rather than a gate that stops. We learned this in our own repo: the release workflow
published from `main` with no dependency on the gate sweep, so the promotion PR was verified and the
merge commit that actually shipped was not.

```yaml
  deploy:
    needs: [test, doctrine]
```

Same approved-diff rule as everything else here: show the change, never rewrite `ci.yml` silently.
**Idempotent** — if the job is already present and current, say so and change nothing.

While in `ci.yml`, propose the **architecture-graph drift guard** as a separate job (same
approved-diff rule — never a silent rewrite). It is the mechanical half of
`/rails-flow:graph`: a guarantee placed in the deterministic layer instead of trusted to an
agent's memory.

```yaml
  architecture-graph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.x" }
      - name: Architecture graph is current
        run: python3 .claude/scripts/architecture_graph.py --check
```

It rebuilds the graph and compares the `content_digest` over `{nodes, edges, flows}` —
rebuild-and-diff, the same shape as a packaging drift guard, so **code that moved without
the graph moving fails the promotion**. No Ruby, no gems, no DB, no app boot: it is a
seconds-long job. Two setup details worth stating to the user:

- The script ships inside the plugin, which CI does not install. Vendor it once to
  `.claude/scripts/architecture_graph.py` (copy from
  `${CLAUDE_PLUGIN_ROOT}/scripts/architecture_graph.py`) and re-copy when rails-flow
  updates — or skip the job if the team would rather not vendor. Say which was chosen.
- **Two patterns coexist here on purpose, and the difference is worth stating.** This job
  **vendors** one script; the doctrine job above **checks the toolchain out** at a pinned tag.
  Vendoring suits a single self-contained file whose staleness is visible — the digest guard fails —
  but it drifts by design, which is what "re-copy when rails-flow updates" means. The doctrine gate
  runs many scripts across four plugins, so vendoring it would be four copies drifting
  independently; a pinned checkout is one dependency you bump deliberately.
- `generated_at`/`commit` are excluded from the digest, so this never fails merely because
  someone re-ran the generator.

## 8b. Issue labels the flow files with

`/rails-flow:pr-comments` folds an out-of-scope review comment into the tracker with
`--label "from-pr-review"`. `gh issue create` **errors and creates nothing** when a label does not
exist — it does not fall back to an unlabelled issue — so without this the item is **lost**, and
the instruction to reply on the thread with the new issue link cannot be followed. Create it now,
idempotently:

```bash
gh label create from-pr-review --color 5319E7 \
  --description "Raised in PR review, deferred out of scope" --force
```

`--force` makes a re-run update the description rather than fail on "already exists".

This does **not** cover the labels `claude-skills-reporter` passes — those go to the **upstream**
tracker with `--repo`, where the taxonomy is somebody else's to provision. `scripts/lint_self_consistency.py`'s
`unprovisioned-label` rule draws exactly that line, so a new `--label` against the user's own repo
fails the build until a setup step creates it.

If `gh` is unauthenticated, say so and skip — name it **not done** rather than letting a complete
report imply it happened.

## 9. Report

List created files, the detected Project Overrides, and any ambiguity you need the user to
settle (e.g. base branch, form builder mandate yes/no).

Also surface the upstream feedback path: if you hit friction with the toolchain itself (a
hook, command, skill, or setup step misbehaving), `/rails-flow:report <what you saw>`
drafts a structured, deduped, version-pinned issue to the claude-skills repo — toolchain
only, drafts by default. It's how the flow improves from real use.

---

**Why this scaffold has the shape it does.** The agent-instruction conventions above — the
`AGENTS.md` import (§1b), the Architecture Overview constraint (§2), the `.claude/rules/`
placement (§2b), and the style pointer instead of a per-project `STYLE.md` — were decided by
comparing this scaffold against 37signals' own agent instructions in
[fizzy](https://github.com/basecamp/fizzy) and
[writebook](https://github.com/basecamp/writebook), and against Claude Code's memory docs.
Each adopt / adapt / reject decision is recorded with its citation in
`${CLAUDE_PLUGIN_ROOT}/reference/agent-instruction-conventions.md` — read it before changing
any of them, since several look like arbitrary style choices and are not.

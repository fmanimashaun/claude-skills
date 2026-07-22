---
description: Scaffold the rails-flow conventions into this project — CLAUDE.md, GUARDRAILS.md, and the docs/brain memory system
---

# /rails-flow:setup-flow

Install the flow's project scaffolding. Never overwrite an existing file — if CLAUDE.md or
GUARDRAILS.md exists, propose a merged diff and let the user decide.

## 1. Inspect the project first

Fill the templates from reality, not assumptions: read the Gemfile (Rails version, DB
adapter, auth/authz gems, form builder, test stack, deployment), `config/application.rb`,
`db/schema.rb` header, directory shape (`app/services`? `spec/`? `mobile/`?), and existing
docs. Note every place the project deviates from the rails-8 skill's vanilla doctrine —
those become **Project Overrides**.

## 2. Create `CLAUDE.md` with this structure

```markdown
# CLAUDE.md — <project>

**Product**: <one line> · **Stack**: Rails <x>, <DB>, Hotwire, <CSS>, Solid Queue, Kamal 2
This file is the AI agent entry point. Read it before starting any task.

## App Identity
<table of framework, database, jobs, cache, websockets, storage, auth, authorization,
asset pipeline, CSS, deployment, test suite — filled from the Gemfile/config inspection>

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
job shape (ids only, idempotent), key concerns — short code snippets from THIS codebase>

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
<numbered ALWAYS-rules distilled from the above>

## See Also
AGENTS routing → the rails-flow plugin agents · GUARDRAILS.md · docs/brain/MEMORY.md
```

## 3. Create `GUARDRAILS.md`

Sections: **Database migrations** (safe vs prohibited-without-approval, the migration
checklist with rollback proof, required patterns incl. money `decimal(15,2)`), **Git**
(branch model `main ← staging ← dev ← feature/*` adapted to this repo's real branches; no
force-push, no `git add -A`, no `--no-verify`, stage specific files, small logical commits),
**Secrets** (credentials only; never commit .env), **Deploys** (require explicit user
approval). Note at the top: *the rails-flow hooks enforce these mechanically; this document
is the human-readable law they implement.*

## 4. Seed the memory system

Create `docs/brain/MEMORY.md` (an index: one line per memo — link + 8-15 word summary) and
explain `/rails-flow:brain` to the user: lessons and decisions get institutionalized as
memos, not lost in chat history.

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
```

Fill `<base>` with the branch detected in CLAUDE.md setup. Tell the user: bare `/loop`
now runs this on an interval; pair with `--expires` for bounded sessions.

## 7. Project skills (docs → skills)

If `docs/` contains PRDs, branding, architecture, or domain documentation, tell the
user about `/rails-flow:curate`: it distills those into project-local skills in
`.claude/skills/` (committed, team-shared) and keeps them synced via a manifest as
docs evolve. Don't run it unprompted during setup — just surface it.

## 8. Report

List created files, the detected Project Overrides, and any ambiguity you need the user to
settle (e.g. base branch, form builder mandate yes/no).

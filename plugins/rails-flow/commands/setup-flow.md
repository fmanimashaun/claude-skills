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
     doesn't exist (`docs/brain/` absent; a "Before you change an area" line naming a doc
     that is not there); AGENTS.md routing names an agent the plugin
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

## 0. Which stack — detect it, or ask (#2180)

The working rules this command writes (git flow, guardrails, labels, worktrees, parallel sessions, who merges) name no
stack and are the same in both paths below. What differs is the stack: its facts and its own repairs come from the
stack's plugin, never from this file. The detector ships beside this command (`scripts/detect_stack.py`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_stack.py" . --descriptor
```

- **An existing project** (exit 0): the detector has read the stack from the repository's markers. **Do not ask.**
  Activate every stack it reports, one or several: markers of two stacks (a Rails API beside a Next.js front end)
  activate both. **Show which stacks you activated**, by id and plugin (each `stacks` entry carries both), before writing anything. Their descriptor
  (commands, layout, gates, agents) fills the scaffold, and every file under `setup_sections` is a stack's own
  repairs, worked in §8.
- **No stack markers** (exit 1): **ask which stack to set up**, offering exactly what the installed stack plugins
  declare, never a list from memory. Exit 1 also covers an existing repository of a stack no installed plugin
  declares (a `Cargo.toml` alone). So read `fresh` in the output. `true` means the tree holds only what a new repository
  holds (`.git`, `README*`, `LICENSE*`, `.gitignore`, `.github/`, `docs/`) plus the agent files this command writes, so it is a
  new project. `false` means it holds something else: **do not scaffold an app over it**; say no installed stack plugin
  recognises it, and stop. For a fresh tree:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_stack.py" --available
  ```

  Scaffold the app from the chosen stack's plugin (Rails: the rails-8 skill's `project-setup.md`), then take its
  descriptor and setup sections the same way, naming the choice:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_stack.py" . --stack "<id>" --descriptor
  ```

  `--available` exiting 1 means no stack plugin is installed. Say so and name the plugins to install; do not guess a stack.
  **`--available` or `--stack` exiting 2 means a manifest could not be read: stop, quote the printed problems, and do
  not offer a partial list.** `--available` still prints the stacks it could read beside the problems, and offering
  those alone is a silent fallback.
- **It cannot tell** (exit 2): a manifest, the project or a descriptor could not be judged. **Ask**, quoting the
  printed `problems`, and never fall back to Rails. **Ignore `stacks` in the output whenever `problems` is
  non-empty**: they are what the detector could read, not a verdict.

A project can be several stacks at once (Next.js + Supabase + Vercel). Then every reported stack is active, with no
question asked, and each setup section is worked in turn. Asking is only for exit 1 or exit 2.

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

Claude Code reads `AGENTS.md` too, from **v2.1.277**, and which file wins depends on what the
repo has ([memory docs][cc-memory], verified 2026-09-21):

| the repo has | Claude reads |
|---|---|
| `AGENTS.md`, and no `CLAUDE.md`/`CLAUDE.local.md` at or above the cwd | the `AGENTS.md` |
| `AGENTS.md` **and** a `CLAUDE.md`/`CLAUDE.local.md` | **the `CLAUDE.md` only** |
| a `CLAUDE.md` that imports `AGENTS.md` | both, through the import |

**Row 2 is the trap, and it is the one this command can spring.** `setup-flow` writes a
`CLAUDE.md`. Creating one in a repo with a live `AGENTS.md` and no import **silently stops Claude
reading that `AGENTS.md`** — no warning, no error, the file simply stops being consulted. So:
**before writing a `CLAUDE.md` where an `AGENTS.md` exists, say so and add the import in the same
change.**

Two more facts worth stating, because both are counterintuitive:

- **`CLAUDE.local.md` counts.** A developer adding one for their own uncommitted notes stops Claude
  reading `AGENTS.md` *for themselves only* — a per-developer failure nobody else can reproduce.
- **`~/.claude/CLAUDE.md`, managed instructions and `.claude/rules/` do NOT count**; they keep
  loading alongside.

**The import is still the recommendation**, and the docs now support it more strongly than the old
reasoning did: it is the one arrangement that works when direct `AGENTS.md` support is unavailable —
before v2.1.277, on Amazon Bedrock or other third-party providers, with telemetry disabled, on the
first session after an upgrade, and under `disableAllHooks`/`allowManagedHooksOnly`. It is also the
pattern 37signals use in fizzy and writebook (their `.claude/CLAUDE.md` is a single line,
`@../AGENTS.md`):

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

[cc-memory]: https://code.claude.com/docs/en/memory

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

## Before you change an area, read its doc
<one line per task area that HAS a deeper doc, naming the file to read before that kind of
change — e.g. "authorization or a new policy → docs/authorization.md", "billing, plans or
webhooks → docs/billing.md". List ONLY files that exist (`ls` them); never invent a doc to fill
a row, and an empty section is a valid answer. The doc holds the detail, this line only routes to
it, so a CSS change never loads the billing contract. A `.claude/rules/` rule (§2b) fires when a
matching FILE is read or edited; this line fires on the TASK, before any file is opened —
use both where an area has both.>

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

<!-- emit-if: database -->
## Test-run preflight
Before a full suite or e2e run, check the environment, because it fails as a red suite that is not the code's fault:
the database is up (`pg_isready` for Postgres; start it and re-check if it is not), `ls` every spec path you name,
no held `bundler.lock` (a Ruby LSP `bundle update` holds it), and read `uptime` — under high load run in the
foreground or in smaller shards, never many background runs. Never swap hooks or config from another branch while
a sweep runs. *Advice, not enforced: the rails-flow `test-preflight` hook reports the first four as an advisory;
run the project's own checks yourself before the suite: the hook never runs a script from the repository.*
<!-- /emit-if -->

## How to work with me
Act as an advisor, not an assistant. Default to scrutiny.
- **Scope.** Full protocol for decisions, architecture, root-cause claims, estimates, plans, and
  anything going to a named third party. For syntax, lookups and small fixes: answer directly, and
  flag risk only if the approach itself is wrong.
- **Lead with the most consequential point**, especially the unwelcome one. If my premise is
  flawed, say so before answering; if it holds, say "premise holds" and move on. **Do not
  manufacture disagreement.**
- **Label a claim where the label changes what I'd do**: `[Verified]` (checked against docs, a
  search or a file this session) · `[Recall]` (training; may be stale) · `[Inferred]` · `[Guess]`.
  If most of an answer is `[Recall]`/`[Guess]`, say so in line one. Name the version you assume for
  any framework API — Rails, Hotwire, a gem — and treat it as `[Recall]` until verified. If a
  method may not exist as written, say so rather than producing plausible syntax.
- **Disagreement has a shape**: "I disagree because X. Instead: Y. The risk in yours: Z. What would
  change my mind: E." Update on evidence, never on repetition or seniority; if you change position,
  name what changed it.
- **Blast radius before steps** for migrations, destructive commands, and anything touching
  production data. Reversibility over elegance.
- **Open with the answer** or the most consequential point, end on the call or one named next
  step, and state what you're confident about without hedging.

## Context is billed on every turn
- Everything in this file is re-read every session, and a `SessionStart` hook re-fires **after every
  compaction** — into the window the compaction just reclaimed. What it prints is charged each time.
- **A subagent's answer lands in this conversation and stays there** for the rest of the session. A
  verbose agent is paid for once and billed on every later request: ask for findings, not the
  narration of the search; a path to a written report, not the report pasted back.
- **Test every line you emit**: if I ignore this line, what changes? A count and a pointer beat a
  list that grows without bound. Do not restate what I already have — my question, the file you
  just read, the diff I gave you.
- When a task is done and the next is unrelated, say so rather than carrying the whole thread on.

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
<numbered rules distilled from the above, each with its reason — always include:>
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
AGENTS routing → the rails-flow plugin agents · GUARDRAILS.md · docs/brain/MEMORY.md · `/rails-flow:handoff` (the work order for another session or an executor)
```

**The test-run preflight block is conditional (#1561).** The block between `<!-- emit-if: database -->` and `<!-- /emit-if -->` is written only when
the project has a database (Step 1's inspection finds `config/database.yml` or a database gem); with none, write nothing for it. Either way the two
marker lines are dropped, never copied into the project's CLAUDE.md. It is advice (tier 1); the `test-preflight` hook (#1566) is its advisory,
deterministic half, and a project's own preflight is the project's to run before the suite: a PreToolUse hook runs before the user is asked about the command, so the hook
executes nothing a repository supplies (#1821 keeps the removed project hook point). Every line of it is
re-read every session, so it stays this short.

## 2b. Area- or mode-specific instructions belong in `.claude/rules/`

### CLAUDE.md structure — audit, then relocate (never summarise)

`CLAUDE.md` is loaded by every session, so every line is paid for on every turn — and it accretes: a
fact lands beside the rule it explains, then the incident, then the issue number, until the file is
mostly the story of how it came to say what it says. The fix is **not** compression: a summarised rule
loses the reasoning that made an agent follow it. Run the shipped analyser:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_structure.py" --report CLAUDE.md
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_structure.py" --propose CLAUDE.md   # a diff; writes nothing
```

`--report` says what the file is made of (rule / history / mixed / structure paragraphs, the share of
words that are incident narrative, whether a "start here" checklist sits near the top) and reads the
ceiling marker. `--propose` prints the diff that moves every pure-history paragraph **verbatim** to
`docs/brain/claude-md-history.md` — the project's in-repo memory — under a heading naming the section it
came from, leaving one pointer line per section; it refuses if any paragraph would not survive
byte-for-byte. `mixed` paragraphs (a rule leaning on its incident) are listed for a human to split. Show
the diff; apply with `--write` only on approval. Then record the ceiling **at the measured size**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_structure.py" --set-ceiling CLAUDE.md --write
```

That writes `<!-- claude-md: max-lines N -->` into the file — a ratchet, lowered when the file shrinks,
raised only in a change that says why. `project_gates.py`'s `claude-md-structure` check enforces it from
then on and reports **not applicable** until it is set: a ceiling nobody recorded is not a pass. Building
a `CLAUDE.md` from nothing is the same path on an empty file: a checklist first, rules next, history in
the brain. The history file is not a memo: give it one line in `docs/brain/MEMORY.md` so `brain-review`'s
index hygiene does not read it as an orphan.

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
**only when Claude uses the Read, Write or Edit tool on a matching file** (Write and Edit since Claude Code 2.1.288; before that, only Read) — so it costs nothing on sessions that never touch
that area. A rule with no `paths:` loads every session, same as `CLAUDE.md`; use that only for
genuinely global content.

`claude_md_structure.py --report` lists the rule paragraphs that apply to one area as candidates for such a
rule, with the `paths:` glob each would carry (#927) — the third lever when the ceiling bites, after relocating
history and before raising the ceiling.

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
force-push, no `git add -A`, no `--no-verify`, stage specific files, small logical commits; never report a placeholder SHA — after pushing run
`git rev-parse HEAD` and report that exact value; make `gh pr ready` and any merge depend on the sweep result with `&&` (`run_sweep && gh pr ready`), never `;`),
**Secrets** (credentials only; never commit .env), **Deploys** (require explicit user
approval). Note at the top: *the rails-flow hooks enforce these mechanically inside a trusted workspace (a repository's own settings can switch hooks off, #1843); this document
is the human-readable law they implement.*

**Ask, and record the answer: is the test database seeded on purpose? (#1734)** *"Does this project's
suite expect a seeded test database, with a CI script that resets it (`config/ci.rb` running
`db:reset`)?"* The default is **no**, and it needs no line: the guard refuses `db:reset` because
seeds break test isolation for a suite that expects an empty database. A project whose suite needs
the seed rows (Retask's `Setting` rows are part of its test contract) answers yes, and
GUARDRAILS.md gets its own line:

```markdown
- test-db-seeded: yes
```

`guard-bash.sh` reads exactly that line. It then allows ONE command, `RAILS_ENV=test bin/rails
db:reset`, run alone. A development or production reset, a compound command, and a payload the
hook cannot read are still refused, and a project that declares nothing is refused with the name of
its CI script (`bin/ci`, else `config/ci.rb`) in the message. Prose that merely mentions the key,
and an example of the line inside a code block or an HTML comment, do not declare it.

**Ask, and record the answer: the mock-up gate (#1376).** *"Does a change a user can see wait for
your approval of a clickable mock-up before it is built?"* The default is **yes**, and it needs no
line. A team with no one to approve designs answers no, and GUARDRAILS.md gets its own line:

```markdown
- mockup-gate: off
```

`check_mockup_gate.py` reads exactly that line. Undeclared means ON, and prose that merely mentions
the key does not turn it off.

With the gate on, **every issue template gets a Mock-up section**: feature, enhancement and bug.
The trigger is UI impact, not the label. Propose adding this field to each form under
`.github/ISSUE_TEMPLATE/`, and write it only once the owner approves the diff:

```yaml
  - type: textarea
    id: mockup
    attributes:
      label: Mock-up
      description: >
        Does resolving this change what a user sees? If yes, link a clickable mock-up covering a
        phone width and a desktop width, with the empty and error states. If no, write
        "no visible change".
    validations:
      required: true
```

A form only binds the web UI. An agent filing with `gh issue create` skips it, so an agent writes the
same `## Mock-up` section into the body itself, and `check_issue_mockup.py` checks the body
whichever way it was filed.

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
- **`memos/<type>/<slug>.md`** — one lesson or decision each (`memos/feedback/`, `memos/decision/`);
  the type is the directory. A memo at the brain root is misplaced — `brain-sync local --status` names
  the path it belongs at; move it and fix its index line.
- **`MEMORY.md`** — one-line index of the memos (link + 8–15 word summary); the SessionStart hook
  injects its top into every session.

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

## 4a. Ask which memory systems load, and RECORD the answer (#1181)

The brain is one of up to **three** memory systems that inject into every session, and none knows
about the others: Claude Code's **auto-memory** (on by default; its `MEMORY.md` index, first 200
lines or 25KB, whichever comes first, and nothing past that is loaded; `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/check_memory_index.py"` measures it, and the SessionStart hook says so when it is near), the **`remember`** plugin (a day's log and a handoff), and this brain. Each costs
tokens at every session start and again after every compaction. Measured on one repository they were
~3,800, ~5,700 and ~520 tokens — and the largest was a handoff another session had written.

**Ask the user which ones this project loads, and write the answer down.** Running two can be
deliberate, so there is no default to impose; what can be checked is that what loads matches what was
chosen:

```json
{"memory": ["auto-memory", "rails-flow-brain"]}
```

in `.rails-flow/memory.json` — any of `auto-memory`, `remember`, `rails-flow-brain`. `[]` is a
decision (load none), not the same as no file (nobody decided).

**Then hold it in the COMMITTED settings, explicitly**, because Claude Code applies a key set at a
higher scope over the same key lower down, and a project that says nothing inherits each user's
global choice. In `.claude/settings.json`:

- `remember` not chosen → `"enabledPlugins": {"remember@claude-plugins-official": false}`; chosen → `true`.
- `auto-memory` not chosen → `"autoMemoryEnabled": false` (leaving it out leaves it **on**).
- `rails-flow-brain` not chosen → do not scaffold `docs/brain/MEMORY.md`; the SessionStart hook prints
  it whenever it exists.

`project_gates` checks the three against the recorded choice (`memory-systems`): a mismatch **fails**,
no recorded choice is **not applicable** — never a pass. The check runs on demand and in CI only, so it
adds nothing to any session.

## 4b. The docs/ layout — one home per kind (#886)

`docs/` is where agents litter: with no map, every session invents a place, and nothing can say a
file is misplaced. The layout is fixed and the rule is one sentence — **a file's directory answers
the question a reader would ask to find it**; code goes in `scripts/`, never in `docs/`; a script's
output goes under a directory marked `.generated`; binaries go under `design/assets/` or `evidence/`;
memos go under `brain/memos/<type>/`.

| directory | question | holds |
|---|---|---|
| `product/` | WHAT are we building? | spec, roadmap, routes, `features/F-NN-*.md`, `roles/`, `acceptance/` |
| `design/` | WHAT does it look like? | briefs, prompts, UI decisions; `assets/` beneath it |
| `architecture/` | HOW is it built? | **generated** by `/rails-flow:graph`; never hand-edited |
| `runbooks/` | HOW do I operate it? | setup, deploy, on-call, integrations |
| `evidence/` | WHAT did we measure? | spikes, screenshots, coverage, validation — dated, immutable |
| `wiki/` | WHERE is the reference? | **generated** pages + hand-written pages left alone |
| `brain/` | WHAT did we learn and decide? | STATUS, DECISIONS, HYPOTHESES, PROGRESS-LOG, MEMORY, `memos/<type>/` |

A project may declare one more directory by adding a row to `docs/README.md`'s table; the tool honours
a declared row and homes an undeclared directory by its name. Run, in this order:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docs_layout.py" --report              # every file classified; the findings
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docs_layout.py" --propose             # the moves AND the link rewrites, as a diff
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docs_layout.py" --propose --write     # apply; every rewritten link is asserted to resolve
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docs_layout.py" --scaffold --write    # the map, the directory READMEs, the generated markers — only what is missing
```

Show the user the `--propose` output before `--write`: a line marked `unsure -- confirm` is a file the
name could not place, and a `REFUSED` line is a move whose reference lives in a binary the tool cannot
rewrite. Files move byte-for-byte; only path strings are rewritten — in `CLAUDE.md`, `GUARDRAILS.md`,
`loop.md`, `README.md` and every doc. Code found in `docs/` is reported, never moved: it leaves for
`scripts/` by your hand. On a new project, `--scaffold --write` alone lays the map down.

## 5. Knowledge-graph integration (only if graph tools are present)

Detect with `command -v code-review-graph` and `command -v graphify`. Skip absent
tools silently. For code-review-graph, wire it to coexist with the rails-flow hooks:

1. **Protect authored files.** Its installer rewrites AGENTS.md/GEMINI.md/.cursorrules.
   Require a clean git state before `code-review-graph install`; afterwards run
   `git status` and restore any hand-authored file it clobbered
   (`git restore -- AGENTS.md`). Never gitignore an authored AGENTS.md.
2. **Three-file settings pattern.** Keep `.claude/settings.json` permissions-only.
   **Never template `autoMode`, or a `permissions.defaultMode` of `auto` or `bypassPermissions`, into any of these
   project files** (#1827): the auto-mode page says the classifier "doesn't read `autoMode` from project settings",
   and the permission-modes page says such a `defaultMode` "doesn't take effect". They belong in the owner's
   `~/.claude/settings.json`; recommend `/auto-mode-setup` as an owner step. A project can check itself with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_project_settings.py"`.
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
2b. **Optional: a status line and owner checkpoints** (#1829; never edit a real settings file, a project opts in). **Status line:** vendor the one file and point
   `statusLine` at the copy. `${CLAUDE_PLUGIN_ROOT}` resolves only in the fields the plugins reference lists under "Where each variable resolves" (a plugin's hook and
   monitor commands, MCP and LSP server fields, and skill, command and agent content); a `statusLine` command is not among them, so it cannot name the plugin:

   ```bash
   mkdir -p .claude/scripts && cp "${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py" .claude/scripts/statusline.py
   ```

   then, in `.claude/settings.example.json` (teammates copy it to the gitignored `.claude/settings.local.json`):

   ```json
   {"statusLine": {"type": "command", "command": "python3 \"$(git rev-parse --show-toplevel)/.claude/scripts/statusline.py\"", "refreshInterval": 30}}
   ```

   It prints `5h N% · 7d N% · ctx N% · $N · effort` and the branch and worktree, amber from 80%, and leaves out any field the payload lacks. A window whose `resets_at` has
   passed is left out (#1854). The status line page says a script that exits non-zero or prints nothing "cause[s] the status line to go blank", so a failure costs one blank
   line. `refreshInterval` 30 keeps the figures current while the session is idle (the page: "The minimum is `1`").
   **Owner checkpoints:** `permissions.ask` rules force a prompt for the owner-only actions, even in auto mode (the auto-mode page: they are "evaluated before the
   classifier and always force a permission prompt"):

   ```json
   {"permissions": {"ask": ["Bash(gh pr merge *)", "Bash(kamal deploy *)"]}}
   ```

   The page states the limit, and so do we: a rule matches commands that BEGIN with its text, so a merge or deploy written another way (`gh -R x pr merge`, a `bash -c`
   string) "doesn't match the rule, so it isn't checkpointed"; the guard hooks and the git shim stay the backstop. `gh pr merge *` and `kamal deploy *` are our own
   examples in the page's shape, not rules the page lists.
   **A lane denied by auto mode:** open `/permissions`, select the **Recently denied** tab, and "Press `r` on a denied action to mark it for retry" (the page continues: when you exit the dialog, Claude Code tells the model it may retry that tool call).
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
   cannot see). **Copy the shipped file; do not retype it.** The hook reads git's three arguments
   as positional parameters (dollar-one to dollar-three), and Claude Code replaces a dollar sign
   followed by a digit in a command's own markdown with the arguments the command was invoked with
   (skills docs, "Available string substitutions"), so a hook printed here and run as
   `/rails-flow:setup-flow audit` was written with the argument words in place of the
   parameters and never fired (#2022). `scripts/lint_markdown_shell.py` now refuses a bare
   dollar-digit in a command's shell block. `chmod +x` after copying:

   ```bash
   cp "${CLAUDE_PLUGIN_ROOT}/templates/post-checkout-graph.sh" .git/hooks/post-checkout
   chmod +x .git/hooks/post-checkout
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
`config/routes.rb`, `app/**` and `db/schema.rb` (and every other project-owned `db/*_schema.rb`) into `docs/architecture/graph.json`, a
self-contained `index.html` (inline CSS/JS, zero external requests — opens from disk
offline) and a mermaid `graph.md` for GitHub. One artefact, three consumers: humans get a
picture, agents get structural context without reading the whole codebase, and qa-flow gets
reverse dependencies for a computed blast radius.

Offer to generate it now (it needs nothing installed beyond `python3`) and, if the project
has a hosted CI, propose the drift guard in §8. Don't force it — but do say plainly why it
beats a hand-drawn diagram: this one is regenerated at session end and at release, and CI
fails when the code moves and the graph does not.

## 6c. The project wiki (`docs/wiki/`) — generated reference, rebuilt at ship (#887)

A hand-written reference is a transcription, and transcriptions rot. The reference pages are a join
over structured sources — the architecture graph, `db/schema.rb` (and every other project-owned `db/*_schema.rb`), `config/queue.yml`,
`config/recurring.yml`, `Gemfile.lock`, `package.json` — so they cannot drift silently: every count on
a page is asserted against its source's total, every page names the graph's commit, and `--check`
fails the `project-wiki-drift` check when a source moved and the pages did not.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_project_wiki.py"            # Architecture, Routes, Data-Model, Jobs-And-Queues, Components, Dependencies, _Sidebar
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_project_wiki.py" --check    # DRIFT if the committed pages are not a clean build
```

`Home.md` is hand-written: seeded once, never overwritten — the one page that says what the system is
for. The `doc-updater` agent rebuilds the wiki whenever it regenerates the graph, and both are committed
with the change that moved them; nothing runs on a schedule. Not applicable is exit 3: no graph yet
(`/rails-flow:graph` first), or `--check` before the first build.

## 6d. In-app Help & SOP (`docs/product/help/`) — the user's manual, generated from the repo (#934)

The interface carries the name, the unit, the state and the action; the explanation lives in Help. Help is
authored as markdown beside the spec (procedures, rules, glossary, one guide per screen — each citing its
section), joined with `docs/product/help/registry.json` (the app's own dump of its settings, permissions and
screens, written by a rake task), and built into `docs/product/help/_build/help.json`, which the app renders
read-only with the release it describes. `reference/help.md` has the layout, the registry shape and the
rake skeleton.

```bash
bin/rails help:registry                                          # the app writes docs/product/help/registry.json from its own registries (reference/help.md)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_help.py"            # build docs/product/help/_build/help.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_help.py" --check    # DRIFT if the committed build is not clean
```

A screen with no guide, a procedure with no `spec:`, a setting or permission with no description, or a
build that no longer matches its sources is a PROBLEM — the `help-drift` check. Not applicable is exit 3:
no registry yet, or `--check` before the first build.

**Publishing to the GitHub wiki is opt-in and off by default.** The pages live in the repo where the
gates can reach them. If the user wants them on the wiki tab, add `.github/workflows/wiki.yml` — on a
push to `main` touching `docs/wiki/**`, clone `<repo>.wiki.git`, copy `docs/wiki/*` over it, commit and
push. The wiki repository must exist first: GitHub creates it only when the first page is saved in the
web UI, and no API call can do it — say so when offering the template.

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

### The stack's own repairs come from its plugin (#2180)

Each detected (or chosen) stack's plugin ships its own repairs: the gems, initializers, test wiring and boundaries only that
stack has. §0 printed them as `setup_sections`. **Read each file and work it in turn, here**, as approved diffs, the same way
as everything above. Rails' (`rails-stack`) is `setup/rails.md`. A stack whose plugin declares no section has nothing to add.

### Declare the issue labels, so an issue filed from the shell is labelled (#1311)

Issue templates apply labels only through the GitHub web form. An agent files with `gh issue create`,
which skips the template, so without a declaration its issues arrive bare. **Read the repository's
labels** (`gh label list --limit 200`) and **ask which groups every issue must carry.** For example:
one type (`bug` / `feature` / `enhancement`), and a severity when it is a bug. Record them:

```json
{"groups": [
  {"one_of": ["bug", "feature", "enhancement"]},
  {"when": "bug", "one_of": ["severity:s1", "severity:s2", "severity:s3", "severity:s4"]}
]}
```

Save it as `.rails-flow/issue-labels.json`. A value ending in `*` is a prefix (`comp:*`). rails-flow's
`guard-bash` hook then refuses a `gh issue create` that misses a group, and names what is allowed.
Undeclared, it still refuses an issue with no label at all.

**Then install the server-side labeller, which sees the issue however it was filed (#1791).** The hook reads command text, which a
shell only gives meaning when it expands it, so it cannot catch every spelling; GitHub sees the issue itself. Copy
`${CLAUDE_PLUGIN_ROOT}/scripts/label_new_issue.py` to `.github/scripts/` and `${CLAUDE_PLUGIN_ROOT}/templates/label-new-issues.yml` to
`.github/workflows/` (its `actions/checkout` is already pinned to a commit SHA; keep it pinned when you update it), and commit both. An issue missing a declared group then gets a
`needs-labels` label and one comment naming what is missing (it guesses no label). An `issues` workflow runs from the default
branch, so it starts when that commit is on it. Ask first: it adds a workflow and a label to the repository.

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
- **With several PRs open at once, the committed graph and wiki conflict on every one of them**:
  each branch regenerates them, and every merge re-conflicts the rest (#1230). Offer the opt-in
  policy: `.rails-flow/generated-docs.json` with `{"enforce_on": ["dev", "main", "chore/docs-refresh-*"]}`.
  With it, a stale graph or wiki fails only on those branches and is a `NOTE:` elsewhere;
  `generated-paths-untouched` then fails any other branch whose diff touches `docs/architecture/` or
  `docs/wiki/`, and the docs are regenerated once after a merge batch on a `chore/docs-refresh-*`
  branch. Vendor `generated_docs.py` beside `architecture_graph.py`, or the vendored copy keeps the
  enforce-everywhere behaviour. No file means today's behaviour, so ask rather than assume.

## 8a. The promotion merges, never squashes — make it a ruleset (#895)

A `dev → main` promotion must be a **merge commit**. A squash keeps dev's content and drops its
ancestry, so the merge base falls back and the **next** promotion cannot merge at all — phantom
conflicts on files nobody edited twice. `gh pr merge --merge` is the rule; the Merge button's default
is whatever the repository allows, and a human is not bound by a command doc. So the rule is a ruleset:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/branch_rulesets.py" --check     # the release branch: PRs merge only, no deletion, no force-push
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/branch_rulesets.py" --apply     # create it when NONE covers the branch — after the user says so
```

`--check` is the `branch-ruleset` check. **Not applicable is exit 3, never a pass**: no `gh`, `gh` not
authenticated, `origin` not on GitHub, or the API unreachable. `--apply` changes what the Merge button
offers on the user's repository — a public blast radius — so run it only after the user confirms, and
never on a ruleset someone else owns: a partial one is reported with the pieces to add and left alone.
PRs into `dev` keep whatever method the team uses; only the release branch is constrained.

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

## 8c. Prove the toolchain's gates can still fail (#1109)

Run it **here, at setup, and again after any toolchain upgrade** — the two moments the answer can
change:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_toolchain_mutations.py"
```

**Not in the per-run gate sweep, and that is the design.** A mutation catches nothing while you
work: it proves a property of the *checker*, which moves when the toolchain or the environment
moves, never when you edit your app. Upstream the full sweep is 438 of 475 seconds; spending that
on every merge to re-check somebody else's code would be cost without a case.

**It is a different question from `toolchain-selftests`**, which runs on every sweep. That one asks
*does this gate still discriminate here*. This asks *would its fixtures still notice if the gate
broke* — a selftest that passes against a deliberately broken checker has stopped guarding, and
looks identical to a healthy one from outside. Four gates written in a single day upstream were
partly vacuous and every one passed its own fixtures; only mutation testing found them.

Guards that span plugins stay in the marketplace and are **not** covered here — a project that
installed one plugin could not verify a cross-plugin claim anyway. That limit is reported, not
hidden.

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

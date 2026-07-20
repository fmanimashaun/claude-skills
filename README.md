# Claude Skills — Rails 8 & Hotwire

Opinionated [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that teach Claude to build full-stack **Ruby on Rails 8.1** applications the
way I build them. Drop them into a project and Claude Code (or claude.ai)
picks them up automatically whenever the task is Rails or Hotwire.

## The skills

| Skill | What it encodes | References |
|---|---|---|
| **`rails-8`** | The full Rails 8.1.x doctrine: vanilla-first stack (built-in auth, Solid Queue/Cache/Cable, Propshaft + importmap, Kamal 2), models → controllers → views workflow, **pure RSpec** testing (no Minitest, no matcher add-ons), OpenAPI docs via rswag, AI features via ruby_llm, observability, advanced Active Record, ecosystem gems | 16 reference files |
| **`hotwire`** | The Hotwire stack from the official handbooks: Turbo 8 (Drive, morphing refreshes, Frames, Streams), Stimulus 3.2 (full controller reference), and **Hotwire Native** (iOS/Android shells, path configuration, bridge components) | 3 reference files |

They cross-reference each other — install both for Rails work.

### House rules baked in

- Rails **8.1.x**, "the Rails way": convention over configuration, server-rendered HTML, one-person-framework defaults.
- **Testing is RSpec only.** Apps are scaffolded with `rails new --skip-test`; the stack is rspec-rails + FactoryBot + Faker + Capybara + SimpleCov + WebMock/VCR, with pure RSpec matchers (no shoulda-matchers).
- **No gems from categories Rails 8 eliminated**: the built-in authentication generator (not auth engines), Solid Queue (not external job backends), Solid Cache/Cable (not Redis).
- REST APIs are documented with **OpenAPI** — rswag as the test-driven default.
- AI/LLM features use **ruby_llm** (chat, tools, structured output, embeddings, `acts_as_chat`).
- Deployment is **Kamal 2** on plain servers.

## The agentic flow — `rails-flow`

The skills give Claude the *knowledge*; the **rails-flow** plugin encodes the *process* —
an orchestrated development flow for any Rails 8 project, following Anthropic's
orchestrator-workers and evaluator-optimizer patterns.

**Commands** (namespaced): `/rails-flow:setup-flow` scaffolds CLAUDE.md, GUARDRAILS.md and
the `docs/brain/` memory system into a project · `/rails-flow:feature <desc>` runs the full
loop — plan (delegated exploration) → feature branch off `dev` → spec-first implementation
(the failing spec that proves the NEW behavior comes before the code) → mandatory gates
(code review, full green suite, security + design audits when relevant) → PR → non-skippable
tool-gated merge review (code-review-graph's review-pr skill when its CLI + graph are
present, the bundled pr-reviewer agent otherwise) · `/rails-flow:fix` works a bug or a phased review backlog one
proven issue at a time · `/rails-flow:review` runs seven parallel specialist passes and
writes a phased, fix-consumable report · `/rails-flow:brain` institutionalizes lessons as
indexed memory memos · `/rails-flow:issues` triages open repo issues (bug / feature /
chore / needs-info) and works them one at a time through the matching pipeline, each
PR auto-closing its issue · `/rails-flow:pr-comments` sweeps a PR's review feedback —
every actionable comment is fixed on-branch or folded into a tracked issue, and **no
next task starts until the current PR closes clean**.

**Agents** (8): rails-developer, migration-writer, code-reviewer, test-runner,
security-auditor, design-auditor, doc-updater, pr-reviewer — each context-isolated, tool-
restricted, and judged against the *project's* CLAUDE.md overrides, not generic taste.

**Hooks** (the mandatory layer — advisory prose can be forgotten, hooks cannot):
PreToolUse blocks `db:reset`, force-pushes, `git add -A`, `--no-verify` and unapproved
deploys · PostToolUse auto-runs rubocop on edited Ruby files · Stop refuses to finish with
behavioral changes that lack a proving spec, or with red changed specs · SessionStart
injects branch state and the memory index. After installing, restart Claude Code (or
`/reload-plugins`) so hooks register. Hook scripts are
bash — on Windows, run Claude Code inside WSL or Git Bash.

### Autonomous operation — `/goal` and `/loop`

Two native Claude Code primitives turn the flow into an unattended system, and they
divide cleanly: **`/goal` works turn after turn until a condition is met; `/loop` runs a
prompt on a recurring interval.** Reaching for `/loop` when you mean `/goal` is the
common mistake.

The backlog grinder is a goal, not a poll — after `/rails-flow:review` writes its
phased report:

```
/goal all phases in docs/reviews/<date>-codebase-review.md are marked done —
work them with /rails-flow:fix, one phase at a time
```

Genuinely loop-shaped jobs: a **PR babysitter** when `/feature` stops after CLEAN on a
default-branch base (`/loop "Check PR #42: if CI failed, fix on the branch and push;
address review comments; if merged say MERGED" --interval 10m --expires 8h`); a **drift
watchdog** that pulls `dev` and runs the suite fail-fast every 30–60 minutes to catch
breakage arriving from outside your session; and a periodic **security sweep**
(bundler-audit + Brakeman, new findings only). Loops are session-scoped with a 1-minute
minimum interval and 3-day maximum window — always set `--expires`, and use `/cost` to
watch spend.

`/rails-flow:setup-flow` also scaffolds a project `loop.md`, which replaces the
built-in prompt for bare `/loop` — so `/loop` with no arguments runs the project's own
maintenance pass (suite health, lint drift, security deltas, graph freshness; deltas
reported only).

Autonomy stays safe **because** of the hooks, not despite them: an unattended 2 a.m.
iteration cannot `db:reset`, force-push, or deploy; the stop gate refuses turns with
unproven behavioral changes; and nothing merges past `dev` without a CLEAN verdict
from the review gate.

### Adding tool-gated code review (optional, recommended)

The merge gate has two tiers. Out of the box, the bundled `pr-reviewer` agent reviews
every PR and nothing merges without its `VERDICT: CLEAN`. When
[code-review-graph](https://github.com/tirth8205/code-review-graph) is present, the gate
upgrades: its `review-pr` skill reviews the PR against a Tree-sitter knowledge graph of
the codebase — blast-radius analysis of every changed function's callers — with
`code-review-graph impact` cited as evidence.

code-review-graph is **not** installed from this marketplace. Since v2.x it is a pip
CLI that configures each project directly. The runbook below goes zero → verified-
functional; every phase ends with a check that proves the layer it set up actually
works, so a failure surfaces at its own step instead of as mystery breakage later.

#### Phase 0 — Prerequisites (once per machine)

```bash
python3 --version          # expect 3.10+
pipx --version             # or use pip / uv below
cd /path/to/your-project
git status                 # REQUIRED: clean working tree before Phase 2
```

A dirty tree is a hard stop — the installer rewrites files, and a clean state is your
only cheap undo.

#### Phase 1 — Install the CLI + embeddings (once per machine)

```bash
pipx install code-review-graph
pipx inject code-review-graph sentence-transformers
```

The inject supplies the optional embeddings extra (sentence-transformers → PyTorch,
~200 MB). Without it, `code-review-graph embed` fails with *"local embedding provider
needs sentence-transformers"*. pipx keeps each tool in an isolated venv, so the library
must go **into that venv** — a plain `pip install sentence-transformers` elsewhere will
not be seen. Injected packages survive `pipx upgrade` and `pipx reinstall`.

Not using pipx:

```bash
pip install 'code-review-graph[embeddings]'        # QUOTE the brackets — zsh globs []
uv tool install 'code-review-graph[embeddings]' --force
```

Keep the default **local** embedding provider for private code: the `openai` /
`google` / `minimax` providers send your code's symbol text to external APIs.

**Verify:** `which code-review-graph` resolves (pipx: via `~/.local/bin`), and
`code-review-graph --version` prints a version.

#### Phase 2 — Project install + damage triage (once per repo)

```bash
code-review-graph install
git status
```

Expected new/modified files: `.mcp.json`, `.claude/skills/`, hook changes in
`.claude/settings.json`, a git pre-commit hook, `.gitignore` additions — plus IDE noise
(`AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.opencode.json`, …).

**Triage immediately:** if the repo has a hand-authored `AGENTS.md` or `CLAUDE.md` and
the diff shows it rewritten, restore it now (`git checkout -- AGENTS.md`). Gitignore the
IDE noise you don't use — but never an authored `AGENTS.md`.

#### Phase 3 — Build, embed, and prove the CLI layer

```bash
code-review-graph build
```

Expected: `Full build: N files, N nodes, N edges` — nonzero everything.

```bash
code-review-graph embed    # first run: model download + full-graph pass (slow once)
code-review-graph status
```

Expected from `status` — the key check: node/edge counts matching the build, a fresh
`Last updated` timestamp, and `Languages:` **including `ruby`**. If ruby is missing,
the graph parsed nothing useful and everything downstream is theater — usually a
`.code-review-graphignore` that is too broad.

Prove queries answer with real code, no Claude involved:

```bash
code-review-graph search User                        # any class you know exists
code-review-graph query --pattern callers_of --target some_real_method
code-review-graph impact app/models/something.rb
time code-review-graph update --skip-flows           # expect well under ~2s
time code-review-graph embed                         # second run: fast, incremental
```

Each returns structured `file:line` hits. `search` returning nothing for a class you
know exists means the graph is broken regardless of what `status` says.

#### Phase 4 — MCP wiring check (the pipx blind spot)

```bash
cat .mcp.json
```

The MCP server embeds your *queries* at search time, so it needs the library too. If
`command` points at your pipx/venv binary, the inject covers it. If it is `uvx`, the
server runs in an ephemeral environment that will NOT see the inject — semantic search
silently degrades. Fix: set `args` to
`["--with", "code-review-graph[embeddings]", "code-review-graph", "serve"]`, or point
`command` at the pipx binary (`which code-review-graph`). Interpreter paths are
hardcoded at install time — re-run `code-review-graph install` after environment
changes.

#### Phase 5 — Claude Code bring-up

Fully **quit and reopen** Claude Code — `/reload-plugins` is not enough; `.mcp.json` is
read only at startup. Then, in the project:

1. `/doctor` → expected: no plugin errors (rails-flow stays clean too)
2. `/mcp` → expected: `code-review-graph` listed as connected
3. Type `/review` and pause → expected: `review-pr`, `review-delta`, `review-changes`
   in the completion list

#### Phase 6 — Functional smoke test inside Claude

Ask about *real* symbols and watch the tool-call line:

- *"Where is `SomeService` defined?"* → expected: `semantic_search_nodes_tool`,
  answer with `file:line`, **no grep**
- *"Who calls `some_real_method`?"* → expected: `query_graph_tool` with `callers_of`
- *"What breaks if I change `app/models/x.rb`?"* → expected:
  `get_impact_radius_tool` with node/file counts and a risk rating

grep firing where a graph tool should means the wiring failed even though everything
"installed".

#### Phase 7 — Coexistence wiring + freshness probes

Run `/rails-flow:setup-flow` (CRG-aware since rails-flow 1.0.2): it moves graph updates
from per-edit hooks to a PID-guarded Stop hook (per-edit stays rubocop-only, so the two
never contend), empties the installer's PostToolUse hooks, applies the `CRG_TOOLS`
8-tool allow-list (~70% schema reduction; the 33k-token architecture-overview tool
becomes uncallable), and adds a post-commit updater so terminal commits don't stale the
graph.

Then two liveness probes, both read from `code-review-graph status`:

1. Have Claude make any trivial edit and finish its turn → `Last updated` advanced
   (Stop hook alive)
2. Make a small commit from the terminal, wait a few seconds → timestamp advanced
   again (post-commit hook alive)

Final integration test: a tiny `/rails-flow:feature` on a throwaway branch — the merge
gate should announce it is using the `review-pr` skill rather than falling back to
`pr-reviewer`.

Ruby is a first-class parsed language. Expect strong blast-radius analysis on service
objects, jobs, and explicit call chains; weaker coverage of Rails metaprogramming
(association-generated methods, dynamic abilities) — grep remains the fallback there.

#### Optional: graphify (second graph — exploration and cross-repo)

[graphify](https://github.com/safishamsi/graphify) complements CRG rather than
competing with it: CRG answers *"where is X / who calls X / what breaks"* with
embedding precision; graphify answers *"how does this fit together"* — BFS
neighborhood exploration, `graphify path A B` hop-chains (~200 tokens), Leiden
community reports with Obsidian wikilinks, and — uniquely — `graphify merge-graphs`
across repositories, where bridge nodes in the merged view are your highest-impact
shared code. Ruby is first-class: a dedicated extractor covers classes, methods,
singleton methods, and member-call resolution.

```bash
pipx install graphifyy            # two y's on PyPI; the CLI is `graphify`
cd your-rails-project
# create .graphifyignore first (node_modules, vendor, tmp, log, graphify-out/, …)
graphify update .                 # AST-only build, zero LLM tokens
graphify hook install             # post-commit + post-checkout freshness
```

Two hard rules. **Never put graphify in a Claude hook** (Stop/PostToolUse): its
~10s update piles up per-turn — CRG's sub-second update owns the Claude-hook slot;
graphify updates only via its git hooks (add a resource guard: skip when CPU >50%
or free memory <2GB). And teach the fallback chain in CLAUDE.md so a CRG semantic
miss doesn't fall straight to grep:

```
CRG 0 results → graphify query '<term>' --graph graphify-out/graph.json → grep
```

It's v0.9.x (pre-1.0, MIT) — expect some churn; each piece degrades gracefully if
uninstalled.

## Repository layout

```
claude-skills/
├── skills/
│   ├── rails-8/          # SKILL.md + references/  (source of truth)
│   └── hotwire/          # SKILL.md + references/
├── plugins/
│   └── rails-flow/       # agentic flow plugin: commands + agents + hooks
├── dist/
│   ├── rails-8.skill     # zip packages for claude.ai / Claude Desktop upload
│   └── hotwire.skill
└── scripts/
    ├── install.sh        # copy skills into a project or ~/.claude/skills (bash)
    ├── install.ps1       # same, native Windows PowerShell
    ├── package.sh        # rebuild dist/*.skill after editing skills/ (bash)
    └── package.ps1       # same, native Windows PowerShell
```

## Install — Claude Code

Skills are plain folders; installing = putting each skill at
`<location>/skills/<name>/SKILL.md`. Two locations matter:

- **Project**: `<project>/.claude/skills/` — commit it, and everyone (and CI
  agents) working in the repo gets the skills.
- **Personal**: `~/.claude/skills/` — available in all your projects, just for
  you.

### One command, via the plugin marketplace

```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills   # the two skills (knowledge)
/plugin install rails-flow@claude-skills    # the agentic flow (process) — see below
```

Run those inside any Claude Code session. The `rails-stack` plugin bundles
both skills and follows you across projects; manage or remove it later via
`/plugin`. Use the methods below instead when you want the skills *committed
into a specific repo* for your team.

### Into a project (recommended for teams)

macOS / Linux / WSL / Git Bash:

```bash
git clone https://github.com/fmanimashaun/claude-skills.git
cd claude-skills
./scripts/install.sh /path/to/your/project            # both skills
./scripts/install.sh /path/to/your/project rails-8    # just one
```

Windows (native PowerShell — no bash required):

```powershell
git clone https://github.com/fmanimashaun/claude-skills.git
cd claude-skills
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Target C:\path\to\project            # both
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Target C:\path\to\project rails-8    # one
```

(The `-ExecutionPolicy Bypass -File` form sidesteps the blocked-downloaded-script
policy; alternatively run `Unblock-File scripts\*.ps1` once and call them
directly.)

No clone needed — pull the folders straight into the project instead:

```bash
cd /path/to/your/project
npx degit fmanimashaun/claude-skills/skills .claude/skills
```

Then commit:

```bash
git add .claude/skills && git commit -m "Add rails-8 and hotwire Claude skills"
```

### For all your projects (personal)

```bash
./scripts/install.sh --global                                           # bash
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Global    # PowerShell
```

Both land in `~/.claude/skills/` — the same path on every OS (`~` is your
user profile on Windows).

### New Rails project quickstart

```bash
mkdir myapp && cd myapp && git init
npx degit fmanimashaun/claude-skills/skills .claude/skills
claude
# then: "Create a new Rails 8 app in this directory for <what you're building>"
```

The rails-8 skill takes it from there — `rails new --skip-test`, RSpec wiring,
the golden-path workflow.

### Verify

Start (or continue) a Claude Code session in the project and ask
*"What skills are available?"* — or just give it a Rails task; skills
auto-trigger from their descriptions. Notes:

- Edits to already-installed skills are picked up live within a session; if
  the `.claude/skills/` directory itself didn't exist when the session
  started, restart Claude Code once so it can be watched.
- The most common install mistake is nesting one level too deep: the path
  must be `.claude/skills/rails-8/SKILL.md`, not
  `.claude/skills/skills/rails-8/SKILL.md`.

## Install — claude.ai and Claude Desktop

Custom skills are uploaded as zip files, individually per user:

1. Grab `dist/rails-8.skill` and `dist/hotwire.skill` from this repo (or a
   [release](../../releases)).
2. In claude.ai: **Settings → Features → Skills → upload** each file.
   Requires a paid plan (Pro/Max/Team/Enterprise) with **code execution
   enabled**; on Team/Enterprise an admin may need to enable the capability
   first.
3. Uploads are per-user — teammates upload their own copies (or use the
   project install above in Claude Code, which *is* shared via git).

Docs: [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
· [Claude help center](https://support.claude.com).

## Install — Claude Agent SDK / API

The Agent SDK reads the same directories: point `cwd` at a project containing
`.claude/skills/`, include `"user"`/`"project"` in `setting_sources`, and
allow the `Skill` tool. For the raw API, skills upload via the Skills API and
run in the code-execution container. See
[Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills).

## Updating

```bash
cd claude-skills && git pull
./scripts/install.sh /path/to/your/project   # re-copy into each install target
```

On claude.ai, delete the old skill and upload the new `.skill` file. After
editing anything under `skills/`, rebuild the packages with
`./scripts/package.sh` (or `scripts\package.ps1` on Windows).

## Try these prompts

- "Create a new Rails 8 app for a facilities work-order tracker."
- "Add live-updating comments to posts." (Turbo Streams + RSpec)
- "Document the JSON API with OpenAPI." (rswag)
- "Add an AI assistant that can look up work orders." (ruby_llm tools)
- "Wrap this app as an iPhone app with a native submit button." (Hotwire Native)

## Versioning

Skill content is pinned to **Rails 8.1.3**, **Turbo 8.0.23**, **Stimulus
3.2.2**, and **Hotwire Native iOS 1.2.2 / Android 1.2.5**, written July 2026.
The skills instruct Claude to verify versions when the current date is well
past that — but expect a refresh here when Rails 8.2/9 lands.

## License

[MIT](LICENSE) — use, fork, adapt.

# Claude Skills — Rails 8 & Hotwire

Opinionated [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that teach Claude to build full-stack **Ruby on Rails 8.1** applications the
way I build them. Drop them into a project and Claude Code (or claude.ai)
picks them up automatically whenever the task is Rails or Hotwire.


## The system — five plugins, one marketplace

This marketplace ships five plugins that layer into a complete Rails 8 development
lifecycle. Each is independently versioned and installable; together they cover
knowledge → build → test → ship → design.

| Plugin | Role | Key commands |
|--------|------|--------------|
| **rails-stack** | The knowledge — Rails 8 + Hotwire + design-system skills that auto-load when relevant | *(skills, no commands)* |
| **rails-flow** | The build process — orchestrated feature work with hard gates | `/rails-flow:feature` `/fix` `/review` `/issues` `/curate` `/report` `/setup-flow` `/brain` `/brain-review` `/brain-sync` |
| **qa-flow** | Independent QA — black-box testing of the running app, gates dev→main | `/qa-flow:cases` `/qa-flow:functional` `/qa-flow:verify` `/qa-flow:certify` `/qa-flow:setup-qa` |
| **pipeline** | Lifecycle + release — sequences the flows, builds the container, deploys | `/pipeline` `/pipeline:release` `/pipeline:deploy-cloud` `/pipeline:status` `/pipeline:ack` `/pipeline:setup-pipeline` |
| **design-flow** | UI/design — applies the Fidara design system for consistent, modern, responsive UI | `/design-flow:setup` `/design-flow:component` `/design-flow:audit` |

Install `rails-stack` + `rails-flow` for build-only; add `qa-flow` for the independent
quality gate; `pipeline` for end-to-end lifecycle and containerized deployment; `design-flow`
for consistent UI. The flows interlock but don't hard-depend on each other — rails-flow
generates the PR Documentation Contract that qa-flow consumes; pipeline orchestrates the
build/test/ship gates; design-flow applies the `fidara-design` skill (bundled in rails-stack)
so UI is consistent without a designer or Figma.

> **Maintainers:** the tooling for maintaining *this* marketplace is **not** a plugin and
> is **not** installed with the four above. It lives in this repo's [`.claude/`](.claude/)
> folder (commands + agents + a status hook) and is active automatically when you clone the
> repo — so app builders never see it. See [`CLAUDE.md`](CLAUDE.md) and
> [Maintaining the marketplace](#maintaining-the-marketplace) below.

## The skills

| Skill | What it encodes | References |
|---|---|---|
| **`rails-8`** | The full Rails 8.1.x doctrine: vanilla-first stack (built-in auth, Solid Queue/Cache/Cable, Propshaft + importmap, Kamal 2), models → controllers → views workflow, **pure RSpec** testing (no Minitest, no matcher add-ons), OpenAPI docs via rswag, AI features via ruby_llm, observability, advanced Active Record, ecosystem gems | 16 reference files |
| **`hotwire`** | The Hotwire stack from the official handbooks: Turbo 8 (Drive, morphing refreshes, Frames, Streams), Stimulus 3.2 (full controller reference), and **Hotwire Native** (iOS/Android shells, path configuration, bridge components) | 3 reference files |
| **`fidara-design`** | The Fidara design system: Tailwind v4 `@theme` token architecture (brand primitives → semantic roles → Utopia fluid scale), Every-Layout composition primitives, a ~16-component catalog (variant×size×state), Stimulus interaction patterns, responsive doctrine, mobile (Hotwire Native + native token export) parity, reference implementations (ViewComponent + Stimulus mixin + Hotwire-Native + native-token-export code), a **data-visualization layer** (validated `fm-*`-derived chart palette, KPI + chart recipes, chart a11y), and the two-brand model — so UI is consistent across web, Android, and iOS without a designer/Figma | 14 reference files (incl. worked implementations for the full component catalog, modal-driven CRUD, and data-viz) |

They cross-reference each other — install all three for Rails + UI work (all ride in `rails-stack`).

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
indexed memory memos (STATUS / PROGRESS-LOG / DECISIONS / HYPOTHESES + provenance tags) ·
`/rails-flow:brain-review` runs a weekly maintenance sweep (staleness, decisions-vs-PRD drift,
contradictions, stalled hypotheses) · `/rails-flow:brain-sync` publishes to / consumes a
cross-project **shared brain repo** (`<org>/brain`) so agentic flows in separate repos coordinate
via `gh` without cloning each other — git is the single source of truth ·
`/rails-flow:issues` triages open repo issues (bug / feature /
chore / needs-info) and works them one at a time through the matching pipeline, each
PR auto-closing its issue · `/rails-flow:pr-comments` sweeps a PR's review feedback —
every actionable comment is fixed on-branch or folded into a tracked issue, and **no
next task starts until the current PR closes clean** · `/rails-flow:curate` distills
`docs/` (PRDs, branding, architecture) into project-local skills and keeps them
synced as documentation evolves — the project's agents get smarter as its docs grow.

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

### Continuous project skills — docs → skills

Every repo carries knowledge only humans read: PRDs, brand systems, domain rules.
`/rails-flow:curate` turns those into project-local skills (`.claude/skills/`,
committed, team-shared) via the `skill-curator` agent — distilled doctrine, never
mirrored documents — tracked in a manifest of source hashes. The SessionStart hook
reports when sources drift from their skills, so curation is continuous: as the
project's documentation grows, its agents' expertise grows with it. The curator may
also PROPOSE project-local agents wired to dense skill clusters (a brand-guardian for
a rich design system); creation always awaits human approval.

### Agent teams mode (experimental)

rails-flow's eight agents double as teammate types: Claude Code's agent teams spawn
persistent teammates FROM agent definitions, honoring their tools and model. Where
that beats one-shot subagents: `/review`'s parallel passes with peer messaging, and
gate loops where a persistent reviewer stays cache-warm across BLOCKED→fix cycles
instead of re-reading the branch each round. Team hooks add enforcement —
`TaskCompleted` can mechanically refuse premature completion. Requirements: Claude
Code ≥ 2.1.32, Opus-class lead, feature flag on; it's experimental and off by
default, and the default flow remains classic subagents. The scaffolded CLAUDE.md
now also carries Delegation Rules with an anti-recursion role check (executors never
spawn executors).

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
# Exclude noise BEFORE the first build — a missing or too-broad ignore file is
# the top cause of thin or bloated graphs:
printf '%s\n' node_modules/ vendor/ tmp/ log/ coverage/ public/assets/ \
  storage/ graphify-out/ .code-review-graph/ > .code-review-graphignore

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
3. Switch branches and back (`git checkout -`) → timestamp advanced once more
   (post-checkout hook alive — branch switches rewrite the tree without any edit
   hook firing, so this is the probe that catches silent staleness)

Static double-check: `python3 -m json.tool .claude/settings.local.json | grep -A3
PostToolUse` shows `[]` — graph updates live in Stop, never per-edit.

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

**Verify it end to end** (same prove-each-layer discipline as the CRG runbook):

```bash
ls graphify-out/                        # expect: cache graph.html graph.json GRAPH_REPORT.md
head -12 graphify-out/GRAPH_REPORT.md   # corpus verdict + node/edge/community counts
                                        # + "Built from commit: <sha>" — compare with:
git rev-parse --short HEAD              # mismatch = stale graph, hooks not firing
graphify query 'billing' --graph graphify-out/graph.json --budget 800
graphify path 'SomeController' 'SomeService' --graph graphify-out/graph.json
graphify explain 'SomeService' --graph graphify-out/graph.json
grep -c graphify .git/hooks/post-commit .git/hooks/post-checkout   # ≥1 each
```

A `query` on a class you know exists must return ruby-typed nodes with file paths;
empty results on a real symbol means the graph is broken regardless of what the
report says. Open `graphify-out/graph.html` in a browser for the free visual.

It's v0.9.x (pre-1.0, MIT) — expect some churn; each piece degrades gracefully if
uninstalled.

Deliberately not adopted from the source guide, so you don't wonder: the ~200-line
smart-grep interceptor hook (the `CRG_TOOLS` allow-list plus the SessionStart
cheatsheet capture most of its token savings at a fraction of the maintenance
surface) and the Obsidian vault generator script (personal-layer tooling —
`graph.html` and `GRAPH_REPORT.md` give the visual and the map for free).

## Independent QA — `qa-flow`

qa-flow tests the **running application from the outside** — deliberately independent of the
developer spec suite. The developer flow proves a feature works; qa-flow guards that a
change didn't break previously-certified behavior, and certifies the whole system for
release.

**Stack-agnostic — the QA engineer picks the tools, qa-flow never forces one.**
`/qa-flow:setup-qa` **inspects the codebase and proposes a recommended stack** (detecting
existing Cypress/Playwright/Selenium, `*.feature` files, mobile targets, an OpenAPI spec,
etc. — and never proposing to switch a framework you already use), which you confirm or
override. It writes `qa/qa.config.yml` where you choose per tier —
`web_e2e: playwright | cypress-cucumber | selenium-pytest-bdd`, `mobile: appium`,
`functional_agent: playwright-mcp | autonoma-selfhosted`, reporting, etc. — all **free by
default**. The stack-agnostic core (case catalogue, risk plan, evidence rules, certification
gate, Markdown/CSV reporting, the git/release flow) is the product; the runner is a config
choice. Paid/optional backends (e.g. `case_management: testmo`) are **opt-in via config +
credentials** — never forced, never a hard dependency.

Set `reporting: allure` (or `both`) and every runner (Playwright / Cypress / Selenium /
Appium) plus the API/perf/a11y tiers feed one free, unified **Allure** HTML report
(`qa/reports/allure-report`) with steps, history, and screenshot/trace attachments —
`markdown-csv` (repo-local Markdown + Excel CSV) remains the zero-dependency default.

**Two moments, mapped to QA theory** (smoke ⊂ sanity ⊂ regression):

- `/qa-flow:verify` — fires after a feature merges to dev. Smoke gate (is the build
  testable?) → sanity on the changed areas → **targeted regression by blast radius**
  (does this change threaten existing behavior?). Not feature re-testing. Defects file
  as `qa,from-qa` issues worked via `/rails-flow:issues label:qa`; no next feature
  until green. Regression selection is automatic at the mechanical floor, proposed for
  semantic neighbors, and **human-gated when the change touches auth, tenancy, money,
  migrations, or a shared concern**.
- `/qa-flow:certify` — the comprehensive pre-`main` gate. Full regression across
  browsers + release-only layers (k6 load/soak, OWASP ZAP DAST) against **staging**.
  A clean sweep writes `qa/CERTIFICATION` (bound to the exact dev sha) and promotes the
  cycle's proven features into the growing regression corpus.

**The gate is mechanical**: a PreToolUse hook blocks any dev→main promotion (push,
merge, `gh pr merge` with base main) unless `qa/CERTIFICATION` exists, reads PASS, and
matches the current dev sha. `QA_ALLOW_MAIN=1` is audited break-glass.

**Case authoring + agentic functional testing (free, repo-local, no online tool):**

- `/qa-flow:cases [area|feature|#issue|all]` — automates the tedious part of QA: the
  `case-author` agent **writes and maintains** the test-case catalogue `qa/test-cases.csv`
  from the PRD, the app's menu/routes, the qa-lead plan, and past defects — stable `TC-###`
  IDs, idempotent (add / update / deprecate, never renumber or delete), Excel-openable. No
  Testmo or online case manager needed (an export can seed it, but the file is the source of
  truth).
- `/qa-flow:functional` — the `functional-tester` agent drives the running app through
  **Playwright MCP** (free, Microsoft) from those case titles: menu-scoped, evidence-based
  (a screenshot backs every finding), strictly in-scope, no code changes. Writes a Markdown
  report **+ an Excel-openable CSV summary** and screenshots into `qa/manual-tests/`. This is
  agentic functional/exploratory coverage — complementary to the automated regression tiers.

`/qa-flow:setup-qa` scaffolds the `qa/` workspace (Playwright config, seed personas,
k6 skeletons, `qa/test-cases.csv`, `qa/manual-tests/`), the PR template, and reports the
tools to install (`npx playwright install`, `pipx install schemathesis`, `k6`, Docker for
ZAP, and the Playwright MCP server).

Agents: qa-lead (blast-radius planning), **case-author** (catalogue authoring/upkeep),
**functional-tester** (Playwright-MCP functional testing), e2e-tester, api-contract-tester,
a11y-auditor, perf-tester, security-scanner, exploratory-tester, qa-reporter.

### The PR Documentation Contract

rails-flow's `/feature` and `/fix` generate a structured PR body — Summary, What was
built, **How to test** (steps + expected results), Expected results checklist, Out of
scope, Risk notes, Proof — and `pr-reviewer` **blocks** PRs missing it when qa-flow is
installed. It is QA's primary planning input: qa-lead reads the author's "how to test"
as claims to verify, then exceeds them. The risk notes drive blast-radius selection.

## Lifecycle & deployment — `pipeline`

pipeline sequences rails-flow and qa-flow across the SDLC without replacing their
gates, and produces the release artifact. `/pipeline` detects the current stage
(developing / verify-pending / verify-failed / certify-pending / release-ready /
released) and drives the next flow, stopping at each gate; `/pipeline:status` reports
read-only.

**The release artifact is a versioned Docker image** — the same image Kamal pulls to a
cloud server later, so "local vs cloud" is only *where it's pulled*. `/pipeline:release`
builds it (Rails 8 ships the Dockerfile), tags with the certified dev sha, pushes to
**ghcr.io** (free, no Actions minutes), and in local mode **pulls it fresh and
health-checks `/up`** — proving the artifact boots, not just builds. Gated on
`qa/CERTIFICATION` matching the dev sha — uncertified code is never imaged.

### Cloud deployment on demand — `/pipeline:deploy-cloud`

`.env` is the **deploy agent's briefing sheet** — not a Rails runtime file (Rails 8
uses encrypted credentials, not dotenv). You prepare it once; the agent reads every
value and **routes each to its Rails-native home**, then deploys autonomously with no
prompting:

- `CRED__*` keys → **Rails encrypted credentials** (written non-interactively via
  `ActiveSupport::EncryptedConfiguration` with a read-back verify; `CRED__stripe__api_key`
  → `stripe: { api_key: }`). Committed as ciphertext, image-baked.
- `KAMAL_REGISTRY_PASSWORD` / `RAILS_MASTER_KEY` / DB password → gitignored
  `.kamal/secrets`, referenced by **name** in the committed `deploy.yml`.
- host / domain / registry user / image → `config/deploy.yml` facts.

`/pipeline:setup-cloud` writes an annotated `.env.example` documenting every value
grouped by destination, plus a README "Cloud deployment" section. A blocking safety
pass proves (via `git diff`) that no secret value ever entered a committed file.
Deploys require explicit approval and inherit rails-flow's deploy guard.

**Frugal by design**: `/pipeline:install-hooks` writes local git-hook *nudges* that
detect lifecycle transitions and remember them — they never invoke Claude headlessly or
spend tokens. A dormant GitHub Actions adapter ships as an `.example` for when cloud
minutes are available.

### Platform note

qa-flow and pipeline hooks are **bash + python3**. On Windows, run Claude Code inside
**WSL or Git Bash** with `python3` available, or the hooks — including the blocking
release gate — can't execute (and a blocking gate that can't run is the dangerous
direction: ensure the toolchain is present where enforcement matters).

## Maintaining the marketplace

The four plugins above help you build *apps*. The tooling that maintains *this
marketplace* is **not a plugin and not distributed** — it lives in this repo's
[`.claude/`](.claude/) folder, so it's active automatically for anyone who clones the repo
and completely invisible to app builders who add the marketplace. Nothing to install.

Clone the repo, open Claude Code, and you have:

- **`/maintainer-triage [issue|label]`** — classify open issues by component × type ×
  priority, label, dedupe, queue.
- **`/maintainer-work [issue]`** — one issue end-to-end: confirm → **verify against
  source-of-truth** → fix → PR (`Closes #n`) → bump + CHANGELOG → release.
- **`/maintainer-audit [component]`** — proactive source-of-truth review; files findings
  as issues.
- **`/maintainer-setup-intake`** — scaffold issue templates + label taxonomy.

Backed by five agents in [`.claude/agents/`](.claude/agents/) and a SessionStart
open-issue status hook. Its **non-negotiable gate**: no skill claim is edited until the
`doctrine-verifier` agent confirms it against an authoritative source — verification
precedes edits, and an INCONCLUSIVE verdict leaves doctrine unchanged. **Full maintainer
guide: [`CLAUDE.md`](CLAUDE.md)** (git flow, automated releases, versioning discipline,
packaging).

### The feedback loop — reporting from the field

The *sending* end ships inside rails-flow (installed by users); the *receiving* end is the
`.claude/` tooling here. **`/rails-flow:report <observation>`** delegates to the
`claude-skills-reporter` agent, which turns friction hit while using the toolchain into
a structured, deduped, version-pinned, evidence-backed issue on this repo. It is
scope-guarded (toolchain only — it refuses to file your app's bugs), **drafts by default**,
and files only on an explicit `MODE: FILE` (via `gh issue create --body-file`). So real
daily usage feeds back as triage-ready issues — which a maintainer's `/maintainer-triage`
and `/maintainer-work` then turn into releases. (Every issue in this repo's tracker was
filed this way.)

## Repository layout

See [CHANGELOG.md](CHANGELOG.md) for the full version history of every plugin.

```
claude-skills/
├── skills/                # bundled into the rails-stack plugin
│   ├── rails-8/          # SKILL.md + references/  (source of truth)
│   ├── hotwire/          # SKILL.md + references/
│   └── fidara-design/    # the Fidara design system: SKILL.md + 7 references
├── plugins/               # DISTRIBUTED — the app plugins in marketplace.json
│   ├── rails-flow/       # agentic build flow: commands + agents + hooks
│   ├── qa-flow/          # independent QA flow
│   ├── pipeline/         # lifecycle + release orchestrator
│   └── design-flow/      # UI/design flow: applies the fidara-design skill
├── .claude/               # NOT distributed — maintainer tooling for THIS repo
│   ├── commands/         # /maintainer-triage · -work · -audit · -setup-intake
│   ├── agents/           # doctrine-verifier, issue-triager, skill/plugin-doctor, release-manager
│   ├── hooks/            # SessionStart open-issue status
│   └── settings.json     # registers the hook
├── CLAUDE.md              # maintainer guide (start here to maintain the repo)
├── .github/
│   ├── workflows/release.yml  # auto-release on dev→main merge
│   └── ISSUE_TEMPLATE/   # structured report intake + label taxonomy
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

### Recommended for teams: the plugin marketplace

```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills   # knowledge: Rails 8 + Hotwire skills
/plugin install rails-flow@claude-skills    # build process: orchestrated feature work
/plugin install qa-flow@claude-skills       # independent QA: verify + certify + release gate
/plugin install pipeline@claude-skills      # lifecycle + containerized release + cloud deploy
```

After installing, restart Claude Code so all hooks register. Per-project setup runs in
dependency order: `/rails-flow:setup-flow` → `/qa-flow:setup-qa` →
`/pipeline:setup-pipeline`.

Run those inside any Claude Code session. The `rails-stack` plugin bundles the
rails-8, hotwire, and fidara-design skills and **auto-updates as new versions ship —
no per-project copies to hand-sync** — which is why it's the recommended path for
teams. It's also required anyway for the `rails-flow` / `qa-flow` / `pipeline`
interplay, so a team already running the toolchain has it installed.

Reserve a project's own `.claude/skills/` for **project-specific** skills — e.g. ones
distilled with `/rails-flow:curate`, or your own domain skills — **not** full copies
of the framework skills the plugin already delivers. Committing the framework skills
*and* running the plugin means two copies of the same doctrine to hand-sync on every
release; keep the plugin as the single source and skip the vendoring below unless you
need it.

### Into a project — fallback for no-plugin environments

Use this only when you **can't** run Claude Code plugins — claude.ai/Desktop-only
teams, or air-gapped CI that needs the skills committed into the repo. **Trade-off:**
vendored copies don't auto-update; you must re-sync them on every skill release (see
[Updating](#updating)). Teams that can run the plugin should prefer it.

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

**Plugin installs auto-update** — new marketplace versions arrive through `/plugin`
(refresh with `/plugin marketplace update claude-skills`); nothing to re-copy. The steps
below apply only to the **vendored fallback** (skills committed under `.claude/skills/`),
which must be re-synced on every release:

```bash
cd claude-skills && git pull
./scripts/install.sh /path/to/your/project   # re-copy into each vendored install target
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

# Tool-gated code review with a knowledge graph (optional)

Moved out of the README, which is an install-and-orient page: this is a 200-line setup for an
**optional** third-party integration, and it was crowding the thing most readers came for.
Nothing here changed in the move.

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

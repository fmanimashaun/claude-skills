# Changelog

All notable changes to this repository. Components version independently:
**rails-flow** (version in `plugins/rails-flow/.claude-plugin/plugin.json`),
**rails-stack** (version in its `marketplace.json` entry), and repository-level
changes (README, packaging, infrastructure). Every version bump gets an entry here.

## Repository hygiene

### 2026-07-22 — README brought to four-plugin fidelity
- The README documented only rails-stack + rails-flow; qa-flow and pipeline (the
  entire test + deploy half) were absent, which made fetched/summarized views report
  "2 plugins" and confused tooling. Rewrote (513→628 lines): added a top-of-file
  four-plugin architecture overview table, full qa-flow section (verify/certify two
  moments, mechanical dev→main gate, PR Documentation Contract), full pipeline section
  (Docker-image-as-release-artifact on ghcr, /pipeline:deploy-cloud .env-routing model,
  frugal git-hook nudges, platform note), and updated the install block to all four in
  dependency order. No functional change; metadata 1.4.5.

### 2026-07-22 — remove root-level plugin file duplicates
- 14 stale plugin files (agents, commands, hook scripts, plus a stale
  marketplace.json and orphan hooks.json) had been committed to the REPO ROOT by
  an early "Add files via upload" web drag-drop, duplicating — at frozen old
  versions — the canonical files under plugins/**/ and .claude-plugin/. Removed all
  14 (each verified to have a canonical copy first). Hardened .gitignore with
  root-anchored patterns (/*.sh, /hooks.json, /marketplace.json, /plugin.json) so
  plugin files can only live under plugins/** and .claude-plugin/**, never the root.
  No canonical file touched; marketplace remains 1.4.4 with all four plugins.

## skill-maintainer (marketplace maintenance plugin)

> **Relocated to repo-local `.claude/` in v1.6.8** (the short-lived separate marketplace
> from v1.6.7 was reverted and deleted). The entries below are its history as a
> distributed plugin; it now lives in `.claude/` as this repo's own maintainer tooling —
> see `CLAUDE.md`.

### 1.0.1 — 2026-07-23
- Fix #4: separate this maintainer-only plugin from the app-builder install surface.
  Manifest descriptions (marketplace entry + plugin.json) now lead with a hard
  "⚠ MAINTAINERS ONLY — do NOT install into app projects" marker, so the `/plugin` browse
  surface itself carries the warning (not just README prose). All four commands
  (`setup-intake`, `triage`, `work`, `audit`) gained a hard repo-type precondition:
  they refuse to mutate anything unless `.claude-plugin/marketplace.json` exists at the
  repo root (reusing the SessionStart hook's test) — so a mis-install can't scaffold
  marketplace issue-templates/labels into an app repo. README made consistent: the plugin
  table row is badged maintainers-only and the plugin's own README leads with the caveat
  instead of a bare install recipe.

### 1.0.0 — 2026-07-23
- New fifth plugin: the maintenance side of the loop — downstream projects report
  issues as they hit them, and this flow ships source-verified fixes. Marketplace
  1.6.0.
- 4 commands: `/skill-maintainer:setup-intake` (scaffold GitHub issue templates + a
  label taxonomy, idempotent), `:triage` (classify open issues by component × type ×
  priority, label, dedupe, queue), `:work` (one issue end-to-end: confirm → verify →
  fix → PR `Closes #n` → bump + CHANGELOG → release), `:audit` (proactive
  source-of-truth review, files findings as issues).
- 5 agents: `issue-triager` (classify/label only), `doctrine-verifier` (BLOCKING gate —
  no skill claim is edited without an authoritative citation; verification precedes
  edits, INCONCLUSIVE leaves doctrine unchanged), `skill-doctor` (edits skill
  references on a CONFIRMED verdict, then repackages via `package_core.py`),
  `plugin-doctor` (fixes plugin agents/commands/hooks; `bash -n` + behavior repro +
  all-paths-intact before hand-off), `release-manager` (independent component
  versioning, CHANGELOG, reproducible packaging, tagged release).
- SessionStart status hook surfaces the open-issue signal (P1 / incorrect-doctrine
  counts); read-only, non-blocking, fails open when `gh` is absent.
- Repo intake (dogfood): `.github/ISSUE_TEMPLATE/` forms (incorrect-doctrine — requires
  a citation, skill-gap, plugin-bug, packaging, feature) + `config.yml` (usage
  questions → Discussions) + `.github/labels.yml` taxonomy.

## rails-flow (agentic flow plugin)

### 1.3.1 — 2026-07-23
- **Dropped NotebookLM from the brain flow.** `/rails-flow:brain-sync` no longer documents
  NotebookLM as an optional synthesis lens; the `<org>/brain` git repo is the **single source of
  truth** for cross-project state, with no external embeddings/RAG layer. Rationale: keep the
  audit trail — git gives provenance, deterministic reads, and diffs; a separate synthesis service
  drifts from git and can't be trusted for coordination. Federation (publish/consume via `gh`,
  no cloning) is unchanged.

### 1.3.0 — 2026-07-23
- **Brain, leveled up — fuller structure + maintenance + cross-repo federation.** The brain
  was `/brain` memos + MEMORY.md; it's now a full repo-side memory system, and two new commands:
  - `setup-flow` §4 now scaffolds the **fuller brain**: `STATUS.md` (where we are now, edited in
    place), append-only `PROGRESS-LOG.md`, ADR-lite `DECISIONS.md` (with reversal conditions),
    `HYPOTHESES.md` (**lifecycle** candidate→proposed→confirmed|refuted with dated evidence),
    `MEMORY.md`, and a `README.md` doctrine — plus **provenance tags** (`[observed]`/`[decided]`/
    `[assumed]`/`[reported]`) on non-obvious claims, with a "preserve contradictions" rule.
  - NEW **`/rails-flow:brain-review`** — weekly maintenance sweep: flag stale STATUS/evidence,
    surface decisions-vs-PRD drift and contradictions, check hypotheses against evidence, compress
    recurring patterns (preserving minority signals). Report + proposed diffs; applies only what's
    approved. The keystone ritual that keeps the brain from becoming a landfill.
  - NEW **`/rails-flow:brain-sync`** — a **cross-project shared brain repo** (`<org>/brain`) as the
    coordination bus: each project publishes its STATUS to `projects/<self>/` and appends to a
    shared `EVENTS.md`/`CONTRACTS.md`, and reads siblings via `gh` single-file fetches — so agentic
    flows in separate repos coordinate **without cloning each other**. Git is the store (versioned,
    provenance, deterministic). **NotebookLM** is documented as an optional read/synthesis lens on
    top (briefings, Q&A) — never the store, since its write primitive is append-sources not mutable
    state (official Enterprise API + community MCP options + auth caveats noted).
  - `session-start` hook now surfaces the top of `STATUS.md` ("where are we now") alongside MEMORY.md.

### 1.2.1 — 2026-07-23
- Reporter now covers the **design system**: `/rails-flow:report` + `claude-skills-reporter`
  scope includes the `fidara-design` skill and `design-flow` plugin. A generated
  component/UI that won't compile or render in a real Rails app is explicitly in-scope
  (`comp:fidara-design` / `comp:design-flow`) — so the least runtime-verified layer has a
  path back into the issue inflow.

### 1.2.0 — 2026-07-23
- Fix #2: NEW `claude-skills-reporter` agent + `/rails-flow:report <observation>` — closes
  the toolchain feedback loop. Turns friction hit while USING the toolchain into a
  structured, deduped, version-pinned, evidence-backed issue on the upstream marketplace
  repo. Scope-guarded (toolchain only — refuses to file the user's app bugs); pins
  marketplace + plugin version (and running-vs-latest delta); dedups against open/closed
  issues before filing; **drafts by default**, files only on explicit `MODE: FILE` via
  `gh issue create --body-file`. `setup-flow` now surfaces the report path; README gains a
  "feedback loop" section. Pairs with skill-maintainer (the receiving end).
- setup-flow: idempotent-safe re-runs + audit/repair, both by construction.
  IDEMPOTENCY — rails-flow content lives in `<!-- rails-flow:begin/end X -->` markers;
  re-runs refresh only marked blocks and never touch out-of-marker prose; a marker-less
  hand-authored CLAUDE.md is never restructured (additive blocks only, with a diff).
  REPAIR — setup-flow can now diagnose and fix a DEFECTIVE CLAUDE.md, always as
  diagnose→propose-diff→await-approval (never an autonomous rewrite). Repair scope is
  deliberately conservative: only (a) contradictions of fact (stack table vs Gemfile,
  pointers to missing paths, AGENTS.md naming absent agents) and (b) broken safety
  rules (Delegation Rules missing the anti-recursion check, gate bypasses, GUARDRAILS
  contradictions). Divergent-but-valid content (documented Project Overrides, custom
  layouts, domain prose) is left untouched — deliberate choices are never "repaired"
  into vanilla; missing sections are additions, not defects.

### 1.1.2 — 2026-07-22
- stop-gate macOS portability fix (field-reported): the hook shelled out to `timeout`,
  absent on stock macOS, so the wrapped rspec run exited 127 and the gate misread it as
  a RED suite — a false block on green specs. Added a portable `_rf_timeout` helper
  (prefers `timeout`, falls back to `gtimeout`, else runs bare — a missing timeout must
  never be misread as failing) using `type -P` so shell-function/alias shadows can't
  fool it. Same gap noted for the CRG post-checkout hook in setup-flow guidance
  (install coreutils for `gtimeout`, or it runs without the time cap). Both branches
  behaviorally verified: green passes, real failures still block. Same class of bug
  previously patched out of the CRG hook — now consistent across all hooks.

### 1.1.1 — 2026-07-22
- PR Documentation Contract: /feature and /fix now generate the full contract body
  (Summary, What was built, How to test + expected results, Out of scope, Risk notes,
  Proof); pr-reviewer BLOCKS PRs missing it when qa-flow is installed; it is QA's
  primary planning input. QA handoff documented in /feature (verify gates feature->dev).

### 1.1.0 — 2026-07-21
- NEW `skill-curator` agent + `/rails-flow:curate`: distills `docs/` (PRDs,
  branding, architecture, domain rules) into project-local skills with a
  hash-manifest sync protocol; SessionStart reports source drift; curator may
  propose project-local agents (human-approved). Docs → capabilities,
  continuously.
- Scaffolded CLAUDE.md gains Delegation Rules: coordinator/executor split with
  an anti-recursion role check (`ROLE: EXECUTOR` never spawns subagents).
- Agent-teams doctrine: /review documents optional teams mode (persistent
  teammates from these agent types, peer messaging, TaskCompleted enforcement);
  default remains one-shot subagents. Verified against official agent-teams docs.

### 1.0.8 — 2026-07-21
- Version-only bump alongside the marketplace 1.1.8 release; no plugin content
  change since 1.0.7 (keeps the plugin cache-key aligned with the release tag).

### 1.0.7 — 2026-07-20
- Version-only bump: invalidates installed 1.0.6 caches that captured the
  pre-amendment `setup-flow` (same-version content amendments don't propagate —
  lesson encoded: content changes always ride a version bump).

### 1.0.6 — 2026-07-20
- graphify integration as the complementary exploration/cross-repo graph:
  `setup-flow` detects it, scaffolds `.graphifyignore`, git-hook-only freshness,
  and the `CRG → graphify → grep` fallback chain.
- Setup/verification parity with the source field guide: ignore file before first
  build, graphify end-to-end verification, CRG post-checkout hook (branch-switch
  staleness), SessionStart graph cheatsheet, third freshness probe.

### 1.0.5 — 2026-07-20
- Repo-wide LF normalization after a CRLF incident broke all four hook scripts
  on macOS/WSL (`git add -A` from a Windows clone swept phantom-modified files).
  `.gitattributes` added (`* text=auto eol=lf`); recurrence structurally impossible.
- Content otherwise identical to 1.0.4.

### 1.0.4 — 2026-07-20
- New `/rails-flow:issues`: triages open issues (bug/feature/chore/needs-info),
  works them strictly one at a time through the matching pipeline, `Closes #n`
  PRs with auto-close verification, `/goal`-driven unattended mode.
- New `/rails-flow:pr-comments`: sweeps conversation + inline comments + CI;
  in-scope items fixed on-branch (spec-first), out-of-scope folded into
  `from-pr-review` issues; re-gates after changes.
- Close-out rule threaded through `/feature` and `/fix`: no next task while the
  current PR has unresolved feedback.
- pr-reviewer deferral rule: BLOCKING findings are never deferred to issues to
  earn a CLEAN; deferred suggestions must be folded and linked.

### 1.0.3 — 2026-07-20
- Autonomous operation: `/goal` vs `/loop` doctrine (condition-driven vs
  interval-driven), `setup-flow` scaffolds a project `loop.md` maintenance pass,
  `/feature` offers a PR-babysitter loop on default-branch stops, `/fix`
  documents unattended backlog runs.
- README: autonomy section; Windows note (hook scripts are bash — WSL/Git Bash).

### 1.0.2 — 2026-07-20
- code-review-graph v2.x era (upstream moved plugin → pip CLI): merge gate in
  `/feature`, `/fix`, and pr-reviewer detects the CLI + built graph and invokes
  the `review-pr` skill (plugin namespace removed upstream).
- `setup-flow` gains CRG coexistence: authored-file protection, three-file
  settings pattern with PID-guarded Stop hook, `CRG_TOOLS` 8-tool allow-list,
  post-commit updater, gitignore hygiene.

### 1.0.1 — 2026-07-20
- Hook loader schema fix: `hooks.json` wrapped in a top-level `"hooks"` key;
  empty `matcher` dropped from non-tool events (Stop, SessionStart).

### 1.0.0 — 2026-07-20
- Initial release. Five commands (`/feature`, `/fix`, `/review`, `/setup-flow`,
  `/brain`), eight subagents (rails-developer, migration-writer, code-reviewer,
  test-runner, security-auditor, design-auditor, doc-updater, pr-reviewer), four
  guardrail hooks (bash guard, rubocop-on-edit, spec-proof stop gate, session
  context). Synthesized from the fmworkflows/auctioneer agent systems, elevated
  to hooks-enforced, plugin-distributed, progressive-disclosure form.

## pipeline (lifecycle orchestrator)

### 1.1.1 — 2026-07-23
- **/pipeline:ack git-dir guard** (#46): the marker path came from an unguarded
  `$(git rev-parse --git-dir)`; outside a repo it collapsed to `/pipeline-pending` and the
  `rm -f` could delete a root-level file. Now bails (exit 0 + message) if git-dir is
  unresolved/empty. Fixed `setup-pipeline.md` doc drift (hardcoded `.git/…` → the resolved
  git-dir, worktree-safe, with the `.git/` common case noted).

### 1.1.0 — 2026-07-23
- Fix #5: the post-merge QA-verify nudge marker now has a dismissal/clear path. New
  `/pipeline:ack` removes `.git/pipeline-pending` (worktree-safe via `git rev-parse
  --git-dir`) — nudge-only, no token spend — so a stale nudge can be cleared without
  another merge or a manual `rm`; verified the SessionStart hook stops re-surfacing it
  after. The pipeline-coordinator now CLEARS the marker when the verify stage resolves
  (a `/qa-flow:verify` PASS or an explicit N/A), making "clears when the stage completes"
  literally true. `pipeline-status.sh` reads the marker via git-dir (matching the writer)
  and its hint points to `/pipeline:ack` (e.g. docs-only merges with nothing to verify).
  Docs updated (`setup-pipeline.md`, README).

### 1.0.5 — 2026-07-22
- setup-pipeline + setup-cloud: idempotent re-run + repair contract (matching
  setup-flow). pipeline.yml keys reconciled not overwritten (missing added, wrong
  values proposed as diffs); .env.example regenerated preserving user annotations,
  never touching the real .env; generated deploy.yml uses kamal-config markers so
  re-runs refresh only the generated block. Every scaffolding command in the
  marketplace now shares one idempotent-and-repairable discipline.

### 1.0.4 — 2026-07-22
- Portability pass: pipeline-status skips cleanly when `python3` is absent; portable
  `mktemp` template in install-git-hooks (BSD+GNU). Platform assumptions now behave
  consistently across macOS/Linux/WSL.

### 1.0.3 — 2026-07-22
- install-git-hooks hardening (peer review): append-or-backup instead of clobbering
  an existing post-merge hook (critical in an ecosystem where CRG and rails-flow also
  write git hooks) — managed-block markers make re-runs idempotent, non-managed hooks
  are backed up then appended to; `dev_branch` fallback no longer defeated by
  pipefail when pipeline.yml is absent. Platform note added to the plugin README.

### 1.0.2 — 2026-07-22
- Cloud deploy reworked to the .env-briefing-sheet + routing model (Rails
  convention). `.env` is the agent's single source of truth (NOT a Rails runtime
  file — Rails 8 has no dotenv); the agent ROUTES each value to its home: `CRED__*`
  keys → Rails encrypted credentials written NON-INTERACTIVELY via
  ActiveSupport::EncryptedConfiguration with a read-back verify (never
  credentials:edit, which needs an editor and silently no-ops); deploy secrets →
  gitignored .kamal/secrets by name; facts → deploy.yml. Annotated `.env.example`
  template ships in the plugin, grouped by destination bucket, with the
  `CRED__top__sub` nesting convention. Verified vs Rails credentials + Kamal 2 docs.

### 1.0.1 — 2026-07-22
- Cloud deployment on demand: `kamal-configurator` agent + `/pipeline:setup-cloud`
  and `/pipeline:deploy-cloud`. setup-cloud writes `.env.example` (the documented
  contract of every variable the deploy expects) and a README "Cloud deployment"
  section; deploy-cloud reads the filled `.env`, generates `config/deploy.yml`
  (secret NAMES only, committed) and `.kamal/secrets` (values, gitignored +
  dockerignored, via the `<% Dotenv.load(".env") %>` bridge Kamal 2 requires since
  it no longer auto-loads .env), safety-checks that no secret value entered a
  committed file, then `kamal setup`/`deploy` with explicit approval + the deploy
  guard. Verified against Kamal 2 secrets docs. Same ghcr image as the local flow —
  cloud is just where it's pulled.

### 1.0.0 — 2026-07-22
- Fourth plugin: sequences rails-flow and qa-flow across the SDLC without replacing
  their gates. pipeline-coordinator detects stage (developing / verify-pending /
  verify-failed / certify-pending / release-ready / released) and drives the next
  flow; /pipeline advances, /pipeline:status reports read-only.
- Release artifact = a versioned Docker image on ghcr.io (source-verified: the same
  image Kamal pulls to a server later — local vs cloud is only where it's pulled).
  /pipeline:release builds, tags with the certified dev sha + latest, pushes, and in
  local mode pulls-and-runs to health-check /up (proves the artifact boots, not just
  builds). Cloud mode = kamal deploy, gated by rails-flow's deploy guard.
- Gated on qa/CERTIFICATION matching the dev sha — uncertified code is never imaged.
- Local git-hook nudges (/pipeline:install-hooks): post-merge on dev leaves a marker
  the SessionStart hook surfaces — detects transitions, NEVER invokes Claude or
  spends tokens (frugal by design; no GitHub Actions minutes used). Dormant Actions
  adapter shipped as an .example for when cloud minutes exist.
- pipeline.yml carries registry/image/mode/branches — local today, cloud by config
  flip, no rebuild.

## qa-flow (independent QA plugin)

### 1.4.1 — 2026-07-23
- **release-gate.sh: closed fail-open bypasses** in dev→main promotion detection (from the
  PR-review backlog triage, #45). (1) Heredoc-body stripping ran before quote/comment
  stripping, so a `<<EOF` inside a quote (`echo "<<EOF"`) or comment (`# <<EOF`) was read as a
  real opener and swallowed a later `git push origin main` → gate passed. (2) Delimiter regex
  missed numeric-leading/hyphenated delimiters. (3) Detection missed prefixed promotions
  (`FOO=1 git push`, `sudo git push`, `git -C repo push`). New pipeline: un-quote delimiters →
  strip quotes → strip comments → strip heredoc bodies, then peel env/sudo/git-option prefixes.
  Verified with an 18-case battery. Local advisory gate; `QA_ALLOW_MAIN=1` override unchanged.

### 1.4.0 — 2026-07-23
- `setup-qa` now **detects the codebase and proposes a recommended stack** instead of asking
  cold: it reads deps/test tooling (`cypress`/`@playwright/test`/`selenium`+`pytest-bdd`),
  `*.feature` files, mobile targets (React Native/Flutter/`ios`+`android`), an OpenAPI spec,
  existing Allure/Testmo config — and pre-fills `qa/qa.config.yml` with a one-line rationale
  per non-default tier. **Respects existing tooling** (never proposes switching a framework
  the repo already uses); greenfield falls back to free defaults by app language. Advisory
  only — the engineer confirms or overrides any line before it's written. Still no forced
  stack.

### 1.3.0 — 2026-07-23
- Wire the free **Allure** unified report end-to-end (`reporting: allure` | `both`; default
  `markdown-csv` unchanged, zero-dependency): `setup-qa` scaffolds the framework's Allure
  adapter for the chosen `web_e2e`/`mobile` runner (allure-playwright / allure-cypress /
  allure-pytest / Appium adapter), all tiers writing into one `qa/reports/allure-results` →
  `qa/reports/allure-report` (both gitignored). `e2e-tester` emits results and **attaches
  evidence** (failure screenshot, Playwright trace, logs), then `allure generate`.
  `qa-reporter` honors the mode, generates the aggregated HTML, keeps a legible Markdown
  verdict/counts alongside, and cites the report path in the PR-native comment. Free/OSS
  (Apache-2.0); no paid or online reporting service.

### 1.2.0 — 2026-07-23
- **Stack-agnostic — no forced testing stack.** New `qa/qa.config.yml` is the override
  point the QA engineer sets; every agent honors it. `setup-qa` is now config-first: it
  asks/reads the config and scaffolds ONLY the chosen tools. Free defaults; any tier
  overridable.
  - `web_e2e`: `playwright` | `cypress-cucumber` | `selenium-pytest-bdd` | `none`;
    `mobile`: `appium`; `functional_agent`: `playwright-mcp` | `autonoma-selfhosted`;
    `api`/`perf`/`security`/`a11y`; `reporting`: `markdown-csv` | `allure`;
    `case_management`: `in-repo` (free CSV, default) | `testmo` (paid, opt-in).
  - `e2e-tester` rewritten stack-agnostic: universal doctrine (self-adapting resilient
    locators, no sleeps, auth-reuse, tag routing, failure classification, corpus growth) +
    per-framework specifics; reuses the same Gherkin `.feature` scenarios across web/mobile.
- **Autonoma-inspired patterns, kept free:** `functional-tester` now **auto-maps** the
  in-scope flows before testing and drives by the **live accessibility snapshot**
  (self-adapting, no brittle selectors) via Playwright MCP. `qa-reporter` gains **PR-native
  result posting** (`gh pr comment`, marker-updated) so results show up in the PR like a CI
  check.
- **Opt-in paid backends without lock-in:** `case_management: testmo` makes `case-author`
  mirror `qa/test-cases.csv` ↔ Testmo via its REST API (`TESTMO_URL`/`TESTMO_TOKEN`, env,
  gitignored); the in-repo CSV always stays the source of truth. Testmo is not an MCP —
  REST/CLI; `setup-qa` captures the creds. Default stays free/in-repo.

### 1.1.0 — 2026-07-23
- Automate the tedious QA loop — case authoring/management + agentic functional testing,
  **free and repo-local** (no Testmo/online case manager; Testmo is paid and stays optional
  — an export can seed the catalogue but the in-repo file is the source of truth):
  - NEW `case-author` agent + **`/qa-flow:cases`** — writes and MAINTAINS the test-case
    catalogue `qa/test-cases.csv` (columns `Test ID,Title,Area,Type,Priority,Status,Source,
    Notes`) from the PRD, app menu/routes, the qa-lead plan, and `docs/brain` defects.
    Stable `TC-###` IDs; idempotent add / update / deprecate (never renumber or hard-delete);
    Excel-openable; reviewable as a `git diff`.
  - NEW `functional-tester` agent + **`/qa-flow:functional`** — drives the running app via
    **Playwright MCP** (free) from those case titles: menu-scoped, evidence-based (screenshot
    per finding), strictly in-scope, no code changes. Writes a Markdown report + an
    Excel-openable CSV summary + screenshots to `qa/manual-tests/`. Models a proven
    Claude-Desktop + Playwright-MCP manual-testing flow, systematized into the plugin.
  - `setup-qa` scaffolds `qa/test-cases.csv` + `qa/manual-tests/` and documents enabling the
    Playwright MCP server.

### 1.0.6 — 2026-07-23
- Close the #1 residual: release-gate now strips heredoc BODIES before detection, so an
  unquoted heredoc body line beginning with `git merge` / `git push origin main` /
  `gh pr merge` no longer trips the gate (`<<EOF`, `<<-EOF` with tab-stripped terminator,
  and quoted `<<'EOF'`/`<<"EOF"` all handled; here-strings `<<<` left alone). A genuine
  promotion on a line after a heredoc, and ordinary newline-separated promotions, still
  gate. Verified on `main` via a worktree (`git merge` blocks on main; a commit message
  mentioning it does not) plus the full regression matrix. Residual (documented
  in-script): multiple heredocs opened on a single line (`cmd <<A <<B`) track only the
  first body — astronomically rare, and errs fail-closed.

### 1.0.5 — 2026-07-23
- Fix #1: the release-gate hook no longer false-positives on commands that merely
  MENTION a promotion. Detection now strips quoted spans (commit messages, `-m` /
  `--body`, `echo` bodies) and requires `git push …main|master` / `git merge` /
  `gh pr merge` at the START of a command segment (split on `;` `|` `&&` `||`) — so a
  commit whose message contains "gh pr merge", or an `echo`/PR-body referencing
  "git merge", is no longer read as an invocation. Genuine promotions (incl. chained
  `… && git push origin main`) still gate, the `gh pr merge` unresolvable-base case
  still fails closed, and `QA_ALLOW_MAIN=1` still overrides. Verified with a 10-case
  matrix. Residual (documented in-script): an unquoted heredoc body line beginning with
  `git merge` is still seen — rare, and errs fail-closed.

### 1.0.4 — 2026-07-22
- setup-qa: idempotent re-run + repair contract (matching setup-flow). Generated config
  refreshed only within `qa-flow:begin/end` markers; seeds additive (find_or_create);
  defective managed files (baseURL not reading QA_BASE_URL, personas mismatching app
  roles) diagnosed and fixed as approved diffs; deliberate customizations untouched.

### 1.0.3 — 2026-07-22
- release-gate python3-missing guard: word-boundary matching (grep -E with \b)
  instead of the `*push*main*` glob, so `git push origin maintenance` no longer
  false-matches "main". Real promotions (main/master as whole refs, gh pr merge,
  git merge) still catch; still fails closed in the safe direction. Verified.

### 1.0.2 — 2026-07-22
- Portability pass (proactive, same class as the stop-gate macOS fix): the BLOCKING
  release-gate now fails CLOSED if `python3` is absent on a promotion command (a gate
  that can't evaluate must not permit dev→main) with a clear install/override message,
  reads stdin once, and uses `type -P`. The non-blocking qa-status hook skips cleanly
  when python3 is absent. Consistent across macOS/Linux/WSL.

### 1.0.1 — 2026-07-22
- release-gate hardening (peer review): fail CLOSED when the certification sha is
  empty/garbled (the sha binding is the gate — PASS alone is insufficient); robust
  `gh pr merge` promotion detection incl. bare (current-branch) merges and
  unresolvable base treated as promotion; platform note (bash+python3 → WSL/Git Bash
  on Windows) added to the plugin README.

### 1.0.0 — 2026-07-22
- Independent QA engineering flow, sibling to rails-flow, testing the running app
  from the outside with its own toolchain — never the developer spec suite.
- 8 agents: qa-lead (risk/blast-radius planning from PR docs + project skills),
  e2e-tester (Playwright TS, smoke/regression tags, corpus growth),
  api-contract-tester (Schemathesis + authz matrix), a11y-auditor
  (axe-core WCAG 2.2 AA + keyboard), perf-tester (k6 smoke + load/soak),
  security-scanner (OWASP ZAP DAST, triaged), exploratory-tester (session-based),
  qa-reporter (report + defect filing + certification stamp + corpus promotion).
- 3 commands: /qa-flow:verify (post feature->dev: smoke gate -> sanity -> targeted
  regression by blast radius, risk-gated selection), /qa-flow:certify (pre dev->main:
  smoke -> full regression -> load/DAST/cross-browser on staging, writes the stamp),
  /qa-flow:setup-qa (scaffold qa/ workspace + PR template + tool checklist).
- Hooks: release-gate (PreToolUse — blocks dev->main promotion unless
  qa/CERTIFICATION PASSes for the exact dev sha; QA_ALLOW_MAIN=1 audited break-glass)
  and qa-status (SessionStart — certification freshness vs dev).
- Doctrine (source-verified): smoke gates but never certifies; sanity subset of
  regression; regression is the release gate; QA guards existing behavior and absorbs
  proven features into the corpus rather than re-testing the current feature.

## design-flow (UI/design plugin)

### 1.2.4 — 2026-07-24
- `/design-flow:component` now routes **chart / KPI / dashboard** screens through the
  fidara-design `data-viz` doctrine (chart tokens, form-by-job, one axis, legend + direct labels,
  re-validate on hue change). Guidance-only.

### 1.2.3 — 2026-07-23
- `/design-flow:setup` closing report now nudges reporting any component that won't
  build/render via `/rails-flow:report`. Guidance-only.

### 1.2.2 — 2026-07-23
- `/design-flow:component` now routes CRUD screens through the crud-modal-pattern (modal +
  Turbo Stream), not full-page forms. Guidance-only.

### 1.2.1 — 2026-07-23
- `/design-flow:component` now points at both reference-implementation (Button/Card + mixins)
  and the full component-implementations catalog as the concrete-code source. No behavior
  change; sharper guidance.

### 1.2.0 — 2026-07-23
- NEW **`/design-flow:tokens [android|ios|both]`** — runs the native token export (Phase 3):
  parse the Rails app's `@theme`, resolve roles, emit Android + iOS token files to `tmp/`.
  Writes only to `tmp/` for the maintainer to carry into native repos; never modifies them.

### 1.1.0 — 2026-07-23
- NEW **`/design-flow:mobile [ios|android|both]`** — scaffolds the Hotwire Native parity layer
  (Phase 2): native-app detection + body flags, JSON path configuration, bridge components
  (button/menu/tab-bar, progressive enhancement), safe-area + `min-h-touch` wiring, and
  table→card-stack. Reuses the web components; never touches the native app repos.

### 1.0.1 — 2026-07-23
- `/design-flow:setup` now points at the fidara-design `reference-implementation` as the
  canonical source for the base ViewComponents + Stimulus mixins (copy those exact shapes),
  and notes mobile (Hotwire Native parity) as Phase 2. No behavior change; sharper guidance.

### 1.0.0 — 2026-07-23
- NEW fifth plugin — the agentic UI/design flow that APPLIES the `fidara-design` skill so UI
  is consistent/modern/responsive without a designer or Figma (mirrors how rails-flow applies
  the rails-8/hotwire skills).
- 3 commands: `/design-flow:setup [brand]` (scaffold the `@theme` token architecture + layout
  `@utility` recipes + base ViewComponents + Stimulus mixins into a Rails 8 + Hotwire +
  Tailwind v4 project, brand-parameterized, idempotent), `/design-flow:component <name>`
  (author/refactor UI by composing primitives + role tokens with variant/size/state + a11y +
  responsive), `/design-flow:audit` (flag drift: raw/brand colors, hand-rolled layout,
  breakpoint misuse, missing a11y, off-catalog variants).
- 3 agents: `ui-composer` (builds by composing the system), `design-auditor` (consistency
  gate, design-system-specific — complements rails-flow's general one), `brand-guardian`
  (token/logo/icon/two-brand enforcement).

## rails-stack (skills plugin: rails-8 + hotwire + fidara-design)

### 1.7.0 — 2026-07-24
- fidara-design **data-visualization layer** (#63, now 14 references): NEW **data-viz** —
  charts, KPIs, and dashboards as first-class design-system doctrine. Adapts Anthropic's
  design-system-agnostic `dataviz` method (form → color-by-job → **validate** → marks →
  interaction → a11y) to fidara: an 8-slot categorical **chart palette derived from the `fm-*`
  tokens** (brand-anchored: blue=cerulean, orange=fm-orange), plus cerulean sequential and
  cerulean↔red diverging ramps, emitted as `--color-chart-*` `@theme` tokens (→ `fill-chart-1`,
  `bg-chart-2`, … re-pointing under `.dark`); a KPI/stat-tile ViewComponent + bar-mark recipe;
  and the chart non-negotiables (fixed categorical order never cycled, **one axis**, identity
  never color-alone, text wears text tokens, status colors reserved). Wired into SKILL
  non-negotiables, foundations-tokens (chart-token pointer), and `/design-flow:component`.
  - **Validated, not eyeballed** (the method's core rule): the categorical palette was run
    through `validate_palette.js`. **Light** (surface `#F8F9FB`): all hard gates PASS — worst
    adjacent CVD ΔE 9.1, normal-vision ΔE 19.6 (4 slots <3:1 → relief rule: direct labels/table).
    **Dark** (surface `fm-navy #0C1B33`): lightness/chroma/normal-vision (ΔE 19.3)/contrast (all
    ≥3:1) PASS; green↔magenta adjacency CVD ΔE 6.1 (6–8 band) → legal with the secondary encoding
    fidara already mandates. Chart `@theme`→utility generation (`bg-/text-/fill-/stroke-/border-chart-*`
    + dark re-point) verified against the Tailwind v4.3.3 compiler. Basis: WCAG 1.4.11; method
    source: Anthropic `dataviz` skill (built to be re-validated per brand).

### 1.6.2 — 2026-07-23
- **fidara-design: reference recipes now honor the skill's own non-negotiables** (#56 —
  the recipes ship verbatim via `/design-flow:setup`, so the contradiction propagated
  downstream). (1) **Radius**: Modal `panel` and the Modal prose use `rounded-lg` instead of
  arbitrary `rounded-[12px]` — with the `@theme` token `--radius-lg = calc(--radius + 4px) =
  12px`, `rounded-lg` *is* 12px, so the token and the arbitrary value are equivalent and the
  vocabulary stays intact. (2) **focus-visible**: Modal close + Alert dismiss icon-buttons now
  carry `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30` like the
  Button/Input recipes. (3) **Icons**: added an "Icons (Lucide)" note with the real
  `helpers.lucide_icon(...)` call site wrapped in `with-icon`, and wired `with-icon` onto the
  Alert icon + both dismiss buttons; guidance is stroke-width-only in the `lucide-rails`
  initializer, never hardcoded px (the Button loader-spinner is the documented fixed-size
  exception). Verified (doctrine-verifier, CONFIRMED): Tailwind v4 `rounded-lg` →
  `var(--radius-lg)` (tailwindcss.com/docs/border-radius); CSS `svg { inline-size: 1em }`
  overrides SVG presentational `width`/`height` at zero specificity, no `!important`
  (MDN SVG Attribute reference). Version boundary: Tailwind v4 (v3 had a fixed radius scale).

### 1.6.1 — 2026-07-23
- fidara-design SKILL.md: NEW **"if the code here breaks, report it"** section — states the
  verification boundary (token/CSS + Stimulus layer is compiler/Node-verified; the
  ViewComponent/Rails integration is doctrine, not runtime-verified against a live app) and
  routes downstream failures to `/rails-flow:report` (`fidara-design` / `design-flow`). Closes
  the feedback loop for the design system.

### 1.6.0 — 2026-07-23
- fidara-design **modal-driven CRUD as first-class doctrine** (now 13 references): NEW
  **crud-modal-pattern** — in Fidara, create/edit/delete never navigate to a separate
  new/edit page; they open in the shared `<turbo-frame id="modal">` and update the list via
  Turbo Stream (`prepend`/`replace dom_id`/`remove dom_id`) + a toast, with a real
  confirmation modal for deletes and a `modal_controller` (focus-trap + dismissable-layer +
  restore). Modal + Card are the backbone; full-page CRUD forms are a defect. Wired into
  SKILL.md non-negotiables, components.md (Table/CRUD), reference-implementation.md (the
  load-bearing modal frame), and `/design-flow:component`. Matches the reference apps' pattern.
- **Verified fix — Tailwind v4 `@utility`:** foundations-tokens.md now defines `min-h-touch`
  and the safe-area utilities (`pt/pb/pl/pr-safe`, `mb-safe`) with `@utility`, not raw classes
  in `@layer utilities`. In v4 (native CSS cascade layers, `@utility` introduced v4.0), only
  `@utility` registers a class with the variant engine, so `sm:pt-safe` / `hover:min-h-touch`
  now generate — raw `@layer utilities` classes emit the base form but get no variants.
  Confirmed against the Tailwind v4.3.3 CLI compiler + official docs
  (tailwindcss.com/docs/adding-custom-styles#adding-custom-utilities, functions-and-directives).
  Whole design-system CSS (role tokens, fluid type, all `@utility` recipes, `dark:` variant)
  and the four Stimulus mixins were build-verified against the real compiler / Node.

### 1.5.0 — 2026-07-23
- fidara-design **full component catalog** as worked code (now 12 references): NEW
  **component-implementations** completes the reference implementations beyond Button/Card —
  Badge, Alert, form Field + Input recipe + checkbox/radio/switch, Modal, Dropdown, Tabs,
  Toast, Tooltip, Avatar, EmptyState, and the Sidebar/Switcher layout components. Every one is
  a frozen `BASE`/`VARIANT`/`SIZE` map on role tokens + primitives, attribute-driven state,
  a11y baked in — the exact shape agents replicate. Pagination/CRUD-tables remain the
  role-tokenized `shared/*` partials.

### 1.4.0 — 2026-07-23
- fidara-design **mobile Phase 3** (now 11 references): NEW **native-tokens** — the native
  token-export doctrine: the role → Material 3 (Android) / SwiftUI (iOS) mapping so semantic
  role names translate 1:1, plus a reference `bin/export_design_tokens` Ruby script that
  resolves role → primitive → hex from the `@theme` and emits `colors.xml` + `Theme.Fidara`
  (Android) and a SwiftUI `Color` extension (iOS) into `tmp/`. Fluid `--text-step-*` export as
  fixed native sizes (documented). `@theme` stays the single source of truth; native files are
  generated, never hand-diverged. `mobile.md` marks Phase 3 code-ready.

### 1.3.0 — 2026-07-23
- fidara-design **mobile Phase 2** (now 10 references): NEW **mobile-reference-implementation**
  — the web-side Hotwire Native parity code: `native_app?` detection + `body.mobile-app` chrome
  toggles, JSON path configuration (modal vs default, per surface), bridge components
  (`button` nav-bar action, `menu` action sheet) as progressive enhancement extending
  `BridgeComponent`, safe-area + `min-h-touch` wiring, and the table→card-stack recipe.
  `mobile.md` marks Phase 2 code-ready. Native Kotlin/Swift shells stay in their own repos
  (this is the web contract they consume); Phase 3 (native token export) still to come.

### 1.2.0 — 2026-07-23
- fidara-design gains the concrete code it was missing (now 9 references): NEW
  **reference-implementation** — the canonical ViewComponent pattern (Button/Card, cva-style
  variant maps + slots) plus the four Stimulus mixins as real code (list-navigation /
  focus-trap+restore / dismissable-layer / anchored-position) and a base layout composing the
  primitives; agents replicate these exact shapes instead of freehand. NEW **mobile** — the
  web↔mobile parity plan (Hotwire Native shell renders the same web UI; safe-areas +
  min-h-touch + bridge components + path config; native token export to Android/iOS for
  fully-native screens; phased). Closes the doctrine's "spec but no code" gap, all in-repo.

### 1.1.0 — 2026-07-23
- NEW **`fidara-design`** skill bundled into rails-stack — the Fidara design system, so UI
  comes out consistent, modern, and responsive across projects without a designer or Figma.
  Distilled from the fmanimashaun/fidara real assets (brand tokens, auctioneer component
  patterns) + a landscape survey (Flowbite, shadcn/Radix/Material/Carbon/Polaris) + Utopia
  (fluid type/space) + Every Layout (composition/intrinsic layout). SKILL.md + 7 references:
  - **foundations-tokens** — Tailwind v4 `@theme` with three tiers: brand primitives (`fm-*`)
    → semantic roles (shadcn-style, `-foreground` pairs, dark mode by re-pointing) → Utopia
    fluid `clamp()` type/space scale + measure/radius/shadow/motion. Resolves the real
    slate-scale / two-type-scale / `dark:`-sprawl inconsistencies to one source of truth.
  - **layout-primitives** — Every Layout (Stack/Cluster/Center/Box/Grid/Sidebar/Switcher/
    Cover/Frame/Reel/Imposter/Icon/Container) as `@utility` recipes + ViewComponents; compose,
    don't write per-page CSS; intrinsic responsiveness (breakpoints for structural swaps only).
  - **components / forms** — ~16-component catalog with a fixed variant×size×state vocabulary,
    a11y checklists, and prescribed responsive behavior, all on semantic role tokens.
  - **interaction-stimulus** — four reusable Stimulus mixins (list-nav, focus-trap+restore,
    dismissable-layer, anchored-position) covering every overlay; state via `data-*`/`aria-*`.
  - **responsive** — fluid + intrinsic first; per-element prescribed behavior; touch/safe-area.
  - **brand** — the two-brand (one-system, `fm-*` prefix) model, Prism mark, Lucide icons.

### 1.0.5 — 2026-07-22
- rails-8 › controllers-routing §1a: new URL-design doctrine (journey-wide).
  Default posture — human, readable URLs for user-facing pages; REST resource URLs for
  interchangeable records and the JSON API. The rule: match the URL to what the reader
  addresses (a specific record → REST id path; a concept or singleton-scoped-to-me like
  /account, /dashboard, /login → human path via singular `resource` or vanity route; a
  machine → strict REST always). The reconciliation: RESTful controllers UNDER human
  URLs (`get "/login", to: "sessions#new", as: :login`) so helpers read naturally,
  controllers stay resource-honest, and password managers / `/.well-known/change-password`
  work. Auth generator's `resource :session` explained as correct-but-developer-vocabulary;
  vanity override documented as a Project Override, not a bug. Pointer added from
  auth-security.md. Source-verified (SEO/URL usability consensus, W3C change-password
  well-known URL). marketplace 1.5.0.

### 1.0.4 — 2026-07-22
- rails-8 › testing §4: factories are **sequences-first** — deterministic
  defaults (reproducible failures, uniqueness by construction, faster, readable
  output), matching fmworkflows' proven practice (16 factory files, zero Faker).
  Faker demoted to its narrow slot (seeds/demo, presentation variation), always
  fully namespaced: no Syntax::Methods-style mixin exists for Faker — the
  `Faker::` prefix is the API. Source-verified post-hoc against thoughtbot's
  own guidance (Faker for development fixtures, not testing fixtures) and the
  practitioner flaky-CI record; doctrine-change protocol added to the audit
  doc so verification precedes edits from now on.

### 1.0.3 — 2026-07-21
- rails-8 › jobs-and-realtime: new §7 "Threading & the Rails executor"
  (executor.wrap doctrine, load interlock, reloadable-constant caching,
  connection-pool rules) — the single doctrine gap found by the framework audit
  against rails/rails 8-1-stable. mission_control-jobs expanded from a one-liner
  to mount-behind-auth + adapter-feature doctrine.
- Audit record: docs/audits/2026-07-21-framework-gap-audit.md — 31-cluster
  coverage matrix vs the 75 official guides + turbo/stimulus/native sources;
  verdict: zero incorrect doctrine, versions exact, P3 backlog logged.

### 1.0.2 — 2026-07-21
- rails-8 › new `references/sso.md`: roll-your-own multi-tenant SSO doctrine —
  OIDC-first with per-workspace dynamic setup, identities keyed [provider,
  issuer, uid], workspace-scoped provisioning with domain gate, enabled-vs-
  enforced with owner break-glass, JIT role sync (per-tenant mappings, ceiling),
  tenant dashboard rules (write-only secrets, step-up, provider-tabbed guide),
  SAML hatch (signing, SP metadata, cert validation + metadata-polling rotation,
  SLO caveats), audit events, nine-spec RSpec proving set. Distilled from
  implementation review of five external guides.

### 1.0.1 — 2026-07-21
- rails-8 › testing: SimpleCov 1.0 — `add_group` renamed to `group` (1.0.2);
  migration note added (segment-boundary string filters, Ruby ≥ 3.2 floor).
  Field-reported from the first live project run. `dist/rails-8.skill` rebuilt.

### 1.0.0 — 2026-07-20
- Initial release: rails-8 (16 references — vanilla-first Rails 8.1 doctrine,
  pure RSpec, Solid stack, Kamal 2, OpenAPI via rswag, ruby_llm) and hotwire
  (Turbo, Stimulus, Hotwire Native) skills, bundled as one installable plugin.

## Repository / marketplace

### 2026-07-24 (release v1.14.0)
- fidara-design **data-visualization layer** (#63, rails-stack → 1.7.0, now 14 references):
  charts/KPIs/dashboards as doctrine — a validated `fm-*`-derived `--color-chart-*` palette
  (adapting Anthropic's `dataviz` method + validator), KPI/chart recipes, and chart a11y
  non-negotiables. design-flow → 1.2.4 (component command routes chart screens through it).
  `metadata.version` → 1.14.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.13.1)
- rails-flow → 1.3.1: removed NotebookLM from the brain flow; the `<org>/brain` git repo is the
  single source of truth for the cross-project shared brain (no external synthesis layer).
  `metadata.version` → 1.13.1. No skill content changed.

### 2026-07-23 (release v1.13.0)
- rails-flow → 1.3.0: the brain leveled up — fuller repo-side memory (STATUS / PROGRESS-LOG /
  DECISIONS / HYPOTHESES-with-lifecycle + provenance tags), a weekly maintenance sweep
  (`/rails-flow:brain-review`), and cross-project federation (`/rails-flow:brain-sync`) via a
  shared brain git repo over `gh` — agentic flows in separate repos coordinate without cloning
  each other, with NotebookLM documented as an optional synthesis lens (not the store).
  `metadata.version` → 1.13.0. No skill content changed.

### 2026-07-23 (release v1.12.4)
- fidara-design reference recipes reconciled with the skill's own non-negotiables (#56,
  rails-stack → 1.6.2): radius (`rounded-lg` not `rounded-[12px]`), `focus-visible` rings on
  Modal-close/Alert-dismiss, and a copyable Lucide `with-icon`/1em call site. Doctrine-verified
  (Tailwind v4 radius namespace; CSS-over-SVG-attribute cascade). `metadata.version` → 1.12.4.

### 2026-07-23 (release v1.12.3)
- **Docs fixes from downstream reports (#41, #42).** #41: a rails-8 URL-design `### 1.0.5`
  CHANGELOG entry was misfiled under `## pipeline`; moved to `## rails-stack` in its
  chronological slot, and fixed a self-doubled heading — so downstream changelog readers map
  entries to the right plugin. #42: README now presents the auto-updating `rails-stack`
  **plugin as the recommended team install**, with the `degit`/vendoring path re-badged as a
  fallback for no-plugin environments (stated re-sync trade-off), and clarifies
  `.claude/skills/` is for project-specific skills — removing the "commit the framework skills"
  guidance that made a downstream team hand-sync two copies. Docs only; `metadata.version` →
  1.12.3, no skill/plugin behavior change.

### 2026-07-23 (release v1.12.2)
- **PR-review backlog triaged into fixes.** Read all 132 review comments across every PR
  (qodo / codex / accesslint); codex was rate-limited (no findings) and accesslint's were all
  ERB/placeholder parse artifacts (the worked code is a11y-correct). The credible engineering
  findings were filed (#43–#46) and fixed:
  - **CI (`release.yml`)** #43: drift guard used `git diff --quiet -- dist/` (blind to
    untracked files) — a new skill's uncommitted `dist/*.skill` passed the no-drift guard
    falsely; now `git status --porcelain -- dist/`. #44: the `release` job now gates on
    `github.ref == 'refs/heads/main'` so a `workflow_dispatch` from a non-main ref can't
    publish a release for that ref.
  - **qa-flow → 1.4.1** #45: closed fail-open bypasses in the release-gate promotion detector.
  - **pipeline → 1.1.1** #46: guarded `/pipeline:ack` git-dir resolution + fixed doc drift.
  `metadata.version` → 1.12.2. No skill content changed (skills/dist unchanged).

### 2026-07-23 (release v1.12.1)
- **Design system wired into the feedback loop.** Issue templates (incorrect-doctrine,
  skill-gap, plugin-bug, feature) now offer `fidara-design` / `design-flow`; new
  `comp:fidara-design` + `comp:design-flow` labels; the `issue-triager` taxonomy and the
  shipped reporter (`/rails-flow:report` + `claude-skills-reporter`, rails-flow → 1.2.1) now
  cover them. fidara-design SKILL.md documents the verification boundary and routes breakage
  upstream (rails-stack → 1.6.1); `/design-flow:setup` nudges the same (design-flow → 1.2.3).
  `metadata.version` → 1.12.1. Closes the gap where the least runtime-verified component had
  no path back into the issue inflow.

### 2026-07-23 (release v1.12.0)
- fidara-design: modal-driven in-page CRUD as first-class doctrine (crud-modal-pattern,
  rails-stack → 1.6.0, now 13 references) + verified Tailwind v4 `@utility` fix for custom
  utilities; whole CSS/JS layer build-verified against the real Tailwind v4.3.3 compiler +
  Node. design-flow → 1.2.2 (component command routes CRUD through the modal pattern).
  `metadata.version` → 1.12.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.11.0)
- fidara-design full component catalog worked as reference code
  (component-implementations, rails-stack → 1.5.0); design-flow → 1.2.1 (component command
  cites it). `metadata.version` → 1.11.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.10.0)
- Mobile Phase 3 (native token export): fidara-design native-tokens (rails-stack → 1.4.0) +
  NEW `/design-flow:tokens` (design-flow → 1.2.0) — generate Android/iOS tokens from the
  `@theme`. Outputs to `tmp/`; native app repos untouched. `metadata.version` → 1.10.0.

### 2026-07-23 (release v1.9.0)
- Mobile Phase 2 (Hotwire Native parity): fidara-design mobile-reference-implementation
  (rails-stack → 1.3.0) + NEW `/design-flow:mobile` (design-flow → 1.1.0). Web-side code only
  (native app repos untouched). `metadata.version` → 1.9.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.8.0)
- fidara-design reference-implementation (concrete ViewComponent + Stimulus-mixin code) +
  mobile parity plan (rails-stack → 1.2.0); design-flow → 1.0.1 (setup points at the reference
  impl). Closes the design system's spec-but-no-code gap, all in the marketplace repo (no app
  refactor). `metadata.version` → 1.8.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.7.0)
- The Fidara design system lands: NEW `fidara-design` skill (rails-stack → 1.1.0) + NEW
  `design-flow` plugin (1.0.0) — consistent, modern, responsive UI without a designer/Figma,
  grounded in the real Fidara assets + Utopia + Every Layout + a modern-library survey.
  `metadata.version` → 1.7.0. rails-8/hotwire skill content unchanged; a new
  `dist/fidara-design.skill` ships (release workflow now uploads all `dist/*.skill`).

### 2026-07-23 (release v1.6.12)
- qa-flow 1.4.0: `setup-qa` inspects the codebase and proposes a recommended testing stack
  (confirm/override; respects existing tooling) instead of asking cold. `metadata.version`
  → 1.6.12. Skills unchanged.

### 2026-07-23 (release v1.6.11)
- qa-flow 1.3.0: free Allure unified reporting wired across all runners/tiers
  (`reporting: allure|both`; `markdown-csv` remains the default). `metadata.version` →
  1.6.11. Skills unchanged.

### 2026-07-23 (release v1.6.10)
- qa-flow 1.2.0: stack-agnostic QA (qa/qa.config.yml — Playwright/Cypress-Cucumber/
  Selenium-pytest-bdd/Appium, free by default; no forced stack) + Autonoma-inspired free
  patterns (auto-mapped flows, self-adapting locators, PR-native results) + opt-in Testmo
  case-management via config. `metadata.version` → 1.6.10. Skills unchanged.

### 2026-07-23 (release v1.6.9)
- qa-flow 1.1.0: free, repo-local case authoring/management (`/qa-flow:cases`) + agentic
  functional testing via Playwright MCP (`/qa-flow:functional`) — no paid/online tool.
  `metadata.version` → 1.6.9. Skills unchanged.

### 2026-07-23 (release v1.6.8)
- Reverse the v1.6.7 approach: maintainer tooling is now **repo-local `.claude/`**, not a
  separate marketplace. `skill-maintainer`'s commands/agents/hook moved into `.claude/`
  (commands renamed `/maintainer-triage` · `-work` · `-audit` · `-setup-intake`), plus a
  detailed `CLAUDE.md` maintainer guide. This is active for anyone who clones the repo and
  is **never** part of the marketplace install surface — cleaner than a second marketplace,
  and no install step. The `fmanimashaun/claude-skills-maintainers` repo created in v1.6.7
  was **deleted**. Marketplace unchanged (still the 4 app plugins). `metadata.version` →
  1.6.8. Skills unchanged.

### 2026-07-23 (release v1.6.7)
- Full separation for #4: `skill-maintainer` **extracted to a separate marketplace**,
  [`fmanimashaun/claude-skills-maintainers`](https://github.com/fmanimashaun/claude-skills-maintainers),
  and removed from this marketplace's manifest (now 4 app plugins). App builders adding
  `fmanimashaun/claude-skills` no longer see it at all; maintainers add the separate
  marketplace explicitly. README + repository layout updated. `metadata.version` → 1.6.7.
  Skills unchanged.

### 2026-07-23 (release v1.6.6)
- Three issues shipped since v1.6.3 (one consolidated dev→main promotion, tagged v1.6.6):
  - skill-maintainer 1.0.1 — #4 maintainer-only separation (manifest marker + command
    repo-type guards + README consistency). *(Superseded by the full extraction in v1.6.7.)*
  - rails-flow 1.2.0 — #2 claude-skills-reporter agent + `/rails-flow:report` (feedback-loop
    sending end).
  - pipeline 1.1.0 — #5 `/pipeline:ack` + auto-clear for the QA-verify nudge marker.
  `metadata.version` → 1.6.6. Skills unchanged. (No v1.6.4/v1.6.5 tags exist — those interim
  bumps were folded into this single release.)

### 2026-07-23 (release v1.6.3)
- Release flow is now automated via GitHub Actions (`.github/workflows/release.yml`):
  a `dev → main` merge (push to main) reads `metadata.version`, and if that tag doesn't
  exist, builds the `.skill` assets with the canonical `package_core.py` and publishes
  the GitHub Release — no manual `gh release`. Version-unchanged pushes are no-ops (tag
  exists). Includes a dist-drift guard (fails the release if committed `dist/` isn't a
  clean build) and pulls notes from this CHANGELOG's `(release vX.Y.Z)` block. Skills
  unchanged; `metadata.version` → 1.6.3.

### 2026-07-23 (release v1.6.2)
- Adopted a proper git flow: `dev` integration branch (now default) → `fix/*` and
  `feature/*` branch off dev, PR into dev; `dev → main` PR cuts the release. Aligns the
  repo with qa-flow/pipeline's own dev→main doctrine.
- qa-flow 1.0.6 closes the #1 heredoc residual; `.env` gitignored (token safety).
  `metadata.version` → 1.6.2. Skills unchanged.

### 2026-07-23 (release v1.6.1)
- First issue shipped through skill-maintainer: qa-flow 1.0.5 fixes #1 (release-gate
  substring false-positive). `metadata.version` → 1.6.1. Skills unchanged.

### 2026-07-23 (release v1.6.0)
- Fifth plugin `skill-maintainer` added and registered in `marketplace.json`;
  `metadata.version` → 1.6.0. Issue intake scaffolded into `.github/` (templates +
  label taxonomy). Skills unchanged — `.skill` assets carry over from v1.5.0.

### 2026-07-22 — truly reproducible packaging (ZIP_STORED)
- `package_core.py` now STOREs entries (no DEFLATE): output no longer depends
  on the zlib implementation — the v1.2.2 caveat (stock zlib vs zlib-ng) is
  closed by construction, and `create_system` is pinned (its default differs
  Windows vs Unix). A clean checkout now builds byte-identical `.skill`
  artifacts on any machine, Python, or OS. Canon bytes change one final time;
  larger uncompressed assets are the accepted cost of reproducibility.

### 2026-07-22 (release v1.2.2)
- Fix `package.ps1` on Windows: the launcher test matched `python.exe` (glob
  `py*`) and passed `-3`, which non-launcher Python executables reject
  (`Unknown option: -3`). Now only the real `py`/`py.exe` launcher gets `-3`.
- Correct the determinism claim (see the entry below): `package_core.py` output
  is byte-stable per zlib/DEFLATE implementation, but compressed bytes differ
  across zlib versions (stock zlib vs zlib-ng produce different output) — the
  archive *contents* are always identical. So a clean rebuild reproduces the
  committed dist only on a matching zlib; the per-release content-normalization
  is retired, but cross-zlib byte-identity is not guaranteed.
- No skill content change; `dist/*.skill` shipped as previously committed.
- `metadata.version` → 1.2.2; released as tag `v1.2.2`.

### 2026-07-22 — deterministic skill packaging
- `scripts/package_core.py` is now the single canonical `.skill` builder:
  fixed timestamps, sorted entries, deflate 9 — byte-identical output on any
  machine. `package.sh` / `package.ps1` became thin wrappers; automated
  rebuilds use the same script. Canon bytes change ONCE with this commit;
  thereafter the committed dist binaries equal any clean rebuild and the
  per-release normalization step is retired.

### 2026-07-22 (release v1.2.1)
- `metadata.version` → 1.2.1, rails-flow → 1.1.0, rails-stack → 1.0.3; released
  as tag `v1.2.1`.
- `dist/rails-8.skill` repackaged (new `references/sso.md`, jobs-and-realtime §7);
  18 entries. Normalized to the canonical `package.*` build (84,598 vs a
  non-canonical 84,730 rebuild — content identical). `hotwire.skill` unchanged.

### 2026-07-21 (release v1.1.8)
- `metadata.version` → 1.1.8, rails-flow → 1.0.8; released as tag `v1.1.8`.
- `dist/rails-8.skill` normalized back to the canonical `package.*` build: a
  prior non-canonical rebuild had diverged in bytes only (78,809 vs 78,675),
  content identical and matching the v1.1.7 asset. Reproducibility restored
  (checkout + `package` now reproduces the committed artifact).

### 2026-07-21
- rails-stack entry now carries an explicit `version` in `marketplace.json`
  (entry-declared plugins accept manifest fields), giving skills the same
  cache-key discipline as rails-flow.
- This CHANGELOG added; supersedes `metadata.version` as the human-readable
  history (that field is not consumed by Claude Code).

### 2026-07-20
- Repository published: skills, `dist/*.skill` packages for claude.ai upload,
  bash + PowerShell installers, README.
- Plugin marketplace manifest added (`/plugin marketplace add
  fmanimashaun/claude-skills`); rails-flow joins as second plugin.
- README grew into the single source of truth: install methods, the agentic
  flow, autonomy, the phased code-review install-and-verify runbook, graphify.
- Releases: v1.0 (skills), v1.1.3, v1.1.4 (post-LF-normalization).
- `.gitattributes` (LF everywhere, binaries marked).

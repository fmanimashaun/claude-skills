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

### 2026-07-22 — remove root-level plugin file duplicates### 2026-07-22 — remove root-level plugin file duplicates
- 14 stale plugin files (agents, commands, hook scripts, plus a stale
  marketplace.json and orphan hooks.json) had been committed to the REPO ROOT by
  an early "Add files via upload" web drag-drop, duplicating — at frozen old
  versions — the canonical files under plugins/**/ and .claude-plugin/. Removed all
  14 (each verified to have a canonical copy first). Hardened .gitignore with
  root-anchored patterns (/*.sh, /hooks.json, /marketplace.json, /plugin.json) so
  plugin files can only live under plugins/** and .claude-plugin/**, never the root.
  No canonical file touched; marketplace remains 1.4.4 with all four plugins.

## rails-flow (agentic flow plugin)

### 1.1.3 — 2026-07-22
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

## rails-stack (skills plugin: rails-8 + hotwire)

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

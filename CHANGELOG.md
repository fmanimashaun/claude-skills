# Changelog

All notable changes to this repository. Components version independently:
**rails-flow** (version in `plugins/rails-flow/.claude-plugin/plugin.json`),
**rails-stack** (version in its `marketplace.json` entry), and repository-level
changes (README, packaging, infrastructure). Every version bump gets an entry here.

## Repository hygiene

### 2026-07-29 — the packager stops depending on your working copy (#171)
- **The prescribed check was satisfiable while producing the drift it exists to prevent.**
  `.gitattributes` is `* text=auto eol=lf` with `*.skill binary`, so git normalises sources to LF on
  commit but stores the artifact byte-for-byte. Packaging a freshly authored file on Windows (CRLF in
  the working copy) produced an archive carrying CRs its own committed sources did not have — 424
  bytes' worth in #94 — while `git status` showed only the intended `dist/` change, so CLAUDE.md's
  instruction passed. It runs *before* the normalisation that creates the mismatch. The drift then
  surfaced at release time, where `release.yml` correctly refused to publish.
- **`package_core.py` now normalises text members itself**, so the guarantee is "byte-identical on any
  machine" rather than "byte-identical from a clean checkout" — it no longer depends on remembering
  anything, which is the only kind of guarantee this repo trusts.
- **Binary detection is git's own heuristic** (a NUL byte in the first 8000 bytes), deliberately not an
  extension allowlist: an allowlist needs maintaining and **fails open**, so the first file type nobody
  added would silently revert to the original bug. A future `.png` in a brand pack is protected without
  anyone listing it. Only `CRLF` is converted, matching git's `eol=lf`; a lone `CR` is left alone.
- **Proven behaviour-preserving, not asserted.** With the change in place all four `.skill` files
  rebuild **byte-identical** to what was already committed — clean input has LF, so a correct
  implementation changes nothing there. Then the original bug was reproduced end to end: all 39 sources
  CRLF-ified (the #94 condition), and every artifact still built byte-identical to the committed
  version.
- **`--selftest` makes it mechanical** (11 assertions): CRLF and LF working copies build identical
  bytes; a NUL-bearing member with `\r\n` inside is stored unmodified (the fixture naive normalisation
  would corrupt); text members carry no CR; entries stay `ZIP_STORED` with `create_system` pinned and
  timestamps fixed. Two bugs in that selftest were caught while writing it — an incoherent assertion,
  and one scanning the whole archive for `\r` when a ZIP's CRC and size fields can legitimately contain
  `0x0D`, which would have failed spuriously.

### 2026-07-29 — doctrine effect becomes measurable (#156), and the reviewer moves in-repo (#162)
- **The asymmetry this closes.** Doctrine *content* has a hard gate: nothing is edited until
  `doctrine-verifier` confirms it against an authoritative source. Doctrine *effect* had none.
  "The rails-8 skill produces better Rails" lived entirely in prose — the one layer this repo
  otherwise refuses to trust. New `evals/` measures whether loading the skills changes what an
  agent writes. Secondary benefit, possibly the larger one: **a doctrine edit that makes agent
  output worse was undetectable**; a regression is now visible.
- **Runner is `claude -p`, not the Anthropic API.** The obvious build pastes `SKILL.md` into an
  API `system` field — clean, cheap, and measuring the wrong thing. These skills ship as Claude
  Code *plugins*, so a pasted system prompt is a proxy for how they load; a result from it would
  not be evidence about what `/plugin marketplace add` actually gives a user. Consequence worth
  having: **no Anthropic API dependency**, so the harness stays stdlib-only Python with no
  `requirements.txt` and nothing for CI to install.
- **Two gates specified in #156 were wrong, and would have manufactured false regressions.**
  (a) The issue asked for an "ids only" job gate; `jobs-and-realtime.md:28` says the opposite —
  `def perform(order)  # pass records, not ids: GlobalID (de)serializes them`. An ids-only rule
  fails the doctrine's own reference example, so the real-skill arm would have scored *worse* than
  baseline and "proven" our doctrine harmful. Only idempotence is gated (`:176`). (b) A naive
  no-hex rule flags our own `Ui::Logo`, which `brand.md:87` names as "the only component permitted
  to carry literal colors"; the carve-out is encoded. Generalised as a standing rule that
  `selftest.py` asserts: **a gate must pass against the doctrine's own reference examples — if it
  fails what `references/*.md` shows as correct, the rule is wrong, not the doctrine.**
- **A third rule needed fairness, not correction.** `form_with` is correct stock Rails, and
  `ecosystem-gems.md:29` makes simple_form conditional ("dozens of uniform CRUD forms"). So
  `scaffold.py` establishes the convention (Gemfile entry + initializer) and the gate **refuses to
  judge** when it is absent, rather than punishing an agent for writing correct Rails.
- **Gates vs measurements, kept separate.** Six named rules, each citing the doctrine file:line it
  enforces, are grep/parse pass/fail. Cost, wall-clock, output tokens, and turn count are recorded
  and never judged — "less code" is trivially gamed by emitting something broken. A run that
  errored, hit the API error path, or was blocked by a permission prompt is **INVALID** and
  excluded from scoring: scoring infrastructure trouble as a doctrine failure invents a regression.
- **Isolation is asserted, not assumed.** Runs never execute in this repo — our `CLAUDE.md` would
  load into *every* arm, contaminating all three identically and drifting the result toward "no
  difference" without looking broken. `scaffold.py` refuses to run when an ancestor holds a
  `CLAUDE.md`, when a non-home ancestor holds `.claude/`, or when `~/.claude/skills/` is non-empty
  (skills-dir plugins auto-load into every session). Tools are restricted to
  `Read,Write,Edit,Glob,Grep` — no Bash, no network.
- **Verified without spending anything on a benchmark.** `selftest.py` — 38 assertions, every rule
  proven to fire on a violation *and* stay silent on conforming code (a rule that flags everything
  looks rigorous and makes all arms fail equally). `run.py --dry-run` prints all 15 invocations and
  executes none. The staged `real` arm passes `claude plugin validate` with all three skills
  (14/3/17 references) and no maintainer `.claude/` leaked. **No results are published**, and the
  README's results table is deliberately empty pending authorisation.
- **Deliberately disposable runner.** `claude plugin eval` already does this properly
  (`--ablation with-without`, `--runs`, `--threshold`, `--json`, `--max-cost-usd`, HTML reports)
  but is in early access and unavailable here. The durable assets are `cases/*/prompt.md`,
  `gates.py`, and `selftest.py`; when early access opens, point it at `evals/` and delete `run.py`.
  Metadata is `suite.json`, not `case.yaml`, because `yaml` is not in the stdlib.
- **Out of the release path.** Nothing wired into CI. It costs money, it is opt-in, and it must
  never gate a promotion.
- **Four bugs found in review, all in the new harness** (#161). Two would have corrupted results in
  opposite directions: (a) `read_lines()` promised Ruby comment handling but only blanked ERB
  comments, so a palette note in a `.rb` component (`# cerulean is #0077CC`) was reported as a
  violation — a false regression. Stripping is now quote-state-aware (the token we hunt for *is*
  `#`, so splitting on the first one would have deleted every violation) and applied to `.rb` only,
  never `.erb`, where a bare `#` is HTML text and blanking to end-of-line would hide violations
  after it. (b) The `Ui::Logo` carve-out matched any path containing `logo`, making it a one-line
  bypass — name a partial `logo.html.erb` and hardcode anything. Now an explicit allowlist of the
  component's canonical paths. Plus: `--max-total-usd` is **enforced** rather than merely
  documented (a live run without it refuses to start), and `max_turns` is removed from `suite.json`
  because the CLI exposes no `--max-turns` — a declared condition nothing enforces is worse than an
  absent one, so turn count is measured and spend is bounded by the budget ceilings instead.
  Selftest grew 32 → 38 assertions.
- **The realisation.** A trial reviewer kept finding a class of bug our own review missed,
  and it had no proprietary advantage: **it checked the diff against rules already written in
  this codebase's markdown.** Its finding on #161 was literally "missing change-type
  classification" — verbatim from `CLAUDE.md`; others were our own README and `suite.json`
  contradicting our own code. The capability was never rented; the rules were always here,
  nothing was *asking* them of a diff.
- **The class.** Every existing review dimension asks *"is this code correct?"*. The misses all
  came from a different question: *"does this code do what its own documentation, config and
  comments claim?"* Correct-looking code passes the first and fails the second — and the author
  cannot see it, because they read the claim and the code as one thing.
- **`claims-vs-enforcement` has now bitten three times in three PRs**: `--check || echo` making a
  release gate unable to block (#151); a README mandating `--max-total-usd` while the flag stayed
  optional (#161); a docstring promising Ruby-comment handling the code lacked (#161). Writing the
  rule down does not prevent it — the thesis of `lint_markdown_shell.py`, now pointed at our claims.
- **New `scripts/lint_self_consistency.py`** (stdlib, free, no LLM) mechanises the judgement-free
  subset: `dead-settings-key` (a key in a JSON settings block no reader reads) and
  `unenforced-mandatory-flag` (a flag documented as mandatory that code leaves optional).
  **Known-answer calibrated:** run against the pre-fix commit it independently reproduces 2 of the
  5 trial-reviewer findings; against the post-fix commit it is silent with the same inputs
  examined. `--selftest` (8 assertions) proves both rules fire *and* stay silent — a rule that
  flags everything gets disabled after the third false positive and then catches nothing. Its own
  selftest caught a real limitation during authoring: the guard regex hardcoded `parser.error`, so
  it missed a guard on any parser not named `parser`.
- **Coverage is reported even when clean**, because "no findings" over input never read is worse
  than no linter — the `--audit-coverage` lesson, where a fence regex silently skipped 11 blocks.
- **The classes no machine catches became a shipped skill, not a `docs/` file.** First draft put
  them in `docs/review-rubric.md` *and* inline in two agent files — two homes for one doctrine,
  which is precisely the drift this repo exists to prevent, and `docs/` was referenced by nothing,
  so the discovery path that made the trial reviewer work (read the codebase's own markdown rules)
  never reached it. Now `skills/code-review/SKILL.md` is the single source:
  `carve-out-without-negative-test`, `coverage-gap`, `doctrine-contradiction`,
  `unverified-negative` (count first, then read), `gate-that-cannot-fail`. Every class is named and
  traceable to a real finding; a class with no instance behind it is speculation and is excluded.
- **Placing it in `skills/` is the load-bearing decision.** Rules a reviewer must find belong where
  reviewers already look, and as shipped doctrine it is the *same* rule set a user's `pr-reviewer`
  applies — so we are held to what we sell rather than keeping a private checklist.
- **Wired into `CLAUDE.md` and `/maintainer-work` Phase 3** — apply the class list to your own diff
  before asking anyone else to.


### 2026-07-29 — promotions get a two-step name and a divergence assertion
- **"Arm" vs "promote", named.** The v1.22.0 promotion used a branch called `release/v1.22.0`
  merging into **`dev`**, which reads as though `dev` publishes releases. It does not and cannot:
  the workflow triggers only on `push: branches: [main]` *and* re-checks
  `github.ref == 'refs/heads/main'` in the job — verified, zero workflow runs have ever originated
  on `dev`. But the naming made an invisible mechanism look wrong, so step 1 is now
  `chore/arm-vX.Y.Z` titled "version assignment (does not publish)", and `CLAUDE.md` states the two
  steps in a table with which one publishes.
- **A merge unions; it does not override.** Recorded as a correctness rule rather than tidiness:
  merging `dev → main` never removes content that exists only on `main`, so a direct commit there
  is permanently invisible to every future `dev`-based change. One such commit exists in this
  repo's history (`d4b35f6`, `enabledPlugins` in `.claude/settings.json`); it converged only
  because the same block later reached `dev` — luck, not a property of the merge.
  `release-manager` now asserts `git log --no-merges origin/dev..origin/main` before promoting.
- **How to read branch state.** Judge `dev` against `main` with `git diff dev main` (empty after a
  promotion), never the ahead/behind counter: `main` gains one merge commit per release that `dev`
  never receives, so `dev` reads as tens of commits "behind" while being content-identical.
  Merging `main` back into `dev` to tidy the counter is what produced 37 no-op merge commits on
  `dev` earlier in the week.

### 2026-07-29 — the shell inside markdown is now verified (root cause of #151)
- **The repo mandated `bash -n` for `.sh` files and shipped 194 unverified lines of bash inside
  markdown** — 51 fenced blocks across 30 command/skill files, the lines an agent copies and runs
  verbatim in a user's project. Three review findings in one week lived in that gap: the
  `--check || echo` that made the release gate unable to block (#151), the same file's guard
  conflating "no data" with "no tool", and design-flow's unresolvable lint path. Each was
  prose-reviewed and never executed. The #151 fix stated a rule ("a guard decides whether to run
  a check; it must never soften the verdict") — but a rule is not a guarantee, which is the one
  thing this repo's doctrine is explicit about.
- **New `scripts/lint_markdown_shell.py`** (stdlib only): extracts every fenced shell block and
  runs `bash -n` on it (template placeholders substituted first, since `<pack>` is a redirect to
  bash), then flags **swallowed verdicts** (`|| echo`/`|| true` on a verification command) and
  unquoted test operands. **Regression-proven**: run against `release.md` as shipped in v1.21.0 it
  reports the `--check || echo` at line 82 and exits 1; against the fixed file it exits 0.
- **`--audit-coverage`**, because the first version of the fence regex **silently skipped 11 blocks
  in 7 files** by anchoring ` ``` ` to column 1 — blocks nested in numbered lists are indented. A
  lint that reports clean on input it never read is worse than no lint, so coverage is now
  cross-checked against an independent looser scan and a gap is a failure. (Same column-1
  assumption `brand_pack_lint` had; second time it bit.)
- Wired into `CLAUDE.md`, `/maintainer-work` Phase 3, and `plugin-doctor`, so it runs without
  being remembered.
- **Coverage is reconciled on every run, not on request.** `--audit-coverage` was a separate
  command, so a future tweak to the fence regex could still quietly reduce coverage while the
  default run reported clean — the same defect one level up. Every run now cross-checks the strict
  parser against an independent looser scan and **refuses to report clean when they disagree**.
  Proven with a fence the strict regex cannot parse (inside a blockquote) that contains a real
  swallowed verdict: the tool exits 1 saying a clean result would be meaningless, where before it
  printed "no findings".
- Four bugs were found *in the linter itself* while proving it, all silent-failure shaped: `bash -n
  <tempfile>` broke under Git Bash (mangled Windows path → every block a false syntax error);
  `text=True` encoded stdin as cp1252 and crashed on a `✓`; a nonexistent path reported "0 files,
  no findings" instead of erroring; and `verify` matched inside `pipeline-verify`, flagging an
  idempotent `docker rm … || true`. Worth recording that three separate escaping mistakes wrote
  literal control characters (``, TAB) into the source via heredoc patching — invisible in
  output, and the regex matched nothing. Author code with an editor, not with nested string layers.

### 2026-07-28 — the doctrine gate gets an explicit scope
- The verification gate said "no skill claim is edited until `doctrine-verifier` confirms it against
  an authoritative source", without stating what counts as a claim. Our own architecture decisions
  (the brand-pack model, the role contract, distribution policy) have **no upstream to cite**, so
  the verifier returns INCONCLUSIVE for want of a source — and "INCONCLUSIVE leaves doctrine
  unchanged" would then block our own decisions permanently. The exemption was therefore being
  decided per PR by whoever wrote it, which is precisely what a gate exists to prevent. Review
  flagged it on #149; the finding was correct.
- `CLAUDE.md` now scopes it: the gate covers **externally verifiable claims** (framework/gem
  behaviour at a stated version); for **design/architecture** changes the authority is the
  maintainer's explicit decision **recorded on the issue** — the durable equivalent of a citation.
  Four rules stop that becoming a loophole: declare which kind of change you are making *before*
  editing; split a mixed PR so a framework claim still needs CONFIRMED; reuse established framework
  syntax rather than inventing it (new API *is* an external claim); and measure anything measurable
  against the repo's own files with a re-checkable script.

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

### 1.10.0 — 2026-07-29
- **The grep matched what it was meant to allow.** `grep -rn "form_with\|form_for" app/views`
  also matches **`simple_form_for`**, because that string ends with `form_for` — so the mandate
  check fired on every *correct* form. A check that flags everything is as useless as one that
  cannot fire: it gets ignored, then disabled. Fixed with a word boundary
  (`grep -rnE "(form_with|form_for)"`), verified against a fixture containing one correct
  `simple_form_for` and one offending `form_with` — only the offender is reported.
- **Added the check that actually catches violations.** The mandate covers form *elements*, not just
  the form tag, and hand-rolled anatomy was unchecked: `f.label` with a manual error `<p>`, or a
  ViewComponent emitting its own `<label>`, is a form element built without simple_form. Now flagged
  in `app/views` **and** `app/components`.
- **A stock `config/initializers/simple_form.rb` is BLOCKING.** If the wrapper carries no role-token
  classes, fields are unstyled by the design system and every view is tempted to patch classes per
  input — which is precisely the drift the mandate exists to prevent.

### 1.9.0 — 2026-07-29
- **A doctrine contradiction was live in users' hands, in three files.** `pr-reviewer.md` told the
  merge gate to check jobs for "id args", `rails-developer.md` said "pass IDs, never AR objects",
  and `setup-flow.md` wrote "job shape (ids only)" into the generated project CLAUDE.md. But
  `skills/rails-8/references/jobs-and-realtime.md:28` says the opposite — `def perform(order)
  # pass records, not ids: GlobalID (de)serializes them` — and :39 lists records (GlobalID) as
  serializable. **So the shipped merge gate would block a PR for correctly following our own
  doctrine**, the developer agent would write the wrong thing, and setup-flow would propagate the
  wrong rule into the user's own doctrine file for pr-reviewer to then enforce against them.
  Self-reinforcing, and worse than a plain bug because it blames the user.
  **No framework claim is introduced or changed here, deliberately.** `skills/rails-8` is
  untouched, and review flagged that the first draft *restated* the mechanism (GlobalID,
  `discard_on`) in three shipped plugin files — which would have been authoring an externally
  verifiable claim, and `CLAUDE.md` requires a CONFIRMED `doctrine-verifier` verdict for that even
  when the rest of a PR is an architecture decision. So the plugin text now **defers** to the
  rails-8 jobs doctrine instead of paraphrasing it: the corrected rule is "do not demand ids-only;
  follow the project's own job doctrine", and the mechanism stays in the one place that already
  carries it. Same single-source principle this branch applies to the review classes.
  Found by applying the rubric's `doctrine-contradiction` class systematically with one grep rather
  than fixing the single instance review happened to surface.
- **`code-reviewer` and `pr-reviewer` now ask claims-vs-enforcement explicitly** — the class an
  author is systematically blind to, because they read the claim and the code as one intention
  rather than two artefacts that can disagree. Both **delegate to the new `code-review` skill**
  rather than restating its classes, so there is one source of the doctrine and no drift between
  agent and skill. Both keep two habits in the verdict itself: when a claim and the code disagree
  the reviewer decides *which* is wrong (the fix is not automatically the code), and on finding one
  contradiction, grep for the pattern — that class travels in groups.

- **The mechanical half now ships too (#164).** #162 gave users the *doctrine* and kept the
  deterministic check maintainer-side — backwards, since this repo's whole thesis is that a rule
  left in prose gets violated again. New `scripts/self_consistency.py` (stdlib; a Rails repo must
  not need a pip install to review itself) plus a `PostToolUse` hook on `Edit|Write|MultiEdit`
  beside `lint-ruby.sh`.
- **Four rules, each mechanising a named `code-review` class:** `swallowed-exception`
  (`rescue nil`, empty rescue), `swallowed-verdict` (`|| true` on a verification command — the
  `--check || echo` shape that made a release gate unable to block), `assertion-free-spec` (an
  example that runs code but asserts nothing, so it passes whatever the code does), and
  `dead-env-var` (a key in `.env.example` nothing reads).
- **Two candidate rules were cut, not softened.** `unenforced-documented-step` and
  `carve-out-without-negative-test` need judgement — matching a `skip_before_action` is easy,
  proving no spec covers the near-miss is not. A rule that guesses produces false positives, gets
  disabled, and then catches nothing; both stay with the reviewer and the skill, which is the right
  layer. The standard applied was: zero false positives on a conforming repo, or cut it.
- **The hook exits 2 on findings, deliberately.** A check that can only advise is itself a
  `gate-that-cannot-fail` — one of the classes it enforces — so shipping an advisory-only version
  would have violated the doctrine it exists to uphold. It fails *open* on a missing `python3`,
  because a guard decides whether to RUN a check and must never soften the verdict.
- **Calibrated, and non-vacuously.** 22 selftest assertions prove every rule fires on a violation
  **and stays silent on conforming code** — including the cases that would otherwise be false
  positives: `#` inside a Ruby string, a commented-out `rescue nil`, `|| true` on a *cleanup*
  command, a one-liner `is_expected`, an example delegating to shared examples, a `pending`
  placeholder, and an env key referenced from a non-Ruby file (Kamal `deploy.yml`). Run against
  this repo it examines 25 files and 4 env keys and reports nothing — coverage prints on every run,
  because "no findings" over input never read reads as a pass.
- `pr-reviewer` now runs the repo-wide pass first and treats its output as BLOCKING evidence, then
  reasons about the classes no machine catches.

### 1.8.0 — 2026-07-29
- **`architecture_graph.py --if-present`** — with `--check`, a missing `graph.json` exits 0 instead
  of reporting DRIFT, because the graph is opt-in per project. Added so a caller never has to
  branch on the file's existence in shell: that guard belonged in the script, and putting it in a
  command doc's prose is how #151 shipped a release gate that could not block. Without the flag a
  missing graph is still DRIFT, which is correct for a project that opted in.

### 1.7.0 — 2026-07-27
- **Living architecture graph** (#141): `/rails-flow:graph` extracts `{nodes, edges, flows}` from
  `config/routes.rb`, `app/**` and `db/schema.rb` into three artefacts — `docs/architecture/graph.json`
  (machine-readable), `index.html` (human, interactive) and `graph.md` (mermaid, for GitHub file
  views). One extraction, three consumers: humans get a picture, agents get structural context
  without reading the whole codebase, qa-flow gets reverse dependencies for a **computed** blast
  radius (#134 becomes a consumer instead of needing its own extractor).
  - `plugins/rails-flow/scripts/architecture_graph.py` — **stdlib Python 3 only**: no gems, no graph
    tool, no network, no app boot, so it runs in any clone. Node kinds: controller · model · job ·
    mailer · service · component · Stimulus controller · route · table · channel (+ `concern`, which
    the specified `includes` edge needs somewhere to point). Edge kinds: `references` · `persists` ·
    `enqueues` · `renders` · `broadcasts` · `includes` · `belongs_to`/`has_many`/`has_one`, one
    uniform direction (subject → object).
  - **`flows`** are the part a generic code-graph tool does not give you: named, ordered request
    paths ("Create an invoice": `POST /invoices` → controller → model → job → turbo_stream), built
    from the action body plus the private helpers and `before_action` callbacks that actually apply
    to that action (`only:`/`except:` honoured — ignoring them made every action claim work it does
    not do).
  - **Drift check** (`--check`) mirrors the proven `dist/` guard by rebuilding and comparing a
    `content_digest` over `{nodes, edges, flows}`. Digesting the *extracted structure* rather than
    fingerprinting input files means a prose-only view edit cannot raise a false finding, while a
    real structural change cannot hide; `generated_at`/`commit` are excluded, so re-running on an
    unchanged tree is a no-op. Exit 1 = the code moved and the graph did not.
  - **`--delta <ref>`** prints the release-notes delta — new/removed nodes and **flows that changed
    shape** ("flow *Create an invoice* gained a step"), which is what a 40-file diff cannot tell a
    reviewer.
  - **Self-contained HTML by decision** (maintainer ruling on the issue's open question): inline CSS
    and vanilla JS, JSON embedded *and* written as a separate file, **zero external requests** — no
    CDN, no webfont, no remote image, no `fetch`. It opens from a clone, offline, years later.
    Verified mechanically (12 external-request patterns, all zero) and by executing the inlined JS
    against a DOM stub: node/flow selection, cross-link navigation, layer filtering, search, and
    keyboard nav all run clean. Fidara dark-palette values are copied literally with a comment
    saying so (a standalone file cannot read `@theme` tokens); layer is always stated as text, never
    colour alone; visible focus rings, `prefers-reduced-motion`, and a `@media print` block.
  - **Enrichment is quarantined**: `--enrich` folds in `graphify`/`code-review-graph` edges but into
    a separate `enrichment` block **excluded from the digest** — otherwise CI would report drift for
    a teammate's missing local tool. The foreign schema is probed, and a mismatch is noted, never
    guessed at.
  - **Limits are announced, never silent**: unmodelled route DSL (`mount`/`match`/dynamic), flow and
    mermaid caps, and id collisions all land in `notes`, surfaced in the console and persistently in
    the HTML sidebar.
  - Lifecycle: `doc-updater` regenerates at session end (step 5); `setup-flow` offers generation
    (§6b), adds a graph-freshness item to the `loop.md` maintenance pass, proposes the CI drift job
    as an approved diff (§8), and points agents at `graph.json` before grepping.
  - Verified against a synthetic Rails app covering nested/member/collection/namespaced/singular
    routes, `%i[]` callback options, concerns, ViewComponent, Stimulus, Turbo, and `Current.`-scoped
    queries. Fixed while building: `concerns/` mis-namespaced as `Concerns::X` (broke every
    `includes` edge), nested resources missing the parent `:invoice_id` segment, and non-ASCII
    console output mangled on Windows code pages.
  - **Post-review fixes** (Qodo findings on PR #143, folded in here because 1.7.0 had not yet been
    promoted to `main`):
    - **Flow identity is no longer the display name.** `compute_delta()` keyed flows by `name`, and
      `flow_name()` dropped namespaces — so `Admin::InvoicesController#index` and
      `InvoicesController#index` both produced "List invoices" and one **silently vanished from
      every delta** (measured: 7 of 8 flows survived the dict). Flows now carry a unique `id`, the
      delta keys on a version-stable `trigger + entry` pair, and the display name keeps its
      namespace ("List invoices (admin)"). The reviewer's suggested fix — keying on `id` — was
      implemented, tested against a simulated older `graph.json`, and **rejected**: it reported all
      8 flows as simultaneously added and removed, because a delta compares two schema versions and
      so the key must be derivable from fields both sides have and neither redefines.
    - **`/pipeline:release` no longer breaks graph-less projects**: the prose said "skip silently"
      while the commands ran `--check` unconditionally, which exits 1 on a missing `graph.json`. Now
      guarded by a file test, with the skip path stated.
    - **Accessibility**, against this repo's own design doctrine: base type is `1rem` not `15px` (a
      px base overrides the reader's browser font-size preference), and `min-h-touch` (44px) is
      applied under `@media (pointer: coarse)` — full finger-sized targets where a finger aims,
      preserving the density a 40-row graph browser needs on a mouse, which still clears the 24px AA
      floor (~27px buttons, ~31px rows).
    - **Enrichment dedupe** no longer rebuilds the base-edge set once per candidate edge
      (O(base×enriched) → O(base+enriched)), and collapses duplicates within the enriched input.

### 1.6.0 — 2026-07-25
- **File-then-fix discipline for mid-session defects** (#73). The flow intended issue-driven fix
  work but nothing steered it there when defects surfaced *interactively* (user reviewing the running
  app: "this is broken", "also this") — the result was ad-hoc hot-fixing, several unrelated fixes
  stacked on one branch, no issues filed. Now:
  - `fix.md` **Setup**: if the defect surfaced live and isn't filed, **file it before touching code**;
    if several surfaced, file them all (batched), then work them **one at a time**, own branch → PR →
    spec. Never hot-fix onto the checked-out branch.
  - `issues.md` gains **Phase 0 — Capture unfiled defects**, the route from "surfaced in conversation"
    into the tracker queue (the command only ever saw `gh issue list` before).
  - `setup-flow`'s CLAUDE.md scaffold always includes the file-first ALWAYS-rule.
  - **SessionStart advisory** (fail-open, never blocks): ≥2 fix-shaped commits on a branch with no
    issue reference → prints a nudge back to `/rails-flow:fix` · `/rails-flow:issues`. Verified: fires
    on unreferenced fix stacks, silent on `fix/issue-NN-*` branches.

### 1.5.0 — 2026-07-25
- **setup-flow scaffolds economical GitHub CI** (#76): a new step checks `.github/workflows/ci.yml`
  and, when it runs the full matrix on every PR/push (the Rails default), proposes scoping the
  triggers to the `dev → main` gate **as an approved diff — never a silent rewrite** (idempotent;
  leaves it alone if already economical or the user declines). Local gates + qa-flow stay primary
  for `feature → dev`; hosted CI is the independent check at `dev → main`; `workflow_dispatch` stays
  on-demand.

### 1.4.1 — 2026-07-25
- **Review/audit agents report ALL findings — no self-triage** (#77). `security-auditor`,
  `code-reviewer`, `design-auditor`, `pr-reviewer`, and the `/rails-flow:review` synthesis had
  output contracts that let a pass *silently drop* a real finding — downstream, `security-auditor`
  self-dismissed a token-in-URL and a login-CSRF finding as "accepted residual"/"awareness-only"
  and never surfaced them. Every contract now mandates: **report every finding** (any severity)
  with `file:line` + repro + fix option(s), **issue-ready**; **do not decide disposition** (no
  "accept / won't fix / no action / residual—ignore" — a residual is still reported as low-severity);
  the fix-flow + human decide whether/how to fix. Verdict (CLEAN/BLOCKED) stays, but the full list
  ships regardless. Synthesis now only *orders* findings, never drops them. Security findings are
  never reviewer-dismissed.

### 1.4.0 — 2026-07-24
- **Local brain-review cadence nudge** (#65) — the maintenance sweep now actually fires on time.
  `/rails-flow:brain-review` stamps an epoch into `docs/brain/.last-review`; the SessionStart
  hook reads it and nudges *"brain-review due"* when the last sweep is older than the cadence
  (default **7 days**, override `RAILS_FLOW_BRAIN_REVIEW_DAYS`), or *"no sweep on record"* if it's
  never run. Reminder-only — never auto-runs; dismiss by re-stamping. Fully **local/offline**, no
  cloud, hook fails open. (Filed under pipeline as the nudge-pattern owner; implemented in
  rails-flow, where `brain-review`, `docs/brain`, and the brain-surfacing SessionStart hook live.)
  `setup-flow` documents the cadence.

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

### 1.1.4 — 2026-07-29
- **Moved the decision out of the markdown entirely.** The fix above still shipped a 12-line,
  three-branch shell guard in a doc — and a doc is the one layer nothing tests. The branching only
  existed because `--check` conflated *absent* (a legitimate opt-out) with *stale* (a defect), so
  the prose compensated for a missing flag. `architecture_graph.py` now takes **`--if-present`**,
  which owns that judgement in tested Python, and the doc carries two plain invocations with no
  branching at all. If the script is not vendored the command fails on its own — which is the
  correct outcome and deletes the misleading-skip branch rather than fixing it.
  Verified: absent + `--if-present` → 0 · absent without it → 1 · stale → 1 · fresh → 0 · script
  missing → non-zero. Old snippet vs new on the same drifted repo: **0 vs 1**.
  The general rule, now stated in the doc: **bash is for commands, Python is for decisions.** Every
  finding this week came from a snippet that encoded a decision; none came from a plain
  `docker build` / `git push`.
- **The architecture-graph drift check could not block a release** (#151, shipped in v1.21.0). The
  snippet in `/pipeline:release` ran `python3 "$GRAPH" --check || echo "…"`, and `|| echo` consumes
  the non-zero exit — including under `set -e`. A stale graph printed a warning and the release
  proceeded. That is worse than having no check, because the message makes it look like the gate
  ran. Proven before/after against the same drifted repo: old snippet exit **0**, fixed snippet
  exit **1**.
- **The skip branch conflated two different causes.** `[ -f "$GRAPH" ]` was ANDed into the
  absence test, so a project that *had* `docs/architecture/graph.json` but had not vendored the
  script reported *"no architecture graph in this project — skipping"* and silently skipped
  verification. Since the graph is opt-in per project while the script is vendored manually, that
  combination is likely rather than exotic. Now three branches: no graph → skip (exit 0); graph
  but no script → **error, exit 1** (a project that opted in and cannot verify must stop, not
  skip); otherwise run `--check` and let it fail.
- Root cause worth recording: this was introduced *while fixing* an earlier review finding. The
  unguarded `--check` broke graph-less projects, so a guard was added — and making the failure
  non-fatal made it non-functional. **A guard decides whether to run a check; it must never soften
  the verdict.**
- `/pipeline:release`'s Report section now requires the graph verdict as one of three explicit
  words — `verified` / `skipped` / `FAILED` — so a skip can never be read as a pass.
- Verified `scripts/release_local.sh` and `.github/workflows/release.yml` for the same softening:
  both already hard-fail (`fail`, `exit 1`), so the defect was confined to this one snippet.
- Found by review on PR #144 and **missed** on the first read — the comment list was truncated, so
  four of five findings were addressed and reported as "four findings". Count first, then read.

### 1.1.3 — 2026-07-27
- **Release verifies the architecture graph and reports its delta** (#141): `/pipeline:release` now
  runs the graph drift check before reporting and pastes `--delta origin/main` into the release
  notes, so a release carries its structural story (new/removed nodes, flows that changed shape)
  alongside the image digest. Release is the second cadence at which the graph must be true — the
  first is session end, via rails-flow's `doc-updater`. Skips when the app has no
  `docs/architecture/graph.json` (the graph is opt-in) — the skip is a real file guard, since
  `--check` exits 1 on a missing graph and an unguarded call would report every graph-less project
  as a failed release (Qodo finding on PR #143, fixed before promotion). Guidance-only; no hook or
  script changed.

### 1.1.2 — 2026-07-25
- **setup-pipeline CI-economy alignment** (#76): notes that pipeline's own release/build workflows
  are already `main`-only, and points at `/rails-flow:setup-flow` to scope the Rails-default
  `ci.yml` to the `dev → main` gate too — so the hosted CI runs only where it's the independent
  check, consistent with the pipeline release gate. Guidance-only.

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

### 1.5.1 — 2026-07-25
- **functional-tester never touches git** (#78) — it was auto-committing its run evidence
  (report + screenshots **and ~35 ephemeral `.playwright-mcp/` session dumps**) to the checked-out
  branch and pushing, landing 50 files on `origin/dev` unreviewed on a "no code changes" prompt.
  The agent's output contract now forbids all git ops: write **only** under `qa/manual-tests/`,
  leave it uncommitted in the working tree for the coordinator to commit via the normal flow, and
  **never** stage `.playwright-mcp/` (ephemeral MCP state) or push to a shared branch. `setup-qa`
  now gitignores `/.playwright-mcp/` as a backstop.

### 1.5.0 — 2026-07-24
- **NEW `/qa-flow:smoke`** (#64) — the build-verification floor: **launches the app**
  (stack-aware, from a new `app:` block in `qa/qa.config.yml` — `start`/`port`/`health`/`routes`/
  `boot_timeout`, Rails-defaulted `bin/dev` + `/up`), waits for health, hits key routes (5xx =
  fail), sets `QA_BASE_URL`, and tears the server down (trapped). Closes the gap where
  `verify` Phase 0 only *assumed* a booted app and Phase 1 ran full `@smoke` E2E against it — now
  "the build won't boot" is caught in seconds with the real boot log, before any heavier phase.
  Stack-agnostic (only the `app:` config differs), free (the app's own server + curl). `verify`
  Phase 0/1 now run `/qa-flow:smoke` first; `setup-qa` scaffolds the `app:` config block.

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

### 1.5.0 — 2026-07-29
- `/design-flow:component` step 1 previously said a screen should be built by "composing existing
  components + layout primitives" and gave nowhere to compose *from* — no page-level doctrine
  existed. It now routes any request above component scale (a page, a dashboard, a settings area)
  through `page-anatomies.md` first: pick a shell, pick an anatomy, then fill each region.
- Also points at that file's primitive-instead-of-breakpoint substitution table and the
  chrome-vs-content type assignments, to be applied **before** writing markup rather than caught
  later by `/design-flow:audit`.

### 1.4.0 — 2026-07-29
- **`/design-flow:setup` takes a brand pack**, not a two-value brand enum: `<pack>` or
  `<pack>:<variant>` (e.g. `fidara`, `fidara:fmworkflows`, `acme`). Generating the theme layer is
  now the ONLY brand-dependent step — everything else is brand-neutral and identical for every
  pack, which is what "a pack is a theme, not a fork" means in practice. Setup lints the pack
  first and refuses to scaffold on failure.
- **New `scripts/brand_pack_lint.py`** — stdlib Python 3, the mechanical guarantee behind the
  model. A pack that omits a role does not fail at runtime; the role silently falls back to a
  stock Tailwind colour and the brand breaks in one corner of the app. So it is checked:
  - every role in the **22-role contract** is defined; surface roles carry their `-foreground`
    companion and a `.dark` re-point
  - no `var()` points at a primitive the pack never defines
  - **a variant carries no values** — the check that makes drift from a parent pack impossible
  - no `@utility` / `@apply` / component CSS leaked in (that would be a fork, not a theme)
  - `brand.json` complete, knob values within their enums, `chart_palette_validated: true`
  - two subtleties encoded from measurement, not assumption: `--background`'s companion is
    `--foreground` (not `--background-foreground`), and the feedback roles plus `--ring` are
    deliberately **not** re-pointed on dark — demanding 22 dark values would fail every correct
    pack, and a check that cries wolf gets ignored
  - `--roles-from` re-derives the contract from `foundations-tokens.md` and reports drift, so the
    duplicated role list cannot silently diverge from doctrine (verified in sync: 22 roles,
    15 dark re-points)
- **New reference packs**: `brands/fidara/` (the calibrated pack, carrying the `fidara` and
  `fmworkflows` variants) and `brands/_template/` (a client skeleton — copy, set colours, drop in
  the logo, validate). The template deliberately fails the lint until its palette is validated.
- `brand-guardian`, README and the plugin description no longer assert "two brands".
- **The first real run of a pack IS the verification step**, and it reports back. The lint proves
  a pack is internally complete; it cannot prove the *contract* matches reality. So
  `/design-flow:setup` now ends with a four-point check — Tailwind builds, roles resolve in light
  and dark, `Ui::Logo` renders the right variant's endorsement, dark mode re-points — and files an
  issue via `/rails-flow:report` on any failure. The highest-value case is called out explicitly:
  **a pack that lints clean but still renders a stock Tailwind colour means the 22-role contract is
  incomplete**, which every future pack would inherit. Also generates
  `config/initializers/brand.rb` from the manifest, so `Ui::Logo` has identity to read and no
  component ever hardcodes a brand name.
- **Review fixes** (PR #149). Docs described the API two ways: `Ui::Logo`'s usage example and
  `components.md` still documented the **removed `brand:` parameter**, and `setup.md` still asserted
  `fm-*` as *the* primitive prefix — contradicting "primitives are private to a pack" three files
  away. The pack-lint invocation also resolved the script via `${CLAUDE_PLUGIN_ROOT}` while passing
  a project-relative pack path, so it could never find the shipped reference packs; it now resolves
  both locations and offers to scaffold from `_template` when neither exists.
- **Lint hardening from review**, three of which were real holes in a lint written the same day:
  - **A missing mark file passed.** `brand.json` could point at `prism.svg` while `assets/` held
    something else, and the pack still linted clean — with the logo being *half* of what a pack
    declares. Now an error; unreferenced assets warn.
  - **Indented CSS produced a false failure.** The block regex anchored `:root` and its closing
    brace to column 1, so a formatter that indented the block made the lint report **all 22 roles
    missing** — the most alarming possible message for a pack that was fine.
  - **The documented `brands/*` glob always exited non-zero**, because the shipped `_template`
    deliberately fails until its palette is validated. `_`-prefixed dirs are now skipped (with a
    `SKIP` line) unless `--include-templates`. A check that always fails gets ignored — the same
    lesson as the drift-guard work.

### 1.3.0 — 2026-07-25
- **design-auditor + audit gain a fifth checklist category — "Composition/branding"** (#74): the
  auditor structurally could not flag a full-page focused view using bare `center` instead of the
  `cover` vertical-centering recipe, nor a marketing/auth surface with **no brand mark** (both
  happened downstream and a full audit pass reported neither). Now checked in
  `design-auditor.md` and `/design-flow:audit`, including sub-20px marks, hand-rolled text
  eyebrows, and recolored/stretched facets.
- **`/design-flow:setup` scaffolds `Ui::Logo`** (#75) — added to the base-ViewComponent list, with
  guidance to use `docs/design-system/brand-assets/01-logos/` exact SVG paths when present (else the
  canonical 3-facet prism, flagged for swap), plus the auth/focused-page pairing.

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
  (token/logo/icon/brand-pack enforcement).

## rails-stack (skills plugin: rails-8 + hotwire + fidara-design + code-review)

### Unreleased — structure & elements: the pieces page anatomies already assumed (#95)
_Version assigned at promotion._
- **First increment of Phase 2**, honouring that issue's own instruction to ship one group at a time
  rather than all ~17 components at once.
- **The slice was chosen by a gap #94 created.** `page-anatomies.md` shipped in v1.24.0 telling agents
  to "fill the regions from the catalog", then named **heading block**, **Breadcrumb** and
  **description list** — none of which had catalog entries. An agent following it either invents the
  markup (the exact failure page anatomies exists to prevent) or stalls. So this increment is "the
  patterns `page-anatomies.md` already composes", cutting across the issue's Navigation / Lists /
  Elements grouping deliberately: closing a live dangling reference beats matching the kit's taxonomy,
  and these six are what the next groups build on.
- **Six catalog entries + five worked ViewComponents:** Heading blocks (page/section/card — one
  anatomy, scale the only axis, tag and step moving together so a card heading can never be an `<h2>`
  styled small), Breadcrumbs, Description list, Button group, Media object, and Divider **as a recipe,
  not a component** (an `<hr>` is already `role="separator"`; in lists the answer is `divide-y` on the
  container, not n elements).
- **No duplicate mechanisms**, per the issue's own criterion: Card's `detail` recipe now *renders* the
  Description list at `inline` instead of re-implementing `<dl>` rows, and the button group's
  single-select kind is a `radiogroup` driven by the existing **list-navigation** mixin rather than a
  new controller. Breadcrumb collapsing reuses `Ui::DropdownComponent`.
- **Mechanical verification caught two violations in the draft before commit**, which is why it is
  done by script rather than by reading: the breadcrumb separator called
  `lucide_icon(..., class: "size-4")` when the icon doctrine is explicit that icons carry **no** size
  or class (`with-icon` sizes them to 1em in `currentColor` — SVG presentation attributes have zero
  specificity, which is the whole reason that rule exists); and it used `d.with_item`, when
  `Ui::DropdownComponent` takes `items:` as an array of `{label:, href:}`. Both would have shipped
  code that raises or silently ignores doctrine.
- Verified: every primitive, role token, type step, space step and rendered component resolves against
  the other references; zero literal colours; zero inline `dark:`; no new `@utility` defined.
  `page-anatomies.md` now names the components instead of generic patterns, and the file's "full
  catalog has worked code" claim is updated to stay true.

### 1.14.0 — 2026-07-29
- **Maintainer decision, recorded:** *"simple_form is in charge of all forms to drive consistency
  across the codebase — no form or form element should exist that does not use simple_form,"* and
  *"ViewComponents should use the same simple_form."* Three references contradicted that, and two
  called APIs that do not exist at all.
- **`forms.md` called a helper that does not exist** — `field_classes(state)` against `UiHelper`'s
  `input_classes(state:, size:)` (different name *and* keyword arguments). Copied verbatim, the
  field-anatomy example raised `NoMethodError`.
- **`crud-modal-pattern.md` used `form_with` and a `Ui::FieldComponent` signature that does not
  exist** — `(form:, name:, label:)` against an initializer of `(label:, hint:, error:, for_id:)`.
  This is the canonical create/edit example every CRUD screen is built from, so it had the widest
  blast radius of the three.
- **The root cause was deeper than the signatures.** A field-wrapper component that renders its own
  `<label>`, hint and error markup **is a form element built without simple_form** — precisely what
  the mandate rules out. So `Ui::FieldComponent` is gone from doctrine rather than corrected: field
  anatomy is now a **styled simple_form wrapper**, defined once in
  `config/initializers/simple_form.rb`, which is what `forms.md` already meant by "simple_form for
  the markup contract, styled to the design system". Authors write `f.input`; the wrapper supplies
  the `stack`, label classes, control classes, hint/error paragraphs and `aria-describedby`.
  One definition means a change lands on every field at once, which is the entire point.
- **The rule reaches inside ViewComponents.** A component that renders fields takes the form builder
  in and calls `form.input`; it does not re-implement the anatomy. `component-implementations.md`
  shows that composition shape.
- **The mandate was previously enforced more strictly than it was documented** — `setup-flow.md`
  already said "simple_form mandatory — never raw `form_with`" and `design-auditor` greps for
  `form_with` as a violation, while `rails-8/ecosystem-gems.md` still said "keep `form_with` for
  one-off forms — mixing is fine". So the shipped auditor blocked users for following our own
  doctrine, the same shape as the ids-only job contradiction fixed in v1.23.0. rails-8 now states
  simple_form as mandatory (a deliberate divergence from the Rails default, with the reason given),
  `views-hotwire.md`'s forms section is reframed as the builder-agnostic **Turbo contract** with the
  mandate stated up front, `SKILL.md`'s golden path says `simple_form_for`, and the auditor's rule
  drops its stale "if the project mandates" conditional.
- **Every remaining exception was closed rather than flagged.** There is no non-simple_form case:
  a model-less form is `simple_form_for :q, url: …` (simple_form takes a symbol), a hidden label is
  `label: false` plus an accessible name, and `f.input_field` — which *is* simple_form's control-only
  renderer, so it satisfies the mandate — is reserved for a control inside a composed cluster where
  the wrapper's markup would fight the layout. What is forbidden is hand-rolling the anatomy, not
  using simple_form's own API.
- **The wrapper config is now stated as a contract with a way to prove it**, instead of a snippet
  readers must take on trust: order (label → control → hint → error in a `stack`), role tokens only,
  `min-h-touch` + `focus-visible`, error state driven by simple_form's `error_class`/`aria-invalid`
  so `aria-describedby` is not hand-maintained, and label always rendered unless explicitly hidden.
  A short system spec asserts all of it on first install — if it fails, the wrapper is wrong, not the
  doctrine. Repeated deviation is a second named wrapper, never a repeated per-field override.

### 1.13.0 — 2026-07-29
- **The gap.** fidara-design had a strong component catalog and almost no page-level anatomy — one
  base layout and the `cover` recipe. An agent asked for "the invoices screen" had nothing to
  follow above component scale, so it invented page structure, and invented structure is where
  breakpoint chains, nested cards and inconsistent heading ramps come from.
- **New `references/page-anatomies.md`** — **3 shell archetypes** (sidebar + mobile drawer via
  `Layout::SidebarComponent`; stacked top-bar; multi-column rail/main/aside) and **3 page
  anatomies** (home-dashboard, detail, settings), each stating mobile behaviour, brand-mark
  placement, safe-area handling and which catalog components fill each region. Framing: **a screen
  is composed, not designed** — pick a shell, pick an anatomy, fill from the catalog.
- **Scroll containment is called out explicitly** because it is the failure that makes a shell feel
  broken: an independent scroll region needs `min-h-0` alongside `overflow-y-auto`, or the flex/grid
  child cannot shrink and the whole page scrolls, taking the rail with it.
- **A primitive-instead-of-breakpoint substitution table** — `grid grid-cols-1 md:… lg:…` →
  `grid-auto` + `--min`; `flex-col md:flex-row` → `Layout::Switcher`; `hidden md:block` for a rail →
  `Layout::SidebarComponent`; `space-y-*` → `stack`; `max-w-7xl mx-auto px-*` → `shell`. Intrinsic
  reflow responds to the **container**, so it stays correct inside a drawer or a split view where a
  viewport breakpoint is simply wrong.
- **Composed only from primitives that already exist**, per the epic's rule that introducing new
  framework API into a skill is an external claim. Every `@utility`, component name, role token and
  type step in the file was verified against the other references mechanically rather than by
  reading — which caught three of my own errors before commit: `--grid-min` (the real custom
  property is `--min`), `with_rail` (the slots are `renders_one :sidebar` / `:main`), and a
  `FieldComponent` call matching neither shipped signature.
- The settings anatomy deliberately **defers to `forms.md`** instead of asserting a field API,
  because two references disagree about `FieldComponent` — filed as #168 rather than resolved here.
- `SKILL.md` links it as section 3 (between Layout and Components); `/design-flow:component` now
  routes any screen-level request through it before writing markup.

### 1.12.0 — 2026-07-29
- **New `skills/code-review`**, bundled into rails-stack and packaged as `dist/code-review.skill`.
  Review doctrine for the defect class authors are structurally blind to: code that is correct on
  its own terms but does not do what its own documentation, config, comments or project rules
  claim. Names seven classes (`claims-vs-enforcement`, `dead-declaration`,
  `carve-out-without-negative-test`, `coverage-gap`, `doctrine-contradiction`,
  `unverified-negative`, `gate-that-cannot-fail`) with detection guidance for each, and is explicit
  that it *complements* correctness review rather than replacing it.
- **Every class is traceable to a defect this repo actually shipped or nearly shipped** — no
  speculative rules. It also states the project's own rules (CLAUDE.md Project Overrides, README,
  `docs/`) are the *input* to the review, since most findings are a rule in the repo disagreeing
  with code in the repo.
- Consumed by rails-flow's `code-reviewer` and `pr-reviewer`, which delegate to it instead of
  restating it. Packaging is unchanged in shape; the other three `.skill` files rebuild
  byte-identical.

### 1.11.0 — 2026-07-29
- **The design system becomes multi-brand** (#104). `brand.md` refactored from "two brands, one
  system" into the **brand-pack** model, so the system can be used for client and freelance work
  without forking.
  - **A pack is a theme, not a fork.** The framing is explicit: you use this system the way you
    use Tailwind, Bootstrap or Flowbite — you do not re-author it. A pack declares **colours, the
    logo, and the chart-palette validation result**; that is the whole surface. Layout, component
    API, spacing/type scale, a11y and interactions stay central, so every brand inherits the
    fixes. "Not in the pack" is the product, not a limitation.
  - **Two levels: pack, then variant.** A *pack* is a genuinely distinct brand (own palette,
    fonts, mark). A *variant* lives inside a pack and differs only in lockup/endorsement.
    **`fmworkflows` is a variant of the `fidara` pack, not a pack of its own** — it is a product
    *using* fidara's design system. Modelling it as a peer brand would have meant two
    byte-identical `theme.css` files and a live drift hazard (update the parent palette, the
    product silently diverges). A variant carries no values, so it cannot drift. The test:
    *does it re-theme, or only re-label?*
  - **Primitives are private to a pack; the role layer is the public API.** `fm-*` is fidara's
    own naming, not system law — a client pack may name primitives anything, because nothing
    outside a pack may reference one. That is what makes a brand swap a single `@theme` layer and
    what makes completeness mechanically checkable.
  - **Overrides are a rare escape hatch**, not what a brand does: `fonts`, the three personality
    knobs, and `chart_hues` inherit fidara's calibrated defaults when omitted, so a typical
    client manifest is four lines. Every override is a place the brand stops matching the system.
  - `chart_palette_validated: true` is required **even when hues are inherited** — changing the
    palette changes the surface the hues sit on, and hues that clear contrast on fidara's navy can
    fail on a client's light beige.
  - **Fixed a latent doctrine bug the two-value enum was hiding**: the "by Fidara" endorsement was
    attached to the *parent* (`brand: :fidara` → `endorsement? = true`), rendering
    **"Fidara by Fidara"**. An endorsement ties a *product* to its parent, so it belongs on the
    product variant. `Ui::Logo` now takes `brand_variant:` and reads the display name and
    endorsement **string** from the pack manifest — no brand names in component code, so a
    client's "an Acme company" needs no code change.
  - Swept every other assertion of the old model: `SKILL.md`, `components.md`,
    `component-implementations.md`, and design-flow's `setup`, `brand-guardian`, README and
    plugin description.
  - Records what the lint **cannot** prove: it checks a pack against the role contract, not the
    contract against reality. A clean pack that still renders a stock colour is a doctrine defect
    to report upstream, not a project problem to patch locally.
  - **Rejected one review finding with reasoning**: `Ui::Logo`'s px units. The mark has a
    *documented absolute minimum* (prism 20px digital / 6mm print, clear space 1.5×) and its
    wordmark is sized proportionally to the mark, not to body text — scaling a trademark with the
    reader's font preference would violate the brand's own minimum-size rule. Materially different
    from the `body { font-size: 15px }` finding accepted earlier, which overrode text scaling.

### 1.10.0 — 2026-07-25
- **fidara-design Phase 0 — foundations calibrated against two reference corpora** (#93). The
  fluid scale existed; *which step goes where* was undefined, which is where drift starts. All
  values below were measured across 704 + 264 component files and 72 rendered pages, not chosen
  by taste.
  - **NEW tokens**: `--width-shell` (80rem/1280px — both corpora converge, `max-w-7xl` ≡
    `max-w-screen-xl`), `--width-prose` (42rem/672px section ledes), `--space-section`
    (clamp 96→128px, generous — the fidara default) and `--space-section-compact` (64→96px).
    Plus `@utility shell / prose-measure / section-y / section-y-compact`. Verified compiling
    under Tailwind v4.3.3.
  - **NEW "Applying the scale" table — the chrome-vs-content rule.** Interface chrome is
    *smaller* than prose: both corpora are `text-sm`-centric by ~**2.7 : 1** (TW 6494 vs 1575;
    FB 1100 vs 413). So app chrome = `text-step--1`, prose = `text-step-0`, meta = `text-step--2`,
    with card/section/page/hero mapped to steps 1/2/3/4-5. Using `step-0` for chrome is the most
    common calibration error and made product UI read oversized.
  - **Heading ramp** — follow Flowbite's fuller mid-range: reach for `step-1`/`step-2` for card
    and section headings instead of jumping body → hero (Tailwind UI's thin mid-range).
  - **NEW control-density table** bound to the shared `sm/md/lg` vocabulary, reconciling padding
    with height: `md` = `px-3 py-2` / `h-9` (both corpora's default — TW 749, FB 129).
  - **Validated by measurement, now settled**: the radius language matches ours exactly
    (controls `rounded-md` 2068, cards `rounded-lg` 966, pills `rounded-full` 1379) and the
    elevation idiom is a 1px edge + minimal shadow (`ring-1` 690 + `shadow-xs` 498; FB `border`
    302 + `shadow-xs` 116). Flowbite's softer all-`rounded-lg` was **considered and rejected**.
  - **NEW hard rule — never bind markup to a numbered step.** Causal, not stylistic: a numbered
    step encodes a fixed lightness, so every dark adjustment must be inline. Measured cost in the
    corpora (which do bind that way): **20,825 `dark:` classes across 72 pages** (~289/page).
    fidara's role layer needs **zero**.
  - `brand.md` gains a **personality-knobs table** (#104): section rhythm, radius language and
    heading ramp are **per-brand** choices with fidara defaults — a client brand changes a token,
    never a component.

### 1.9.1 — 2026-07-25
- **RSpec and Tailwind are stated as deliberate choices, not corrections** (#101). Both are
  **kept** — the decision is confirmed — but the doctrine previously implied the canonical
  alternatives were defects, which is wrong: **Minitest is Rails' default test framework** and
  **hand-written CSS is what 37signals ship** in their own production apps
  ([basecamp/fizzy](https://github.com/basecamp/fizzy) `Gemfile`: `minitest-reporters` + `capybara`,
  with `test/` not `spec/`; campfire/writebook/fizzy use vanilla CSS, no Tailwind gem).
  - `rails-8 › testing.md` now explains **why** we standardize on RSpec (the rails-flow Stop-gate,
    `test-runner` agent, `bin/ci` list and qa-flow gates all assume RSpec conventions + `spec/`
    layout — one framework is what makes those gates mechanical), and states that **a project
    already on Minitest is not a defect** — record a Project Override, don't migrate it on this
    skill's authority.
  - `fidara-design › SKILL.md` does the same for Tailwind: the reason is **mechanically enforceable
    consistency** (greppable `@theme` roles + `@utility` primitives let `/design-flow:audit` verify
    conformance — impossible for bespoke stylesheets), not that vanilla CSS is inferior.
  - README: "no Minitest" → "a deliberate standardization over Rails' Minitest default".
- Also hardened `.gitignore` for licensed design references (`flowbite*/`, `flowbite*.zip` alongside
  `tailwind-ui/`, `everylayout/`) so kit sources can never be committed to this public repo.

### 1.9.0 — 2026-07-25
- fidara-design **`Ui::Logo` + the auth/focused-page recipe** (#75, #74). `brand.md` fully specified
  the Prism mark (facet hues, wordmark, clear space 1.5×, min 20px / lockup 140px) and
  `brand-guardian` existed to enforce it — but **nothing rendered it**, so downstream screens
  hand-rolled a `<p>Fidara</p>` text eyebrow. Now:
  - **`Ui::Logo`** worked in component-implementations (variants `mark`/`lockup`, sizes
    `sm 20 / md 28 / lg 40` px with the 20px floor enforced in code, `brand:` toggling the
    "by Fidara" endorsement, dark-mode automatic). Facet hues stay **fixed brand hex** — the one
    documented exception to role-tokens-only, because facets must never be recolored.
  - **Catalog entry** in components.md (required on marketing/auth/full-page single-focus surfaces).
  - **Named auth recipe**: `layout-primitives.md`'s canonical-compositions table now calls out
    "Auth / marketing splash / onboarding (single-focus, full-page): `cover > center > stack`" and
    warns not to file these under "Page" — the ambiguity (#74) that left auth screens
    top-aligned via bare `center` (which is `margin-inline` only) and mark-less.

### 1.8.0 — 2026-07-25
- rails-8 **CI trigger-economy doctrine** (#76): `testing.md`'s "mirror `bin/ci` into
  `.github/workflows/ci.yml`" line no longer implies *run everything on everything*. It now
  prescribes scoping the hosted CI to the `dev → main` gate —
  `on: { pull_request: { branches: [main] }, push: { branches: [main] }, workflow_dispatch: {} }`
  — because local `bin/ci` hooks + qa-flow already cover `feature → dev`, and full-matrix-on-every-PR
  burns Actions minutes (on a private repo it can exhaust the quota and block merges, which it did
  downstream). Doctrine-verified: `pull_request.branches` filters the PR's **base** branch (fires on
  the PR into `main` + the merge push), `branches`/`branches-ignore` are mutually exclusive — GitHub
  Actions "Events that trigger workflows."

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

### 2026-07-29 (release v1.25.0)
- **simple_form owns every form, and the doctrine finally says so consistently** (#168,
  rails-stack → 1.14.0, rails-flow → 1.10.0). Maintainer decision: *no form and no form element
  exists that does not use simple_form — including inside a ViewComponent.* Three references
  contradicted it and two called APIs that do not exist: `forms.md` invoked `field_classes(state)`
  against `UiHelper`'s `input_classes(state:, size:)` (wrong name **and** wrong argument style), and
  `crud-modal-pattern.md` — the canonical create/edit example every CRUD screen is copied from —
  used `form_with` plus a `Ui::FieldComponent` signature the component does not have.
- **The root cause was deeper than the signatures, so the component is gone rather than corrected.**
  A field wrapper that renders its own `<label>`, hint and error markup **is a form element built
  without simple_form** — the very thing the mandate forbids — and correcting its arguments would
  have preserved the contradiction. Field anatomy is now a **styled simple_form wrapper defined once**
  in `config/initializers/simple_form.rb`, which is what `forms.md` always meant by "simple_form for
  the markup contract, styled to the design system". Authors write `f.input`; one definition means a
  change lands on every field at once, which is the entire reason for the mandate. A component that
  renders fields takes the form builder in and calls `form.input` instead of re-implementing anatomy.
- **No exceptions were left open.** A model-less form is `simple_form_for :q, url: …` (simple_form
  accepts a symbol); a hidden label is `label: false` plus an accessible name; `f.input_field` is
  simple_form's own control-only renderer and so satisfies the mandate, reserved for a control inside
  a composed cluster. The wrapper is documented as a **contract** — label → control → hint → error in
  a `stack`, role tokens only, `min-h-touch` + `focus-visible`, error state driven by simple_form's
  `error_class`/`aria-invalid` so `aria-describedby` is not hand-maintained — with a system spec that
  proves it on first install. If the spec fails the wrapper is wrong, not the doctrine.
- **The mandate had been enforced more strictly than it was documented.** `setup-flow` already said
  "simple_form mandatory — never raw `form_with`" and the design-auditor treated `form_with` as a
  violation, while `rails-8/ecosystem-gems.md` still said "keep `form_with` for one-off forms —
  mixing is fine". **Our shipped auditor blocked users for following our own doctrine** — the same
  shape as the ids-only job contradiction fixed in v1.23.0. rails-8 now states simple_form as
  mandatory (a deliberate divergence from the Rails default, with the reason given),
  `views-hotwire.md`'s forms section is reframed as the builder-agnostic Turbo contract, and
  `SKILL.md`'s golden path matches.
- **And the auditor's check flagged every correct form.** `grep -rn "form_with\|form_for"` also
  matches **`simple_form_for`**, because that string ends with `form_for` — so the mandate check
  fired on exactly the code it was meant to allow. A check that flags everything is as useless as one
  that cannot fire: it gets ignored, then disabled. Fixed with a word boundary and proven against a
  fixture holding one correct form and one violation. Two checks were added that catch what was
  actually unchecked — hand-rolled anatomy in `app/views` **and** `app/components`, and a stock
  simple_form initializer (unstyled fields push every view toward per-input class patching, which is
  the drift the mandate prevents).
- Pattern worth recording across this release and the last two: every recent fix has been a **check
  that looked like it was working** — two that could not fail, one that fired constantly. Each fix
  now ships with a fixture proving the check distinguishes pass from fail, because a gate never
  observed doing both is not known to work.

### 2026-07-29 (release v1.24.0)
- **Screens got doctrine** (#94, rails-stack → 1.13.0, design-flow → 1.5.0). fidara-design had a
  strong component catalog and almost **no page-level anatomy** — one base layout and the `cover`
  recipe — so an agent asked for "the invoices screen" had nothing to follow above component scale
  and invented page structure. Invented structure is where breakpoint chains, nested cards and
  inconsistent heading ramps come from. New `references/page-anatomies.md` ships **3 shell
  archetypes** (sidebar + mobile drawer, stacked top-bar, multi-column rail/main/aside) and **3 page
  anatomies** (home-dashboard, detail, settings), each stating mobile behaviour, brand-mark
  placement, safe-area handling, scroll containment, and which catalog components fill each region.
  The framing is the deliverable: **a screen is composed, not designed** — pick a shell, pick an
  anatomy, fill from the catalog. `/design-flow:component` now routes any screen-level request
  through it before writing markup.
  It also carries a **primitive-instead-of-breakpoint substitution table** (`grid-cols-1 md:… lg:…`
  → `grid-auto` + `--min`; `flex-col md:flex-row` → `Layout::Switcher`; `space-y-*` → `stack`;
  `max-w-7xl mx-auto px-*` → `shell`), because intrinsic reflow responds to the **container** and so
  stays correct inside a drawer or split view where a viewport breakpoint is simply wrong. And it
  calls out that an independent scroll region needs `min-h-0` beside `overflow-y-auto` — the bug that
  makes a shell feel broken and is invisible until you try it. Phase 1 of the kit-transformation epic
  (#89); Phases 2–5 remain open.
- **The packager stopped depending on your working copy** (#171, maintainer tooling — not
  distributed). `.gitattributes` is `* text=auto eol=lf` with `*.skill binary`, so git normalises
  sources to LF on commit but stores the artifact byte-for-byte. Packaging a freshly authored file on
  Windows produced an archive carrying CRs its own committed sources did not have — 424 bytes' worth —
  and **the check CLAUDE.md prescribed passed anyway**, because it runs *before* the normalisation
  that creates the mismatch. The drift then surfaced at release time, where `release.yml` correctly
  refused to publish. `package_core.py` was never at fault; its guarantee was scoped to "a clean
  checkout", and nothing made the checkout clean. It now normalises text members itself, detecting
  binaries git's own way (a NUL byte in the first 8000 bytes) rather than by an extension allowlist —
  an allowlist needs maintaining and **fails open**, so the first type nobody added would silently
  restore the bug. Proven behaviour-preserving rather than asserted: all four `.skill` files rebuild
  byte-identical to the previous release, and the original failure was then reproduced end to end
  (39 sources CRLF-ified) with every artifact still byte-identical. `--selftest` carries 11
  assertions, including a NUL-bearing fixture with `\r\n` inside that naive normalisation would
  corrupt.
- Third instance this week of the same class — **a guarantee that only holds if you remember
  something** (`--check || echo`, a README-mandated flag the code left optional, and now the
  packaging check). Each has been moved into a deterministic layer, which is the class the
  `code-review` skill shipped in v1.23.0 exists to name.

### 2026-07-29 (release v1.23.0)
- **The doctrine's *effect* is now measurable, not just its content** (#156, maintainer tooling —
  not distributed). This repo has always had a hard gate on doctrine *content*: nothing is edited
  until `doctrine-verifier` confirms it against an authoritative source. It had **no** gate on
  doctrine *effect* — "the rails-8 skill produces better Rails" lived entirely in prose, the one
  layer this repo otherwise refuses to trust. New `evals/` measures whether loading the skills
  changes what an agent writes: three arms (no skill / a deliberately weak control / real
  rails-stack) × five cases × six deterministic gates that each cite the doctrine `file:line` they
  enforce. The runner drives `claude -p` rather than the Anthropic API, because these skills ship
  as **Claude Code plugins** — a pasted system prompt would measure a proxy, and a benchmark that
  measures a proxy repeats the mistake it exists to correct. Side effect worth having: no API
  dependency, so the harness stays stdlib-only with nothing for CI to install.
  Authoring the gates caught **two rules in the issue's own spec that would have manufactured
  false regressions** — an "ids-only" job gate that fails our own reference example, and a no-hex
  rule that flags our own `Ui::Logo`. Generalised into a standing rule the selftest asserts: *a
  gate must pass against the doctrine's own reference examples; if it fails what `references/*.md`
  shows as correct, the rule is wrong, not the doctrine.* No paid benchmark has been run and the
  results table is deliberately empty — a harness with proven gates and no numbers is honest.
- **The reviewer moved in-repo, and stopped being rented** (#162, rails-stack → 1.12.0,
  rails-flow → 1.9.0). A trial reviewer had been catching a class our own review missed, and it
  had no proprietary advantage: **it checked the diff against rules already written in this
  codebase's markdown.** Every existing dimension asks *"is this code correct?"*; the misses all
  came from a different question — *"does this code do what its own documentation, config, comments
  and project rules claim?"* Correct-looking code passes the first and fails the second, and the
  author cannot see it because they read the claim and the code as one intention.
  New **`code-review` skill** (bundled in rails-stack, now four skills) names the classes:
  `claims-vs-enforcement`, `dead-declaration`, `carve-out-without-negative-test`, `coverage-gap`,
  `doctrine-contradiction`, `unverified-negative`, `gate-that-cannot-fail`. It lives in `skills/`
  rather than `docs/` deliberately — rules a reviewer must find belong where reviewers look, and as
  shipped doctrine it is the same rule set a user's `pr-reviewer` applies, so we are held to what
  we sell. `code-reviewer` and `pr-reviewer` delegate to it instead of restating it.
- **A doctrine contradiction was live in users' hands, in three files** (#162). `pr-reviewer` told
  the merge gate to demand ids-only job arguments, `rails-developer` said "pass IDs, never AR
  objects", and `setup-flow` wrote that rule into the user's own generated CLAUDE.md — while
  `jobs-and-realtime.md:28` says pass records. **The shipped merge gate would have blocked a PR for
  correctly following our own doctrine**, and setup-flow propagated the wrong rule into the user's
  rules file for the gate to then enforce against them: self-reinforcing, and worse than a plain
  bug because it blames the user. Found by applying the new skill's `doctrine-contradiction` class
  with one grep — that class travels in groups, because the wrong rule gets copied. `skills/rails-8`
  is unchanged; the plugin text now defers to it rather than paraphrasing the mechanism.
- **`claims-vs-enforcement` is now enforced, in both repos** (#162 maintainer, #164
  rails-flow → 1.9.0). It had bitten three times in three PRs — `--check || echo` making a release
  gate unable to block, a README mandating a flag the code left optional, a docstring promising
  behaviour the code lacked. Writing the rule down does not prevent it, which is the whole reason
  `lint_markdown_shell.py` exists. Two linters now: maintainer-side
  `scripts/lint_self_consistency.py` (`dead-settings-key`, `unenforced-mandatory-flag`), and — the
  half users were missing — `rails-flow/scripts/self_consistency.py` with a PostToolUse hook,
  covering `swallowed-exception`, `swallowed-verdict`, `assertion-free-spec` and `dead-env-var`.
  Both are stdlib-only, print coverage even when clean (because "no findings" over input never read
  reads as a pass), and ship a selftest proving every rule fires **and stays silent** — a rule that
  flags everything gets disabled and then catches nothing. The maintainer linter is known-answer
  calibrated: it independently reproduces two of five prior review findings on the pre-fix commit
  and goes silent on the fixed one with the same inputs examined. The hook exits non-zero
  deliberately: a check that can only advise is itself a `gate-that-cannot-fail`.
  Two candidate rules were **cut rather than softened** — proving no spec covers a carve-out's
  near-miss needs judgement, and a rule that guesses gets disabled.
- Promotions are now named in two steps (`chore/arm-vX.Y.Z` → `dev`, then `dev` → `main`), with
  only the second publishing, and it is recorded that **a merge unions rather than overrides** — so
  a direct commit to `main` is permanently invisible to every future `dev`-based change (#155).

### 2026-07-29 (release v1.22.0)
- **Brand packs — the design system becomes multi-brand** (#104, rails-stack → 1.11.0,
  design-flow → 1.4.0). A pack is a **theme, not a fork**: it declares colours, the logo, and the
  chart-palette validation result, and inherits layout, components, spacing, a11y and interactions
  unchanged — so client work reuses the system instead of forking it. Two levels, pack then
  variant: `fmworkflows` is a **variant** of the `fidara` pack, not a pack of its own, because a
  product uses its parent's design system and a variant carries no values it could drift with.
  Primitives are private to a pack; the role layer is the public API, which is what makes a brand
  swap one `@theme` layer. Overrides (`fonts`, the three personality knobs, `chart_hues`) are a
  rare escape hatch, so a typical client manifest is four lines.
  New `brand_pack_lint.py` enforces the 22-role contract mechanically — a missing role does not
  error at runtime, it silently renders a stock Tailwind colour. Ships `brands/fidara` and a
  `brands/_template` client skeleton. Fixed a latent bug the old two-value enum was hiding: the
  endorsement sat on the *parent*, rendering "Fidara by Fidara"; it now belongs to the product
  variant as a string, so no brand name appears in component code.
- **The release drift check actually blocks** (#151, pipeline → 1.1.4, rails-flow → 1.8.0).
  v1.21.0 shipped `--check || echo`, which consumed the non-zero exit — a stale architecture graph
  printed a warning and released anyway. Worse than no check, because the message implied the gate
  ran. The three-branch shell guard that replaced it has since been deleted too: `--if-present`
  moves that judgement into tested Python and the doc carries two plain invocations.
  **bash is for commands, Python is for decisions.**
- **The shell inside markdown is now verified** (maintainer tooling, not distributed). `bash -n`
  covered `.sh` files while 194 lines of bash shipped inside 51 fenced blocks — the lines an agent
  runs verbatim in a user's project, and where three of this week's findings lived.
  `scripts/lint_markdown_shell.py` syntax-checks them and flags swallowed verdicts; it reconciles
  coverage on every run and **refuses to report clean when its parser cannot see a block**, after
  the first version silently skipped 11 blocks in 7 files.
- The doctrine gate gained an explicit scope (externally verifiable claims need a CONFIRMED
  verdict; our own architecture needs the maintainer's decision recorded on the issue), and
  promotions now assert no `### Unreleased` heading survives — a stray one means its notes never
  reach the published release.

### 2026-07-27 (release v1.21.0)
- **Local release fallback** (`scripts/release_local.sh`). Shipping depended on a single
  hosted runner, and the doctrine's "do NOT run `gh release` by hand" left no sanctioned path
  when one is unavailable — so the fallback would have been improvised under pressure, which is
  how a release goes out with unverified notes or a missing asset. The script is a deliberate
  mirror of `release.yml`: resolve `metadata.version` -> tag, no-op if the release exists,
  rebuild `dist/` with the canonical builder, **fail on drift**, extract the matching
  `(release vX.Y.Z)` CHANGELOG block, publish every `dist/*.skill` **by glob**.
  It re-asserts what a clean CI checkout gives for free and a laptop does not: clean working
  tree, HEAD on `main`, HEAD == `origin/main` (a tag must never point at a local-only commit).
  `--dry-run` verifies everything and publishes nothing; a real run requires typing the tag.
  Publishing uses the Releases API, which is not metered by Actions minutes, so this works when
  a runner will not start — though Actions is free on public repos, so check that the runner is
  genuinely the problem first.
  Verified: guards fire on a dirty tree / wrong branch / unpushed HEAD; no-op path confirmed
  against the published v1.20.1; drift guard fires both on a changed skill source
  (`M dist/rails-8.skill`) and on an untracked new asset (`?? dist/brand-new.skill`); notes
  extraction pulls the real 11-line v1.20.1 block, stops at the next `###`, and falls back with
  a warning when no block matches. The `gh release create` call itself is exercised only by a
  real promotion — run `--dry-run` first, every time.
  Caught while testing: a hand-typed asset list in the old doctrine named two `.skill` files
  while **three** actually ship, so a hand-cut release would have dropped `fidara-design.skill`.
- **Release notes could leak a neighbouring section** (`release.yml` **and** the new script).
  The awk that extracts release notes started grabbing on ANY line containing
  `(release vX.Y.Z)`, not specifically the `### … (release vX.Y.Z)` heading. Since a CHANGELOG
  entry can legitimately mention another release in prose, an earlier section's bullets could be
  published as this release's notes. Demonstrated, not theorised: with a prose cross-reference
  above the real heading, the old expression emitted two bullets belonging to a *different,
  unreleased* version. Both copies now anchor on `/^### /`. Verified the real v1.20.1 extraction
  is byte-identical before and after (11 lines), so the fix is a tightening, not a behaviour
  change. Found by review on PR #146 — the CHANGELOG already contains 2 non-heading
  `(release v…)` mentions out of 39, so the hazard was live.
- Two portability fixes in the script, also from that review: reject a Python 2 `python` (the
  canonical builder needs 3, and a wrong interpreter yields assets nobody can reproduce), and
  give `mktemp` a template — a bare `mktemp` aborts on BSD/macOS, which is exactly the machine
  a local fallback exists to serve.
- **Living architecture graph** (#141, rails-flow + pipeline). One generated artefact
  set — `docs/architecture/graph.json` + self-contained `index.html` + mermaid `graph.md` — extracted
  by a stdlib-only Python 3 script from routes, `app/**` and `db/schema.rb`, and serving three
  consumers at once: humans, agents (structural context without reading the codebase), and qa-flow
  (reverse-walk `edges` for a computed blast radius, so #134 becomes a consumer rather than a second
  extractor). `flows` — named, ordered request paths — are the part generic code-graph tools do not
  provide.
  Staleness is handled in the deterministic layer, per the harness doctrine: `--check` rebuilds and
  compares a `content_digest` over `{nodes, edges, flows}` (the `dist/` guard's rebuild-and-diff
  shape), regeneration runs at session end and at release, and `--delta` puts the structural change
  into the release notes. The HTML makes **zero external requests** — the maintainer ruling on the
  issue's CDN-vs-self-contained question — verified mechanically and by executing its inlined JS
  against a DOM stub. Skills unchanged, so `dist/` is untouched — `rails-stack` stays 1.10.0.
  Components bumped at this promotion: **rails-flow 1.6.0 → 1.7.0** (new capability),
  **pipeline 1.1.2 → 1.1.3** (guidance), **metadata.version 1.20.1 → 1.21.0** (the tag).
  Ships with the PR #143 review findings already folded into 1.7.0/1.1.3 (flow-identity delta bug,
  the release-command guard, and two accessibility corrections against our own design doctrine) —
  no separate version, because nothing between #143 and this promotion ever reached a user.

### 2026-07-26 (release v1.20.1)
- **README: architecture section + the three-loops diagram.** Documents the harness model and the
  one rule it follows ("put your guarantees in the deterministic layer"), a **mermaid** diagram of
  the BUILD / MEMORY / MAINTAIN loops and how they feed each other, and the agent-topology table
  (sequential / parallel / loop / agent-to-agent) naming where each is already used.
  Also records, with reasoning, the two pieces of agentic infrastructure we **deliberately do not
  adopt** -- a graph database for memory, and an external orchestration runtime -- and the
  alternative that achieves the same "graph engineering" benefits with plain files in git: typed
  findings records with dedupe signatures and `caused_by`/`blocks` edges (#138), declared issue
  edges (#133), and a code graph for derived blast radius (#134). Diagram verified by rendering
  with mermaid-cli. Docs only; `metadata.version` -> 1.20.1.

### 2026-07-25 (release v1.20.0)
- **fidara-design Phase 0 — foundations calibrated** (#93, rails-stack → 1.10.0). New
  `--width-shell` / `--width-prose` / `--space-section(-compact)` tokens + `@utility` recipes; the
  chrome-vs-content type rule (app chrome is `step--1`, prose `step-0` — both corpora are
  `text-sm`-centric ~2.7:1); heading ramp uses the middle steps; control density bound to
  `sm/md/lg` (`md` = `px-3 py-2`/`h-9`); radius + elevation confirmed by measurement and settled;
  and a new hard rule — **never bind markup to a numbered palette step** (measured cost: 20,825
  inline `dark:` classes in the corpora vs zero for our role layer). Rhythm/radius/heading are
  recorded as **per-brand knobs** in brand.md (#104). `metadata.version` → 1.20.0.

### 2026-07-25 (release v1.19.1)
- **RSpec + Tailwind reframed as deliberate choices** (#101, rails-stack → 1.9.1): both kept, but the
  doctrine no longer implies Rails' Minitest default or hand-written CSS are defects — each now states
  *why* we standardize (mechanical gates for RSpec; enforceable consistency for Tailwind) and that an
  existing Minitest/vanilla-CSS project is a Project Override, not something to migrate. Verified
  against 37signals' own apps. `.gitignore` hardened for licensed design references.
  `metadata.version` → 1.19.1.

### 2026-07-25 (release v1.19.0)
- **File-then-fix discipline** (#73, rails-flow → 1.6.0): mid-session defects are FILED as issues
  first, then worked one-at-a-time (`fix.md` Setup + `issues.md` Phase 0 + the CLAUDE.md scaffold
  rule), with a fail-open SessionStart advisory when fix-shaped commits stack on a branch with no
  issue reference. Completes the "defer to the issue-loop, don't improvise" theme (#77, #78).
  `metadata.version` → 1.19.0. Skills unchanged.

### 2026-07-25 (release v1.18.0)
- **Brand mark shipped + enforced** (#75, #74): `Ui::Logo` (Prism mark/lockup, 20px floor, brand
  endorsement toggle) + the named **auth/focused-page** recipe `cover > center > stack`
  (rails-stack → 1.9.0); design-auditor and `/design-flow:audit` gain a **Composition/branding**
  checklist category, and `/design-flow:setup` scaffolds the component (design-flow → 1.3.0). Closes
  the loop where the brand spec and its enforcer both existed but nothing rendered the mark.
  `metadata.version` → 1.18.0.

### 2026-07-25 (release v1.17.0)
- **Economical GitHub CI** (#76): run the full hosted CI only at the `dev → main` gate, not on every
  `feature → dev` PR — local gates + qa-flow already cover that, and full-matrix-on-every-PR exhausts
  Actions minutes (it blocked merges downstream). rails-8 `testing.md` doctrine gains the
  trigger-economy caveat (rails-stack → 1.8.0, doctrine-verified); `/rails-flow:setup-flow` proposes/
  repairs `ci.yml` triggers as an approved diff (rails-flow → 1.5.0); `setup-pipeline` aligns
  (pipeline → 1.1.2). `metadata.version` → 1.17.0.

### 2026-07-25 (release v1.16.2)
- rails-flow **review agents report ALL findings, defer disposition** (#77, rails-flow → 1.4.1):
  the four review/audit agents + `/rails-flow:review` can no longer self-dismiss a finding
  (the pattern that silently dropped two real security findings downstream). Every finding is
  reported, issue-ready; act/defer/accept is the fix-flow's + human's call. `metadata.version` →
  1.16.2.

### 2026-07-25 (release v1.16.1)
- qa-flow **functional-tester git-hygiene fix** (#78, qa-flow → 1.5.1): the agent no longer
  auto-commits/pushes its evidence (it polluted `dev` with 50 files incl. ephemeral
  `.playwright-mcp/`); it now leaves evidence under `qa/manual-tests/` for the coordinator, never
  touches git, and `setup-qa` gitignores `/.playwright-mcp/`. `metadata.version` → 1.16.1.

### 2026-07-24 (release v1.16.0)
- rails-flow **local brain-review cadence nudge** (#65, rails-flow → 1.4.0): SessionStart reminds
  when the maintenance sweep is overdue (7-day default, env-overridable), stamped via
  `docs/brain/.last-review`. Local/offline, reminder-only — the local-first replacement for the
  rejected cloud scheduler. `metadata.version` → 1.16.0. Skills unchanged.

### 2026-07-24 (release v1.15.0)
- qa-flow **`/qa-flow:smoke`** (#64, qa-flow → 1.5.0): a stack-aware launch-&-liveness gate that
  boots the app and confirms key routes respond before deeper QA — closing verify's hand-waved
  "boot the app" Phase 0. Adds an `app:` config block; `verify`/`setup-qa` wired to it. Free,
  stack-agnostic. `metadata.version` → 1.15.0. Skills unchanged.

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

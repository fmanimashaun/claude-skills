<!-- Moved here verbatim from CLAUDE.md on 2026-09-03 (#870). CLAUDE.md is now rule-first and links
     into this file by heading; nothing was deleted, only relocated. Add new incidents HERE, and add
     the rule they produced to CLAUDE.md as one line with a link. This file is read by nobody at
     session start, which is the point: it costs a session nothing until a rule's reasoning is wanted. -->

> **How to read this.** Every section below was once the body of `CLAUDE.md`. It carries the incident
> behind each rule, with issue numbers, so a rule that looks arbitrary can be traced to the failure
> that produced it. The rules themselves live in `CLAUDE.md`, which is what Claude Code reads.


# Maintainer history — the long-form reasoning behind `CLAUDE.md`

This repo **is** a Claude plugin marketplace. It ships two kinds of things to other
people, and it carries its own maintenance tooling for you.

- **Distributed (what users install):** the app-builder plugins listed in
  `.claude-plugin/marketplace.json` — `rails-stack` (which bundles the rails-8, hotwire,
  design-system, code-review, quality-pass, derived-artifacts and parallel-session-lane skills),
  `rails-flow`, `qa-flow`, `pipeline`, `design-flow`
  — plus the `dist/*.skill` packages for claude.ai upload. Keep this list in step with the
  manifest: it omitted `design-flow` for as long as that plugin existed (#203).
  `lint_self_consistency.py`'s `undocumented-plugin` rule catches a plugin named **nowhere**
  in this file — which is what happened — but it cannot tell that a mention sits in *this
  list* rather than in prose elsewhere, so the list itself is still on you.
- **NOT distributed (maintainer tooling, this file's subject):** the flow under
  **`.claude/`** — commands, agents, and a status hook that live only in this repo. They
  are **not** part of the marketplace, so `/plugin marketplace add fmanimashaun/claude-skills`
  never installs them. Anyone who *clones this repo* gets them automatically; that is the
  point. (This replaced an earlier idea of a separate maintainer marketplace repo.)

If you are here to **build a Rails app**, you want those plugins, not this file.

The first line of this file is `@AGENTS.md`, which **imports** the harness-neutral rules kept
there — how to explain a mechanism, when to decide versus ask, and to measure before asserting.
That import is the whole reason those rules apply: **Claude Code reads `CLAUDE.md`, not
`AGENTS.md`**, so before it existed the file was read by nothing, for two releases. Folding the
rules in here was tried first and reverted within minutes: `AGENTS.md` is a file the maintainer
edits directly, so a fold makes every new rule wait for someone to notice and copy it — which is
exactly what happened, a new rule landing there two minutes after the fold. The
`unimported-agent-instructions` gate now fails if that import or its target goes missing.

## The maintenance flow (the `.claude/` commands)

Downstream projects using the toolchain file issues here (via rails-flow's
`/rails-flow:report`, the reporter). You turn those issues into shipped, verified fixes:

- **`/maintainer-setup-intake`** — scaffold `.github/ISSUE_TEMPLATE/*` + the label taxonomy
  (already done for this repo; re-runnable, idempotent).
- **`/maintainer-triage [issue|label]`** — classify open issues by component × type ×
  priority, label, dedupe, and post a ranked queue. (agent: `issue-triager`)
- **`/maintainer-work [issue]`** — take an issue end-to-end: confirm → **verify against
  source-of-truth** → fix → PR into `dev` (unversioned, `Refs #n`) → CHANGELOG under
  `Unreleased`. Shipping is a separate, deliberate act: the `dev → main` promotion PR.
  One issue per branch is the default; **related issues may share one branch** under the
  conditions below.

### Grouping related issues on one branch — the preferred path

**Group related issues and knock them off together.** It covers more ground per branch, and for
issues that are really one change wearing several numbers it is also the only *honest* shape:
#109 and #110 were both qa-flow, both under EPIC #108, and both edited the same boot/validation
path — split, they are two PRs editing the same lines where the second cannot be reviewed
without the first. Grouping is the default for related work, not a concession (decision: #206).

"Related" is doing real work in that sentence. Group when all of these hold:

1. **Same component** — one `comp:*` label, so a revert stays surgical.
2. **One coherent mechanism** — same files or code path. If the fixes never touch each other,
   grouping buys nothing and only widens the blast radius of a revert.
3. **Same change type under the gate** — either all need a CONFIRMED `doctrine-verifier`
   verdict or none do. This inherits *Split a mixed change* above rather than weakening it: an
   architecture change must never carry a framework claim through on its coat-tails. **This is
   the one condition that is not a judgement call.**
4. **Still reviewable and bisectable in one sitting.** No fixed cap — take as many as genuinely
   share the mechanism. But the release-cadence reasoning applies: when something breaks, the
   branch is the unit you bisect to.

**Traceability is never pooled** — this is what makes grouping safe rather than sloppy. The
branch name carries the primary issue; the PR body carries one `Refs #n` per issue; the CHANGELOG
gets **one bullet per issue**, never one for the group; and the promotion carries a separate
`Closes #n` for each, so each closes on its own merit. Pool those and you lose which fix answered
which report, and the promotion can no longer say what it shipped.
- **`/maintainer-audit [component]`** — proactively review a skill/plugin against
  source-of-truth + the open-issue signal; file findings as issues (don't fix in place).

Agents backing them (in `.claude/agents/`): `issue-triager`, `doctrine-verifier`,
`skill-doctor`, `plugin-doctor`, `release-manager`. The one maintainer-only **skill** is
`.claude/skills/plugin-boundaries`. It decides *where content belongs* — one stack-neutral core with
stack-specific plugins layered on top, exactly one home per concern, and nothing maintainer-only
shipped to clients; read it **while shaping** a proposal for a new plugin, a stack port, or a split,
because each of its rules comes from a proposal rejected for breaking it. It stays maintainer-only
by its own rule 3: every line of it is about *this marketplace* — `marketplace.json`, per-stack
plugins, the licensed corpora — so a user installing it would receive doctrine about a repo they do
not have.

**Two skills that started here now ship**, because nothing in them was about this repo:
`skills/derived-artifacts` (anything whose numbers come from somewhere else — read the generator's
**structured source** rather than regex-parsing its generated prose, and assert every derived total
against the source's own declared totals; `build_coverage_artifact.py` is the worked case) and
`skills/parallel-session-lane` (the protocol when several agent sessions run against one repo at
once — confirm your worktree, take one coherent slice, stay in your assigned subtree, review your
own diff first). They are read as files here, exactly like `code-review` and `quality-pass`, rather
than being invocable — that is the standing trade for shipping them, and `plugin-boundaries` rule 2
forbids keeping a second copy behind to dodge it.

A SessionStart hook
(`.claude/hooks/scripts/maintainer-status.sh`, wired in `.claude/settings.json`) surfaces
the open-issue count each session — read-only, fails open if `gh` is absent.

## The non-negotiable gate

Skills are **doctrine other people's agents follow verbatim** — a wrong "fix" ships
confident misinformation. So: **no skill claim is edited until the `doctrine-verifier`
agent confirms it against an authoritative source** (official docs for the version in
scope, the gem/framework changelog, the `docs/audits/` protocol). "It sounds right" is
never enough. A CONFIRMED verdict authorizes the edit; REFUTED closes the issue with the
citation; **INCONCLUSIVE leaves doctrine unchanged.** Record the citation + version
boundary in the CHANGELOG entry.

### What the gate covers — and what it cannot

The gate exists for **externally verifiable claims**: how Rails, Hotwire, Tailwind, or a gem
actually behaves at a stated version. Those have an upstream to cite, so citing it is
mandatory and no judgement substitutes for it.

Some skill content has **no upstream** — our own architecture and design decisions (the brand-pack
model, which axes are per-brand, the role-token contract, distribution policy). Sending those to
`doctrine-verifier` returns INCONCLUSIVE for want of a source, and "INCONCLUSIVE leaves doctrine
unchanged" would then block our own decisions forever. That is not the gate working; it is the
gate misapplied.

So for a **design/architecture** change to a skill, the authority is **the maintainer's explicit
decision, recorded on the issue** — the durable equivalent of a citation. The rules that keep this
from becoming a loophole:

- **State which kind of change you are making, in the PR, before editing.** Silence is not a
  claim of exemption.
- **Split a mixed change.** If one PR touches both an architecture decision and a framework
  claim, the framework claim still needs a CONFIRMED verdict. Do not let the architecture half
  carry the factual half through.
- **Reuse established framework syntax rather than inventing it.** Introducing new
  framework API into a skill *is* an external claim, whatever else the PR is about.
- **Measure anything measurable.** A factual assertion about our own doctrine (e.g. "22 roles")
  is verified against the repo's own files and made re-checkable by a script, not asserted.
- **The maintainer decision must be linked** from the CHANGELOG entry, exactly where a citation
  would go.

### An issue body is not an authority

The gate above is about **editing doctrine**. This is about what you edit *from*: an issue's stated
contract is a **hypothesis, not a specification**, however confident it reads. Verify every externally
verifiable claim in it before implementing — and expect the errors to be plausible rather than obvious.

#142 asserted four accordion keybindings *"per the ARIA APG"*. They are absent from the current
pattern: they lived in a **2017 APG 1.1 example** and were deleted since. Traceable to a real source,
wrong today, and implemented as written it would have told every downstream agent that four keys are
mandated by a spec that does not contain them. The same issue also **omitted** a requirement APG
states plainly (an accordion header button must be wrapped in a heading), so read for omissions too,
not just errors.

Where a claim has **no** upstream — APG has no Command palette pattern, no Stepper pattern — say so
and decide it as ours. An INCONCLUSIVE verdict means a maintainer decision recorded on the issue,
never a citation invented to fill the gap.

(Recorded after #142, where the verdict's most valuable output was negative. Also #229: the same run
found two errors in doctrine shipped an hour earlier, because an error in shipped doctrine outranks a
gap in unwritten doctrine.)

(Recorded after #104: brand packs were designed and twice corrected by the maintainer in-session,
with the reasoning on the issue. Review flagged the missing verdict, correctly — the gate as
written had no scope, so the exemption was being decided per PR instead of by doctrine.)

## Git flow (strict)

**`main` is the default branch and the install surface.** `/plugin marketplace add
fmanimashaun/claude-skills` resolves the default branch, so whatever sits there is what
users run. `dev` is the integration branch — a staging area, never a shipping one.

- Branch `fix/*` or `feature/*` **off `dev`**.
- PR **into `dev`**. **No version bump. No `Closes #n`.** Nothing on `dev` has reached a
  user, so nothing on `dev` is a release, and an issue is not "closed" while its fix is
  unshipped.
- Release = **one promotion PR `dev → main`** (a merge commit) that carries the version
  bumps, the CHANGELOG release block, and **every** `Closes #n` for what it ships.
  **Do not commit to `main` directly** — see *why* below; it is stronger than a style rule.

### Merge a promotion with `--merge`. A squash breaks the NEXT one.

`gh pr merge <n> --merge`, explicitly. **Never `--squash`, never `--rebase`** — and this is a
correctness rule, not a preference about history shape.

A squash keeps dev's **content** and drops its **ancestry**: `main` gets a one-parent commit that
looks like dev's tree but is not descended from it. So the merge base between the branches falls
back to whatever preceded the release, git starts seeing both sides as having independently changed
the same files, and **the next promotion cannot merge at all**. v1.83.0 was squashed; v1.84.0 hit six
conflicts on files nobody had edited twice, in a repo where `git diff dev main` was otherwise clean.

The repair, if it happens again: merge `origin/main` into `dev`, resolve **every** conflict to dev's
side, and then assert the merge changed nothing — `git diff --cached <dev's SHA before> --stat` must
be **empty**. That assertion is the whole safety of the operation, because it proves you performed an
ancestry repair rather than a content revert. Verify first that `main` holds nothing `dev` lacks
(compare CHANGELOG headings; `main`'s should be a strict subset). This is **not** the tidiness merge
warned against below — that one is `main → dev` to flatter an ahead/behind counter, and produced 37
no-op merges here. This one repairs a genuine divergence.

`maintainer_doctor.py`'s `the last promotion carried dev's ancestry` check now asserts it, because
the sentence above was prose for eleven releases and prose does not merge anything. It asks whether
`main`'s tip **is a merge** *and* has a parent on `dev` — both halves, since a squash's single parent
is `main`'s own previous tip, which for a repo's first promotion is itself on `dev`. It is a
**diagnostic**, so `--gates-only` (what CI runs) skips it: run the full `maintainer_doctor.py` before
a promotion, which is the moment it is about.

### A promotion is two steps, and only the second publishes

Because the promotion PR's head is `dev`, the bumps have to be on `dev` before it opens. So a
release is:

One command rebuilds every version-stamped artefact, and the arm should use it:

```bash
python3 scripts/rebuild_generated.py     # coverage page, inventory, wiki, dist/*.skill
```

It exists because the arm ran the builders in order from memory, and the **v1.88.0 arm forgot the
wiki** — the gate caught it, which is the gate working and the sequence being memory. It runs every
builder in `BUILDERS` even if one fails, because stopping early leaves the tree half-rebuilt: some gates then pass,
some do not, and the reason is invisible.

| # | Step | Branch / PR | Publishes? |
|---|---|---|---|
| 1 | **Arm** — assign versions, convert `Unreleased` headings, write the one release block, **regenerate BOTH committed pages** (`docs/evidence/coverage.html`, `docs/architecture/inventory.html`) | `chore/arm-vX.Y.Z` → **`dev`** | **No** |
| 2 | **Promote** — merge dev into main | `dev` → **`main`** | **Yes** — the push to `main` fires the workflow |

The coverage page is on the arm step because it stamps the **release version**, read from
`marketplace.json`. That is tracked content, so it legitimately belongs in the bytes — but it means
bumping the version invalidates the committed page and `coverage artifact drift` fails until you
rebuild. The gate caught this on the v1.44.0 arm, which is the gate working; do what it says rather
than removing the stamp, because the version is the only freshness signal a shared copy of that page
carries.

Name step 1 `chore/arm-vX.Y.Z`, **never `release/vX.Y.Z`**, and title it
"arm vX.Y.Z — version assignment (does not publish)". A branch called `release/*` merging into
`dev` reads as though `dev` publishes releases, which it never has: the workflow triggers only on
`push: branches: [main]` *and* re-checks `github.ref == 'refs/heads/main'` in the job. Nothing
merged into `dev` can publish anything.
- Never `git add -A` blindly — stage only files you authored; run `git status` first.

Why the split matters: closing keywords fire only on merge into the **default** branch, so
with `main` default the `Closes #n` lines *must* live on the promotion PR. That is the
desired behaviour — issues close when the fix ships, not when it lands on a staging branch.

**Never write a closing keyword next to a real issue number in a commit message or PR body —
not even inside backticks, not even when quoting a past mistake.** GitHub parses the pattern
wherever it appears and does not care that the sentence is *about* the mistake. The commit that
introduced the rule below said, in prose, that a promotion had wrongly used a closing keyword on
issue 95 — and reaching `main` via the promotion, that sentence **closed issue 95 for the second
time in one day**, minutes after it had been reopened. When you must write about this, use a
placeholder number or name the issue separately from the keyword.

**An issue that ships incrementally gets `Refs`, never `Closes`, until its last increment.** EPICs and
umbrellas — anything whose body says *"ship in sub-releases"* or carries a checklist of groups — are
not closed by the promotion that ships one group. This is not hypothetical: a promotion put
a closing keyword on the Phase-2 component umbrella (issue 95), retiring it while **seven** of its rows were still
undocumented, and **four further slices landed against a closed issue** before anyone noticed. Check
the issue body before writing `Closes`: a checklist with unticked boxes means `Refs`.

**Why "never commit to `main`" is a correctness rule, not tidiness:** a merge **unions**, it does
not override. Merging `dev → main` brings dev's changes in; it never removes content that exists
only on `main`. So a direct commit to `main` lives there permanently and is **invisible to every
future `dev`-based change** — you would only find it by diffing. (One exists in this repo's
history: `d4b35f6`, adding `enabledPlugins` to `.claude/settings.json`. It happened to converge
because the same block later reached `dev`, but convergence was luck, not a property of the
merge.) The promotion pre-flight now asserts there are none.

Corollary for reading branch state: judge `dev` against `main` with `git diff dev main`, which
should be **empty** right after a promotion. Do **not** read the ahead/behind counter — `main`
accumulates one merge commit per release that `dev` never receives, so `dev` shows tens of
commits "behind" while being content-identical. Merging `main` back into `dev` to make the
counter look tidy is what produced dozens of no-op merge commits on `dev` earlier; don't.

## The gates run in CI now, and until recently they did not

`.github/workflows/gates.yml` runs the sweep on **every pull request** and on every push to `dev`.

Before it existed, every automated check on a PR here belonged to a **third party** — AccessLint and
GitGuardian. Our own workflow was `release.yml`, which fires only on a push to `main`, *after* merge,
and whose single check is the `dist/` drift guard. So the gates this file spends pages on — 35 at
the time, `len(GATES)` in `scripts/maintainer_doctor.py` today — ran **nowhere automatically**: they ran when a maintainer remembered to type the command. That is the
claims-vs-enforcement defect this repo warns about most, sitting in its own infrastructure.

Two design points worth not undoing:

- **It runs `--gates-only`, not `--gates`.** The machine diagnostics ask about a *maintainer's clone*
  — current branch, stale local `main` ref, `gh` auth, the licensed corpora. None is meaningful on a
  runner, and failing on them would teach people to ignore a red build, which is worse than no CI.
  The gates are the opposite: every one is a claim about the repo's **content**, so it holds
  identically on a runner and on a laptop.
- **A pull request runs `--fast`; a push to `dev` and the promotion run everything.** `--fast` skips
  exactly `PR_SKIPPED_GATES` — `mutation coverage`, which was 438 of the sweep's 475 seconds on every
  PR — and reports the skip as `skip` with its reason, never silently. The merge commit and the
  release still get the full set, so nothing reaches `main` without it. The set is pinned by the
  doctor's selftest in both directions; widening it is how a fast mode becomes the only mode (#866).
  The guards themselves live one per file under `scripts/mutations/`, discovered by glob, so a
  refactor edits the small file beside it rather than a 5,600-line table.
- **It asserts `node` and `ruby` are present rather than tolerating their absence.** Without them
  `lint_markdown_code.py` returns exit 3 (INCOMPLETE) and the doctor maps 3 to SKIP — and in CI a
  skip is indistinguishable from a pass unless something asserts the interpreters exist.

`dist/` drift is checked here **as well as** in `release.yml`, because a diagnostic is not a gate and
`--gates-only` therefore skips it. Same shape in both files on purpose: **change one, change the
other**, exactly as with `release_local.sh`.

## Releases are automated — do NOT run `gh release` by hand

`.github/workflows/release.yml` fires on every push to `main`. Its `release` job `needs: gates` — the
full sweep from `gates.yml` runs first, via `workflow_call`, so a merge commit no PR tested is still
gated — and then:

1. reads `metadata.version` from `.claude-plugin/marketplace.json` → tag `vX.Y.Z`;
2. if no **release** exists for that tag yet (`gh release view`), builds `dist/*.skill` with `scripts/package_core.py`,
   verifies committed `dist/` matches (drift guard), extracts notes from the CHANGELOG
   `(release vX.Y.Z)` block, and publishes the release with **every** `dist/*.skill`
   asset (a glob, never a hand-typed list — that is how a release silently drops a newly
   added skill);
3. if a release already exists (version wasn't bumped), it is a **no-op**.

So to ship: land the work on `dev` unversioned, then open the promotion PR that bumps
`metadata.version` and merge it. The workflow does the rest. A corollary worth internalizing:
**a stray bump on `dev` is a loaded gun** — the next promotion publishes a real release the
moment it merges, whether or not anyone intended to ship.

### When the runner is unavailable — `scripts/release_local.sh`

"Do not run `gh release` by hand" means *do not improvise one*, not "there is no fallback".
If a hosted runner will not start, use the script — it is a deliberate mirror of
`release.yml`: same five steps, same order, same failure conditions.

```bash
bash scripts/release_local.sh --dry-run   # verify everything, publish nothing
bash scripts/release_local.sh             # publish (types-the-tag confirmation)
```

Always `--dry-run` first. It re-asserts the three things a clean CI checkout gives for
free and a laptop does not: a **clean working tree**, **HEAD on `main`**, and **HEAD ==
`origin/main`** (so a tag can never point at a commit only your machine has). It keeps the
drift guard and the CHANGELOG-block extraction, and it attaches **every** `dist/*.skill`
via glob — never a hand-typed list, which is how a hand-cut release silently drops a newly
added skill.

Publishing a release uses the Releases API, which is **not** metered by Actions minutes, so
this path works even when a workflow will not run. Note that Actions is free and unmetered
for public repos, so before reaching for this, check that the runner is genuinely the
problem. **If you change `release.yml`, change the script — and vice versa.**

## Versioning discipline

**Versions are assigned at the promotion, never on a merge into `dev`.** A version number
is a claim about what a user can install; on `dev` that claim is false. (This bit us on
#143: the fix PR bumped three components on `dev`, so `dev` advertised 1.21.0 while `main`
— and every user — was still on 1.20.1, and a promotion would have auto-published a
release nobody had decided to cut. #144 reverted it.)

- While work sits on `dev`, its notes go under a **`### Unreleased`** heading in the
  component's CHANGELOG section. No number is invented up front.
- In the **promotion PR**, assign the numbers and rename those headings. Components version
  **independently** — bump only what changed:
  - skill content → the **rails-stack** `version` in `marketplace.json`;
  - a plugin's code → that plugin's `plugins/<name>/.claude-plugin/plugin.json`;
  - always bump the top-level `metadata.version` — it is the release tag label. Patch for
    fixes, minor for new capabilities.
- **Every bump gets a CHANGELOG entry** under the component's section (newest first).
- **One `### … (release vX.Y.Z)` block per COMPONENT that this promotion bumps** — and the
  tag in every one of those headings must be the tag that actually ships. Never leave a
  `(release vX.Y.Z)` heading for a version that never gets tagged: nothing publishes it and
  its notes are simply gone. (v1.6.6 shipped three fixes and published one block's worth.)

  This bullet used to say **one block per promotion, full stop**, which was true when a
  promotion moved one component and became self-contradictory the moment the rule above it
  said components version *independently*. Two bumped components necessarily means two
  blocks. It was not a harmless wording problem: `release.yml` was written to that sentence
  and `exit`ed at the next heading, so a two-component promotion published the first block
  and silently dropped the rest. Four releases shipped that way before anyone diffed a
  release body against the CHANGELOG — #682, #642, #640 and #643 never appeared in theirs.

  `scripts/extract_release_notes.py` now emits **every** block for the tag, from one
  implementation called by both `release.yml` and `release_local.sh`, and the
  `release notes complete` gate refuses a promotion whose CHANGELOG holds a block that
  would not publish. Do not put the extractor back into the shells: the
  `duplicated-release-extractor` rule fails if either grows its own, because two copies kept
  in step by a comment is what made this invisible for four releases (#699).

### Release cadence

Promote **per coherent slice** — a feature, or a batch of related fixes. Do not hold
promotions until the whole queue is clear: a 40-issue release is hard to bisect when
something breaks, and the `dist/*.skill` assets on the latest GitHub release (the claude.ai
upload path) stay stale the entire time. Small, frequent, readable promotions.

## Verify the shell we ship inside markdown

`bash -n` on `.sh` files was never the whole surface: commands and skills carry ~200 lines of
bash in fenced blocks — the lines an agent copies and runs **verbatim in a user's project** —
and nothing checked them. Three review findings in one week lived there, including a
`--check || echo` that made a release gate unable to block.

```bash
python3 scripts/lint_markdown_shell.py                  # syntax + dangerous patterns
python3 scripts/lint_markdown_shell.py --audit-coverage  # prove no block is silently skipped
```

Run it after editing any command/skill markdown that contains a shell block. It catches
syntax errors (templates are placeholder-substituted first), **swallowed verdicts**
(`|| echo`/`|| true` on a verification command), and unquoted test operands.

`--audit-coverage` exists because the first version of the fence regex silently skipped 11
blocks in 7 files: a lint that reports clean on input it never read is worse than no lint.
Treat a coverage gap as a defect in the linter, not a nuisance.

### The same argument applies to JS, Ruby and ERB — and they are the bigger surface

`bash -n` on fenced blocks was the start, not the whole job. The other languages carry **more** code
than the shell does — several hundred ruby, erb and js blocks against a couple of hundred bash; both
linters print the live counts — and it is the same code an agent pastes into a user's project.

```bash
python3 scripts/lint_markdown_code.py                   # node --check / ruby -c per block
python3 scripts/lint_markdown_code.py --audit-coverage  # prove no block is silently skipped
python3 scripts/lint_markdown_code.py --selftest        # mostly SILENCE fixtures; it prints the count
```

**Its whole risk is false positives, so read that half first.** Reference docs are full of deliberate
elision (`def perform(account) ... end`) and of fragments that are correct but not standalone (a method
with no class). So a block is **normalised** — elisions substituted, exactly as the shell linter
substitutes `<pack>` — then tried in a short, **named ladder of contexts** (bare, class body, method
body, object literal), passing if any accepts it. Widening that ladder to silence a failure is how the
tool stops finding anything; the run prints which context accepted each block so the ladder can be
watched.

Three things it taught that are worth not relearning:

- **Two Rails idioms are invalid in stdlib ERB.** `<%= form_with … do |f| %>` compiles to
  `(expr do).to_s` and `<%==` to `((= expr))` — both syntax errors — because Rails compiles views with
  **erubi**, not `ERB`. Erubi is a gem, so depending on it would make the gate pass or fail by machine.
  Both are normalised away instead. This was **21 of the first run's 26 findings**: a linter's own false
  positives on the most common idiom in the corpus.
- **`js` matches the `js` in ` ```json `.** Without a `\b` after the language, every JSON block in the
  repo was handed to `node --check`. The `--audit-coverage` control caught it because that regex already
  had the boundary and the strict one did not — an **over**-matching extractor is as dishonest as an
  under-matching one.
- **ERB does not error on an unterminated `<%`.** It emits the rest of the template as a **literal
  string**, so the expression silently never runs and the view renders text where a value belongs. That
  needs an explicit balance check; the compiler will not give you one.

It found four real copy-paste hazards in shipped skills, all of which raise on paste: a bare
`rescue … end` with no `begin`, two prose-as-code lines (`Product.select(…) / .pluck(…)` — `/` is
division), and two blocks mixing a class field with statements.

### Which claims are enforced, and which are not — `docs/architecture/doctrine-map.html`

One question got asked by grep more than once a session: **which claim in our markdown is made true
by which gate, and which claims are made true by nothing.** That last set is the defect class above,
and we were finding them one accident at a time — nothing read the manifest's `use_cases` (#639),
nothing gated `marketplace.json` completeness (#651), a `--check || echo` made a release gate unable
to block (#151).

```bash
python3 scripts/doctrine_map.py                   # rebuild the page
python3 scripts/doctrine_map.py --check            # drift gate
python3 scripts/doctrine_map.py --audit-coverage    # a declared source with no rows is a finding
```

**There is no extractor, and that is the design.** Pulling "a claim" out of prose is the hard part,
and a bad extractor is worse than none — *a map that misses claims reads as coverage*. So `CLAIMS`
is an explicit registry living in the same file as the validators that check it, the shape
`maintainer_doctor.GATES` and `mutation_check.GUARDS` already use, because a registry and its checker
in two files drift apart.

Each row is `guarantee`, `advice`, or `gap`, using **[`docs/doctrine/harness-doctrine.md`](docs/doctrine/harness-doctrine.md)**'s
existing test (*"if a model ignores this, what happens?"*) rather than new vocabulary. The validators
are all mechanical — so none is taste wearing a count (#476); the six below are the ones that name a
defect class, and `validate()` also refuses an unknown kind and a duplicate claim:

| validator | the defect it catches |
|---|---|
| `anchor missing` | the claim was reworded or deleted and the map still advertises it |
| `unresolved enforcement` | the row cites a gate/guard/rule/script that no longer exists — **this map committing the very defect it is for** |
| `unenforced guarantee` | a `guarantee` citing nothing; make it `advice`, or a `gap` with an issue |
| `untracked gap` | a `gap` with no issue number, which is a shrug |
| `resolved gap` | a `gap` whose enforcement now resolves — the row got fixed and nobody reclassified it |
| `undeclared source` | a row points outside `DOCTRINE_SOURCES`, so the declared surface is wrong |

Two things it deliberately does **not** do. An `advice` row with nothing behind it is **correct** —
`quality-pass` never blocks a merge on purpose, and `art-direction.md` argues at length that gating
judgement is worse than not gating it; the selftest has an explicit negative test for this, without
which `unenforced guarantee` would be a blanket ban on advisory doctrine. And `hook:` resolves against
the JSON that **wires** a script, never against the filesystem, because a hook sitting on disk that
nothing invokes is exactly the shape this map exists to surface.

**The map is a floor, not a ceiling, and the page says so.** `--audit-coverage` can tell you a
declared source has *zero* rows; nothing can tell you a source with four rows was not owed nine. A
row count is evidence that someone looked — never proof the file is covered. A green artifact standing
in for work nobody did is the failure this replaces, so it does not get to be one.

Not OpenKB, which prompted the issue: it compiles documents into a wiki **with an LLM**, so the bytes
are not a function of the inputs and no drift gate could hold them — an LLM-compiled knowledge base
would be the one generated artefact here that nothing could check, in the repo that files bugs about
exactly that. Take the idea, not the tool.

## Verify our own claims, not just our shell

A trial reviewer spent a fortnight catching a class of bug our review missed, and it had no
proprietary advantage: **it checked the diff against rules already written in this repo's
markdown.** One finding was literally "missing change-type classification" — verbatim from
this file. Others were our own README and a config file contradicting our own code.

The class is **claims-vs-enforcement**: a guarantee stated in prose that nothing makes true.
It has bitten three times in three PRs — `--check || echo` making a release gate unable to
block (#151), a README mandating `--max-total-usd` while the flag stayed optional (#161), a
docstring promising Ruby-comment handling the code lacked (#161). Writing the rule down does
not prevent it; that is the whole reason `lint_markdown_shell.py` exists.

```bash
python3 scripts/lint_self_consistency.py            # dead settings keys, unenforced flags
python3 scripts/lint_self_consistency.py --selftest  # prove both rules fire AND stay silent
```

The judgement-free half is that linter. **The rest is the `code-review` skill**
(`skills/code-review/SKILL.md`) — `carve-out-without-negative-test`, `coverage-gap`,
`doctrine-contradiction`, `unverified-negative`, `gate-that-cannot-fail`. It lives in
`skills/` rather than in `docs/` deliberately, for two reasons: rules a reviewer must find
belong where reviewers already look, and it is **shipped doctrine** — the same rules a
user's `pr-reviewer` applies, so we are held to what we sell. Read it against your own diff
before asking anyone else to.

### The quality half is a SECOND pass, and it is advisory on purpose

`skills/quality-pass/SKILL.md` (#360) covers what `code-review` deliberately does not: **reuse,
simplification, efficiency, altitude**. It is shipped doctrine like the rest, and two properties
are load-bearing rather than stylistic.

- **It is scoped away from bugs, in both directions.** A reviewer hunting correctness and quality
  in one read does neither well, which is why this is a second file and not five more classes in
  `code-review`. Each skill says where the other one starts.
- **It never blocks a merge.** Quality is judgement; a gate on taste gets switched off, and then
  nothing checks quality at all. That is why the gate this change added is **not** a duplication
  gate: `scripts/check_shared_shapes.py` refuses only a **number in the worked example
  disagreeing with the repo** — `claims-vs-enforcement` on our own prose, the same shape as
  `plugins/rails-flow/scripts/check_handoff.py` reconciling a tier table against the agents it describes. Do not "strengthen"
  it into refusing copies; that would contradict the doctrine it guards.

The worked example (`skills/quality-pass/references/worked-example.md`) records the pass's first
real run and the decision it produced — **not to extract**, with the measurement behind it. Read it
before proposing a de-duplication here: the textual overlap across those four files was 29% and the
extractable mechanism about 6%, and the gap between those two numbers is the whole lesson.

Two of its classes exist because we shipped them: a `doctrine-contradiction` told users'
merge gate to demand ids-only job arguments while `jobs-and-realtime.md:28` says pass
records, and `setup-flow` wrote that wrong rule into the user's own CLAUDE.md so the gate
then enforced it against them. When you find one instance of a contradiction, **grep for
the pattern** — that class travels in groups.

## Packaging (skills)

`scripts/package_core.py` is the ONE canonical `.skill` builder — **ZIP_STORED**
(uncompressed) + pinned `create_system` + **normalised line endings**, so output is
byte-identical on any OS/Python/zlib **and regardless of what your working copy holds**.
Never zip skills any other way. After any `skills/**` edit: `python3 scripts/package_core.py`
then confirm `git status` shows only the intended `dist/` change. The CI drift guard fails
a release if committed `dist/` isn't a clean build.

That last check used to be insufficient, and the way it failed is worth remembering. `.gitattributes`
is `* text=auto eol=lf` with `*.skill binary`, so git normalises sources to LF on commit but stores
the artifact byte-for-byte. Packaging a **freshly authored file on Windows** (CRLF in the working
copy) produced an archive carrying CRs its own committed sources did not have — 424 bytes' worth in
#94 — and `git status` showed only the intended `dist/` change, so **the prescribed check passed
while producing the exact drift it exists to prevent**. It ran *before* the normalisation that
created the mismatch, and the drift only surfaced at release time on someone else's clock.

The builder now normalises text members itself (binary detected git's way — a NUL byte in the first
8000 bytes — never an extension allowlist, which fails open on the first type nobody added). So the
guarantee no longer depends on remembering anything:

```bash
python3 scripts/package_core.py --selftest   # 11 assertions: CRLF==LF output, binaries untouched,
                                             # STORED + pinned create_system + fixed timestamps
```

## The feedback loop

`/rails-flow:report` (in the rails-flow plugin, shipped to users) → files structured,
deduped, version-pinned issues **here** → you `/maintainer-triage` and `/maintainer-work`
them → `dev → main` auto-releases. Every issue in this tracker arrived this way.

## New machine? Run the doctor first

```bash
python3 scripts/maintainer_doctor.py          # diagnose, change nothing
python3 scripts/maintainer_doctor.py --fix    # also apply the SAFE repairs
python3 scripts/maintainer_doctor.py --gates  # + the full gate sweep
```

`/maintainer-onboard` wraps it with the judgement half (read the doctrine, report released
version, unshipped work, candidate next work).

This exists because moving maintenance to a second machine once needed a hand-written 120-line
briefing, and it was only complete because the author had just hit every trap personally: a
fresh clone lands on **`main`**; an idle clone's **stale local `main` ref** makes the
`git diff dev main` check above report phantom deletions (5,231 of them, once); the licensed
corpora need attaching; and `git status --porcelain` **collapses a new untracked directory**, so
a new file can look like nothing at all. A checklist in prose would be the same
claims-vs-enforcement defect this file keeps warning about, so it is a script that can fail.

**Read its output as three verdicts, not two** — plus an informational `note` that is not a verdict.
`ok` is verified, `FAIL` blocks work, and **`skip` means the check did not run — it is not a pass.** That distinction is the whole point: the bug
that prompted this was `build_coverage.py --selftest` printing "35 checks passed" on a machine
with no corpora while two checks against the real repo silently did nothing.

`--fix` touches exactly two things — fast-forwarding the local `main` ref and checking
out/pulling `dev`. It never rewrites history, never `reset --hard`, never `clean`, and it
restores `dist/` byte-for-byte after the drift rebuild, so a diagnostic never mutates the repo.

### The coverage matrix has a browsable page, and it is committed

`docs/evidence/coverage.html` — generated by `scripts/build_coverage_artifact.py`, which **imports**
`build_coverage.py` rather than parsing it, and cross-checks its own row counts against the Totals
table committed in `references/coverage.md`. Filterable by guidance state, kind and corpus.

```bash
python3 scripts/build_coverage_artifact.py           # rebuild, then `git add docs/`
python3 scripts/build_coverage_artifact.py --check    # drift gate (in maintainer_doctor --gates)
```

**It is committed on purpose.** The first version wrote to a gitignored path, so the deliverable
existed only on the machine that built it — no other maintainer could see the thing it was for.
Two properties of the gate are worth knowing before you touch it, because both were defects first:

- **`--check` compares the blob at `HEAD`, never the file on disk.** It used to test `is_file()` and
  read the working copy, so a page built and never `git add`ed passed the gate whose own message says
  *"is not committed"* — the invisible-deliverable failure waved through by the gate built to stop it.
- **The rendered bytes must be a function of the DATA and nothing else.** Two kinds of non-content
  input leaked in, and each broke the gate in production:
  - **Git state.** It embedded its own short SHA, branch and released/unreleased state, making the
    gate **unpassable by construction** — committing the page advances `HEAD` and a promotion flips
    `unreleased` → `released`, so the bytes could only match at the one commit that does not yet
    contain the file. A file inside a commit cannot name its own commit. Then the **dirty caveat**
    did the same thing more sharply: regenerating `coverage.md` necessarily dirties the tree, so the
    very next command wrote a `state: "dirty"` page to the committed path and the gate failed
    permanently. `--check` guarded the *comparison* and left the *write* wide open.
  - **Corpora availability.** It walked the licensed kits for the upstream totals, so a machine
    without them committed `tw: null, fb: null` and broke the gate for everyone who had them. Adding
    it to `CORPORA_GATES` only stopped the check failing on the machine that was *missing* them; the
    damage still landed elsewhere. **Fix the input, don't widen the carve-out** — both counts now come
    from the committed `coverage.md` Totals table, and the exemption is removed.

  The page therefore stamps the **release version and nothing else**, and `--check` needs no
  dirty-tree exemption: mid-edit the honest verdict is a real one ("the committed page doesn't match
  your data — regenerate it"), which is exactly what `build_coverage.py --check` reports for
  `coverage.md` with no exemption at all. Same shape, same expectations.

**Regenerating `coverage.md` means regenerating the page too.** They are built from the same data and
both are committed, so four PRs in one afternoon left the page stale and failed the gate for whoever
ran next. `build_coverage.py` now prints the follow-up command when it writes; do what it says.

**The licensed corpora** (Tailwind UI, Flowbite, Every Layout) live in a separate **private**
repo, `fmanimashaun/design-corpora`, and are **OPTIONAL**. Exactly one file needs them:
`scripts/build_coverage.py`, which enumerates the kits to rebuild `coverage.md`. So a machine without
them can do everything except regenerate or drift-check **`coverage.md`**, and **no gate fails for
their absence** — `coverage matrix drift` SKIPs (it is the entire content of `CORPORA_GATES`) and
every selftest still runs, reporting its corpora-dependent fixtures as skipped.

`build_coverage_artifact.py` *imports* `build_coverage` but is **not** corpora-dependent: it reads the
upstream counts from the committed `coverage.md` Totals table, so the HTML page renders identically
with or without the kits attached. It was corpora-dependent, and briefly exempted for it — see the
section above for why exempting it was the wrong fix. The doctor's selftest pins `CORPORA_GATES`
**exactly**, in both directions, so re-adding it takes a deliberate edit with a reason.
Attach them as **one nested clone in a gitignored `design-corpora/` subfolder**:

```bash
git clone https://github.com/fmanimashaun/design-corpora.git design-corpora
python3 scripts/build_coverage.py --audit   # expect: 93 Tailwind UI + 63 Flowbite classified
```

That is the whole setup — no symlinks, and nothing extra on Windows.

**Why one subfolder and no links (#197).** The earlier layout symlinked `tailwind-ui/`,
`flowbite/` and `everylayout/` in from a sibling clone, and `.gitignore` matched them with a
**trailing slash — which matches a real directory only**, while git stores a symlink as mode
`120000`. So all three corpora sat **untracked in the very guard written to hide them**, printed
right under the warning below about 656 MB of licensed blobs. The ignore patterns are therefore
root-anchored and **slash-free**, and `maintainer_doctor.py` proves they still cover this layout
— against paths that do not exist, because a trailing-slash pattern *does* match a real
directory, so testing the real path on a machine that has the corpora would hide the regression.
That check is the reason this is doctrine rather than a habit: the rule was written, believed,
and matched nothing.

Never un-ignore them to commit them here: ~656 MB of licensed blobs in this history could only
be removed with `git filter-repo` and a force-push that rewrites every commit SHA and detaches
every release tag. Deleting the files in a later commit does not remove the blobs.

`flowbite-figma/` is **not** in that repo: its `.fig` is 283 MB, over GitHub's 100 MB per-file
hard limit. Direct file transfer if you need it; it drops into `design-corpora/` like the rest.

## First session in a clone: copy the permission example

`.claude/settings.example.json` is committed and carries a `permissions.allow` block. **Copy it to
`.claude/settings.local.json`** (gitignored) before doing real work, merging rather than overwriting
if you already have one.

Without it a maintenance run stops for confirmation every few commands, which is how an unattended
run stops being unattended. The cause is not obvious and cost a session before it was written down:
the commands here are **compound pipelines** — `python3 scripts/lint_self_consistency.py | grep -c
findings` — and the *whole string* is evaluated, so **one** unlisted binary anywhere in the chain
re-prompts all of it. A list holding `git`, `gh` and `python3` but not `grep` still prompts on most
real commands.

It deliberately omits `rm`, `curl`, `wget`, `kill`, `chmod` and package installers. Those destroy
work, reach the network, or mutate a toolchain a later step then trusts — a prompt is correct
friction there **even mid-run**, because their blast radius outlives the run. For no friction at all,
choose a permission *mode* deliberately rather than arriving at one by extending a list of binaries.

Three files, three audiences, and mixing them up is the whole trap:

| file | tracked | who gets it | read by Claude |
|---|---|---|---|
| `.claude/settings.json` | **yes** | everyone who clones | **yes** |
| `.claude/settings.local.json` | no, gitignored | **you, this machine** | **yes** |
| `.claude/settings.example.json` | yes | everyone who clones | **no — inert** |

`settings.json` holds what makes the repo *work* — the SessionStart hook, `enabledPlugins` — and is
correct to commit. `settings.local.json` holds what **you** trust to run on **your** machine, which
is not a decision to make on anyone else's behalf, so the allowlist goes there. The example file is
only a bridge: committed so a fresh clone has something to copy, read by nothing. This is the same three-file
pattern `/rails-flow:setup-flow` §2c scaffolds for users — which this repo was telling people to
follow while not following it.

## Platform

The `.claude/` hook and the plugins' hooks are **bash + `python3`**, and the flow drives
**`gh`** (authenticated: `gh auth status`). On Windows, run Claude Code in **WSL or Git
Bash** with `python3` and `gh` on PATH.

**Hooks do NOT all fail open, and the exceptions are deliberate.** This line used to say they did,
flatly. Of the twelve hook scripts, nine are advisory — a status line, a linter, a cross-check — and
a missing `python3` degrades them to silence, which is right: an advisory that blocks work when a
dependency is absent is an advisory people disable. The three **gates** fail **closed**, verified by
running each with `python3` shadowed by a stub that exits 127:

- `plugins/rails-flow/hooks/scripts/guard-bash.sh` — still exits **2**. Line 7 falls back to the raw
  JSON payload when the parse fails, and the payload still contains the command text, so every
  pattern still matches. `git add -A` is blocked either way.
- `plugins/qa-flow/hooks/scripts/release-gate.sh` — exits **2** when `python3` is missing *and* the
  command targets `main`, and **0** otherwise. Fail-closed **scoped to the command it guards**, which
  is the distinction that matters: a gate that failed closed on unrelated work would get switched off.
- `plugins/rails-flow/hooks/scripts/guard-lane.sh` (#660) — exits **2** for a write outside
  `RAILS_FLOW_LANE`, and **0** when no lane is assigned at all. Same scoping as the release gate, one
  axis over: it is dormant unless a lane exists, so a single-session run never pays for a
  multi-session feature. Its path normalisation is pure shell for this reason — one that needed
  `python3` would take the fail-closed guarantee down with it.

Which behaviour a new hook should have is not a matter of taste — classify it before writing it,
using the guarantee-vs-advice test in **[`docs/doctrine/harness-doctrine.md`](docs/doctrine/harness-doctrine.md)**
(*"if a model ignores this, what happens?"*). Advisory → fail open. Guarantee → fail closed, scoped.

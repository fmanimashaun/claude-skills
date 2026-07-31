# CLAUDE.md — maintaining the `claude-skills` marketplace

This repo **is** a Claude plugin marketplace. It ships two kinds of things to other
people, and it carries its own maintenance tooling for you.

- **Distributed (what users install):** the app-builder plugins listed in
  `.claude-plugin/marketplace.json` — `rails-stack` (which bundles the rails-8, hotwire,
  fidara-design and code-review skills), `rails-flow`, `qa-flow`, `pipeline`, `design-flow`
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
`skill-doctor`, `plugin-doctor`, `release-manager`. A SessionStart hook
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

### A promotion is two steps, and only the second publishes

Because the promotion PR's head is `dev`, the bumps have to be on `dev` before it opens. So a
release is:

| # | Step | Branch / PR | Publishes? |
|---|---|---|---|
| 1 | **Arm** — assign versions, convert `Unreleased` headings, write the one release block | `chore/arm-vX.Y.Z` → **`dev`** | **No** |
| 2 | **Promote** — merge dev into main | `dev` → **`main`** | **Yes** — the push to `main` fires the workflow |

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
counter look tidy is what produced 37 no-op merge commits on `dev` earlier; don't.

## Releases are automated — do NOT run `gh release` by hand

`.github/workflows/release.yml` fires on every push to `main`:

1. reads `metadata.version` from `.claude-plugin/marketplace.json` → tag `vX.Y.Z`;
2. if that tag doesn't exist, builds `dist/*.skill` with `scripts/package_core.py`,
   verifies committed `dist/` matches (drift guard), extracts notes from the CHANGELOG
   `(release vX.Y.Z)` block, and publishes the release with **every** `dist/*.skill`
   asset (a glob, never a hand-typed list — that is how a release silently drops a newly
   added skill);
3. if the tag already exists (version wasn't bumped), it is a **no-op**.

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
- **One `### … (release vX.Y.Z)` block per actual promotion.** The workflow publishes
  only the block whose heading matches the shipped tag. A promotion usually consolidates
  several pieces of work, so put ALL their notes under the one release block for the tag
  that ships — never leave `(release vX.Y.Z)` headings for versions that never get tagged,
  or their notes vanish from the published release. (This bit us: v1.6.6 shipped three
  fixes but first published one block's worth of notes.)

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
than the shell does — 154 ruby, 85 erb, 22 js blocks against 79 bash — and it is the same code an
agent pastes into a user's project.

```bash
python3 scripts/lint_markdown_code.py                   # node --check / ruby -c per block
python3 scripts/lint_markdown_code.py --audit-coverage  # prove no block is silently skipped
python3 scripts/lint_markdown_code.py --selftest        # 27 fixtures, mostly SILENCE fixtures
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

**Read its output as three states, not two.** `ok` is verified, `FAIL` blocks work, and **`skip`
means the check did not run — it is not a pass.** That distinction is the whole point: the bug
that prompted this was `build_coverage.py --selftest` printing "35 checks passed" on a machine
with no corpora while two checks against the real repo silently did nothing.

`--fix` touches exactly two things — fast-forwarding the local `main` ref and checking
out/pulling `dev`. It never rewrites history, never `reset --hard`, never `clean`, and it
restores `dist/` byte-for-byte after the drift rebuild, so a diagnostic never mutates the repo.

### The coverage matrix has a browsable page, and it is committed

`docs/coverage.html` — generated by `scripts/build_coverage_artifact.py`, which **imports**
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
- **The page must not stamp anything about the checkout.** It embedded its own short SHA, branch and
  released/unreleased state, which made the gate **unpassable by construction**: committing the page
  advances `HEAD`, and a promotion flips `unreleased` → `released`, so the bytes could only match at
  the one commit that does not yet contain the file. A file inside a commit cannot name its own
  commit. It stamps the release version and the dirty caveat, and nothing else.

A **dirty** tree makes drift genuinely unassessable — the dirty caveat is part of the bytes — so
`--check` returns **3 (INCOMPLETE)**, which the doctor maps to **SKIP**, never `ok`.

**The licensed corpora** (Tailwind UI, Flowbite, Every Layout) live in a separate **private**
repo, `fmanimashaun/design-corpora`, and are **OPTIONAL**. Exactly one file *opens* them —
`scripts/build_coverage.py` — but read that as "one reader", not "one dependency": anything
importing it inherits the dependency, and `build_coverage_artifact.py` does. So a machine without
them can do everything except regenerate or drift-check **either** coverage artifact, and
**no gate fails for their absence** — the two `*-drift` gates SKIP (they are the whole content of
`CORPORA_GATES`), and both selftests still run, reporting their corpora-dependent fixtures as
skipped. That is asserted, not assumed: the doctor's selftest pins that set exactly, in both
directions, because the artifact drift gate was missing from it and a corpora-less machine was told
to "fix the failures before doing maintenance work" about files it is not required to have.
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

## Platform

The `.claude/` hook and the plugins' hooks are **bash + `python3`**, and the flow drives
**`gh`** (authenticated: `gh auth status`). On Windows, run Claude Code in **WSL or Git
Bash** with `python3` and `gh` on PATH. Hooks fail open when a dependency is missing.

# CLAUDE.md — maintaining the `claude-skills` marketplace

This repo **is** a Claude plugin marketplace. It ships two kinds of things to other
people, and it carries its own maintenance tooling for you.

- **Distributed (what users install):** four app-builder plugins listed in
  `.claude-plugin/marketplace.json` — `rails-stack` (the rails-8 + hotwire skills),
  `rails-flow`, `qa-flow`, `pipeline` — plus the `dist/*.skill` packages for claude.ai
  upload.
- **NOT distributed (maintainer tooling, this file's subject):** the flow under
  **`.claude/`** — commands, agents, and a status hook that live only in this repo. They
  are **not** part of the marketplace, so `/plugin marketplace add fmanimashaun/claude-skills`
  never installs them. Anyone who *clones this repo* gets them automatically; that is the
  point. (This replaced an earlier idea of a separate maintainer marketplace repo.)

If you are here to **build a Rails app**, you want the four plugins, not this file.

## The maintenance flow (the `.claude/` commands)

Downstream projects using the toolchain file issues here (via rails-flow's
`/rails-flow:report`, the reporter). You turn those issues into shipped, verified fixes:

- **`/maintainer-setup-intake`** — scaffold `.github/ISSUE_TEMPLATE/*` + the label taxonomy
  (already done for this repo; re-runnable, idempotent).
- **`/maintainer-triage [issue|label]`** — classify open issues by component × type ×
  priority, label, dedupe, and post a ranked queue. (agent: `issue-triager`)
- **`/maintainer-work [issue]`** — take ONE issue end-to-end: confirm → **verify against
  source-of-truth** → fix → PR into `dev` (unversioned, `Refs #n`) → CHANGELOG under
  `Unreleased`. Shipping is a separate, deliberate act: the `dev → main` promotion PR.
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
   `(release vX.Y.Z)` block, and publishes the release with the two `.skill` assets;
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
(uncompressed) + pinned `create_system`, so output is byte-identical on any OS/Python/zlib.
Never zip skills any other way. After any `skills/**` edit: `python3 scripts/package_core.py`
then confirm `git status` shows only the intended `dist/` change. The CI drift guard fails
a release if committed `dist/` isn't a clean build.

## The feedback loop

`/rails-flow:report` (in the rails-flow plugin, shipped to users) → files structured,
deduped, version-pinned issues **here** → you `/maintainer-triage` and `/maintainer-work`
them → `dev → main` auto-releases. Every issue in this tracker arrived this way.

## Platform

The `.claude/` hook and the plugins' hooks are **bash + `python3`**, and the flow drives
**`gh`** (authenticated: `gh auth status`). On Windows, run Claude Code in **WSL or Git
Bash** with `python3` and `gh` on PATH. Hooks fail open when a dependency is missing.

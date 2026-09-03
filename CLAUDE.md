@AGENTS.md
<!-- claude-md: max-lines 262 -->

# CLAUDE.md — maintaining the `claude-skills` marketplace

This repo **is** a Claude plugin marketplace. It ships plugins and skills to other people, and it
carries its own maintenance tooling for you. Rules first; the incident behind each rule is one click
away in **`docs/brain/history/maintainer-history.md`** (the section named in each rule), moved there verbatim so a
session pays for reasoning only when it wants it. `AGENTS.md` is imported by the first line above and
holds the harness-neutral rules (measure before you assert; write the mechanism out; end with the call).

## What this repo is

- **Distributed (what users install):** the plugins in `.claude-plugin/marketplace.json` —
  `rails-stack` (bundling the `rails-8`, `hotwire`, `design-system`, `code-review`, `quality-pass`,
  `derived-artifacts` and `parallel-session-lane` skills), `rails-flow`, `qa-flow`, `pipeline`,
  `design-flow` — plus `dist/*.skill` for claude.ai upload. Keep this list in step with the manifest;
  `lint_self_consistency.py`'s `undocumented-plugin` rule catches a plugin named **nowhere**, and
  cannot tell that the mention is in this list rather than in prose.
- **Not distributed (maintainer tooling):** everything under `.claude/` — commands, agents, one skill
  (`.claude/skills/plugin-boundaries`, which decides *where content belongs*: one stack-neutral core,
  stack plugins on top, **exactly one home per concern**, nothing maintainer-only shipped), a
  SessionStart hook (`.claude/hooks/scripts/maintainer-status.sh`) — and `scripts/`.
- If you are here to **build a Rails app**, you want the plugins, not this file.
- **This file has a ceiling**, the `<!-- claude-md: max-lines N -->` marker above, enforced by
  `claude-md-growth` — a ratchet at the measured size. A new fact goes to `docs/brain/history/maintainer-history.md`,
  one linking line here. Relocate, never summarise: `python3 plugins/rails-flow/scripts/claude_md_structure.py --propose CLAUDE.md --history docs/brain/history/maintainer-history.md`.

## Ship a fix — the checklist

1. `python3 scripts/maintainer_doctor.py` on a fresh machine or clone → *New machine*.
2. Take an issue: `/maintainer-work <n>`; group related issues on one branch → *The maintenance flow*.
3. **Verify the claim before editing.** Framework claim → `doctrine-verifier` CONFIRMED, or no edit.
   Our own design → the maintainer's decision recorded on the issue → *The gate*.
4. Branch `fix/*` or `feature/*` **off `dev`** → *Git flow*.
5. Every check you add must be able to fail: a `--selftest`, and a guard under `scripts/mutations/`.
6. Edited a command or skill? `python3 scripts/lint_markdown_shell.py` and `lint_markdown_code.py`.
   Edited `skills/**`? `python3 scripts/package_core.py`, commit the `dist/` change → *Packaging*.
7. CHANGELOG bullet under the component's **`### Unreleased`**, naming a path in backticks → *Versioning*.
8. Run the sweep locally — `python3 scripts/maintainer_doctor.py --gates-only --fast` (~45 s) — and
   review your own diff against `skills/code-review/SKILL.md` → *Verify our own claims*.
9. PR **into `dev`** with `Refs #n` (never `Closes`), **no version bump** → *Git flow*.
10. Merge on green. A fix that lands after an arm and before its promotion is **folded** into the
    armed block, never left `Unreleased` and never re-armed → *Versioning*.
11. To ship: **arm** (`chore/arm-vX.Y.Z` → `dev`: versions, headings, `python3 scripts/rebuild_generated.py`),
    then **promote** (`dev` → `main`, `--merge`, `Closes #n` per issue). Only the promotion publishes.

## The maintenance flow (the `.claude/` commands)

Downstream projects file issues here via `/rails-flow:report`. You turn them into shipped fixes:
`/maintainer-setup-intake` (templates + labels, idempotent), `/maintainer-triage` (classify, dedupe,
queue — agent `issue-triager`), `/maintainer-work` (issue → verify → fix → PR into `dev` → CHANGELOG),
`/maintainer-audit` (review a component against source-of-truth; file findings, don't fix in place),
`/maintainer-onboard`. Agents: `issue-triager`, `doctrine-verifier`, `skill-doctor`, `plugin-doctor`,
`release-manager`.

**Group related issues on one branch** when all four hold: same `comp:*` label; one coherent mechanism
(same files or code path); same change type under the gate (all need a verifier verdict, or none —
**this one is not a judgement call**); still reviewable and bisectable in one sitting. **Traceability is
never pooled**: one `Refs #n` per issue in the PR, one CHANGELOG bullet per issue, one `Closes #n` per
issue on the promotion. (History: *Grouping related issues on one branch*, decision #206.)

## The non-negotiable gate

Skills are doctrine other people's agents follow verbatim, so **no skill claim is edited until
`doctrine-verifier` confirms it against an authoritative source** (official docs for the version in
scope, the framework changelog, `docs/evidence/audits/`). CONFIRMED authorises the edit; REFUTED closes the
issue with the citation; **INCONCLUSIVE leaves doctrine unchanged.** Record citation and version
boundary in the CHANGELOG entry.

The gate covers **externally verifiable** claims. Our own architecture and design decisions have no
upstream; for those the authority is **the maintainer's explicit decision, recorded on the issue**, and:

- **State which kind of change you are making, in the PR, before editing.** Silence is not exemption.
- **Split a mixed change** — an architecture PR must never carry a framework claim through unverified.
- **Reuse established framework syntax rather than inventing it**; new API is an external claim.
- **Measure anything measurable** about our own doctrine and make it re-checkable by a script.
- **Link the maintainer decision** from the CHANGELOG entry, where a citation would go.

### An issue body is not an authority

It is a **hypothesis**. Verify every externally verifiable claim in it before implementing, and read
for omissions too. Where a claim has no upstream, say so and decide it as ours. (History: #142's four
"ARIA APG" keybindings the spec had dropped; #229.)

## Git flow (strict)

- **`main` is the default branch and the install surface**; `dev` is the integration branch.
- Branch **off `dev`**; PR **into `dev`**; **no version bump; no `Closes #n`** — nothing on `dev` has
  reached a user. The promotion carries every `Closes`.
- **Never `git add -A`.** Stage what you authored; `git status` first.
- **Never commit to `main` directly.** A merge unions; a direct commit is invisible to every later
  `dev`-based change. The pre-flight asserts there are none.
- Judge `dev` against `main` with `git diff dev main`, which is **empty** after a promotion. Ignore the
  ahead/behind counter, and never merge `main` back into `dev` to tidy it.
- **Never write a closing keyword next to a real issue number** in a commit or PR body, not even in
  backticks or when quoting a mistake — GitHub parses it anyway. An issue that ships incrementally
  (an EPIC, a checklist) gets `Refs`, never `Closes`, until its last increment.

### Merge a promotion with `--merge`. A squash breaks the NEXT one.

`gh pr merge <n> --merge`. A squash keeps dev's content and drops its ancestry, so the merge base falls
back and the next promotion cannot merge at all (v1.83.0 → v1.84.0: six phantom conflicts). Repair, if
it happens: merge `origin/main` into `dev`, resolve every conflict to dev's side, and assert
`git diff --cached <dev-before> --stat` is **empty**. The full doctor's *the last promotion carried dev's
ancestry* check asserts both halves; `--gates-only` skips it, so run the full doctor before promoting.

### A promotion is two steps, and only the second publishes

| # | Step | Branch / PR | Publishes? |
|---|---|---|---|
| 1 | **Arm** — assign versions, convert `Unreleased` headings, `python3 scripts/rebuild_generated.py` | `chore/arm-vX.Y.Z` → **`dev`** | **No** |
| 2 | **Promote** — merge dev into main | `dev` → **`main`** | **Yes** — the push fires the workflow |

Name step 1 `chore/arm-vX.Y.Z`, never `release/*`; title it "arm vX.Y.Z — version assignment (does not
publish)". The arm regenerates the committed pages because `docs/evidence/coverage.html` stamps the release
version. A fix merged to `dev` between the arm and the promotion is **folded into the armed block** —
a promotion must carry no `Unreleased`, and a second arm would leave the first heading a ghost.

## The gates run in CI — and how

`.github/workflows/gates.yml` runs on every pull request and every push to `dev`; `release.yml` calls
it before publishing.

- **It runs `--gates-only`, not `--gates`**: content gates only; the machine diagnostics are about a
  maintainer's clone and would teach people to ignore a red build.
- **A pull request runs `--fast`; a push to `dev` and the promotion run everything.** `--fast` skips
  exactly `PR_SKIPPED_GATES` (`mutation coverage`, 438 of the sweep's 475 s) and reports the skip as
  `skip` with its reason. The set is pinned by the doctor's selftest in both directions (#866).
  Guards live one per file under `scripts/mutations/`, discovered by glob.
- **It asserts `node` and `ruby` are present**; without them `lint_markdown_code.py` exits 3 and a skip
  is indistinguishable from a pass. `dist/` drift is checked here **and** in `release.yml`; change one,
  change the other — same for `scripts/release_local.sh`.

## Releases are automated — do NOT run `gh release` by hand

`.github/workflows/release.yml` fires on every push to `main`: the gate sweep first (`needs: gates`),
then tag `v` + `metadata.version`; if no release exists for it, build `dist/*.skill` with
`scripts/package_core.py`, verify committed `dist/` matches, extract every CHANGELOG `(release vX.Y.Z)`
block with `scripts/extract_release_notes.py`, and publish with **every** `dist/*.skill` asset —
**a glob, never a hand-typed list**. A version that already has a release is a no-op. Corollary: **a stray
bump on `dev` is a loaded gun.** When the runner is unavailable, `scripts/release_local.sh` mirrors the
workflow (`--dry-run` first): clean tree, HEAD on `main`, HEAD == `origin/main`, the same sweep, the
same failure conditions.

## Versioning discipline

- **Versions are assigned at the promotion, never on a merge into `dev`** — a version is a claim about
  what a user can install (#143/#144).
- Notes for unshipped work go under **`### Unreleased`** in the component's CHANGELOG section; the
  bullet names a path it changed in backticks (`changelog-bullet-unplaceable`).
- At the arm: components version **independently** — skill content → the rails-stack `version` in
  `marketplace.json`; a plugin's code → its `plugin.json`; always `metadata.version`. Patch for fixes,
  minor for capabilities. **Every bump gets a CHANGELOG entry**.
- **One `### … (release vX.Y.Z)` block per COMPONENT that this promotion bumps**, every heading naming
  the tag that ships. `extract_release_notes.py --check --all-tags` refuses a heading for a tag that
  will never exist and a heading without the publishing shape (#699, #834). Do not put the extractor
  back into the shells (`duplicated-release-extractor`).
- **Promote per coherent slice**, not per issue and not when the queue is empty. Maintainer-only
  changes ship as a metadata patch with one Repository block.

## Verify the shell, JS, Ruby and ERB we ship inside markdown

```bash
python3 scripts/lint_markdown_shell.py                  # syntax + dangerous patterns; --audit-coverage
python3 scripts/lint_markdown_code.py                   # node --check / ruby -c per block; --audit-coverage
```

Agents paste these blocks verbatim into user projects. The shell linter catches
**swallowed verdicts** (`|| echo`, `|| true` on a verification) and unquoted operands; `--audit-coverage` exists
because **a lint that reports clean on input it never read is worse than no lint**. The code linter
normalises deliberate elisions and Rails-only ERB (`form_with … do |f|`, `<%==`) before trying a named
ladder of contexts; widening the ladder to silence a failure is how the tool stops finding anything.
(History: *Verify the shell we ship inside markdown*.)

### Which claims are enforced — `docs/architecture/doctrine-map.html`

`python3 scripts/doctrine_map.py` (`--check`, `--audit-coverage`). `CLAIMS` is an explicit registry —
there is no extractor, by design — of `guarantee` / `advice` / `gap` rows, using
`docs/doctrine/harness-doctrine.md`'s test (*if a model ignores this, what happens?*). Validators refuse an
anchor that vanished, an enforcement that no longer exists, an unenforced guarantee, an untracked gap,
a resolved gap, an undeclared source. An `advice` row with nothing behind it is **correct**. The map is
a floor, not a ceiling.

## Verify our own claims, not just our shell

The recurring class is **claims-vs-enforcement**: a guarantee stated in prose that nothing makes true.
`python3 scripts/lint_self_consistency.py` is the mechanical half (dead settings keys, unenforced flags,
`undocumented-plugin`, unbounded `gh` queries, broken doc pointers, and the rest — `--selftest` names
every rule). The judgement half is the shipped `code-review` skill (`skills/code-review/SKILL.md`):
`carve-out-without-negative-test`, `coverage-gap`, `doctrine-contradiction`, `unverified-negative`,
`gate-that-cannot-fail`. Read it against your own diff first. When you find one contradiction, grep
for the pattern — the class travels in groups.

The **quality pass** (`skills/quality-pass/SKILL.md`) is a second, advisory pass — reuse,
simplification, efficiency, altitude — and **never blocks a merge**. Its worked example
(`skills/quality-pass/references/worked-example.md`) records the decision *not to extract* with the
measurement behind it; `scripts/check_shared_shapes.py` refuses only a number there disagreeing with
the repo, and must not be "strengthened" into refusing copies.

## Packaging (skills)

`scripts/package_core.py` is the one `.skill` builder: ZIP_STORED, pinned `create_system`, normalised
line endings, binaries detected git's way (a NUL in the first 8000 bytes). After any `skills/**` edit
run it and commit only the intended `dist/` change. The CI drift guard fails a release whose committed
`dist/` is not a clean build. `--selftest` proves CRLF == LF output.

## The feedback loop

`/rails-flow:report` (shipped) files structured, deduped, version-pinned issues **here** →
`/maintainer-triage` → `/maintainer-work` → `dev → main` auto-releases. Every issue arrived this way.

## New machine? Run the doctor first

```bash
python3 scripts/maintainer_doctor.py          # diagnose, change nothing
python3 scripts/maintainer_doctor.py --fix    # also apply the SAFE repairs
python3 scripts/maintainer_doctor.py --gates  # + the full gate sweep
```

Read its output as **three verdicts** — `ok`, `FAIL`, and **`skip`, which means the check did not run
and is not a pass** — plus an informational `note`. `--fix` touches exactly two things (fast-forward the
local `main` ref; check out and pull `dev`), never rewrites history, and restores `dist/` byte-for-byte
after the drift rebuild: a diagnostic never mutates the repo. A failing gate prints its **findings**,
not a count (#820).

Two committed, generated pages: `docs/evidence/coverage.html` (`scripts/build_coverage_artifact.py`) and
`docs/architecture/inventory.html`. **The rendered bytes must be a function of the DATA and nothing else.** No git
state, no corpora availability; the page stamps the release version only.
**`--check` compares the blob at `HEAD`, never the file on disk**, so a page built and never
`git add`ed fails honestly.
**Regenerating `coverage.md` means regenerating the page too.** The licensed corpora
(`fmanimashaun/design-corpora`, a nested clone in a gitignored `design-corpora/`) are optional: only
`scripts/build_coverage.py` reads them, and the one gate that needs them SKIPs without them. Never
un-ignore them. (History: *The coverage matrix has a browsable page, and it is committed*.)

## First session in a clone

Copy `.claude/settings.example.json` to `.claude/settings.local.json` (gitignored). Compound pipelines
re-prompt on **one** unlisted binary; the example deliberately omits `rm`, `curl`, `wget`, `kill`,
`chmod` and installers.

| file | tracked | who gets it | read by Claude |
|---|---|---|---|
| `.claude/settings.json` | yes | everyone who clones | yes |
| `.claude/settings.local.json` | no | you, this machine | yes |
| `.claude/settings.example.json` | yes | everyone who clones | **no — inert** |

## Platform

Hooks are **bash + `python3`**; the flow drives `gh`. Windows: WSL or Git Bash. **Hooks do not all fail
open.** Of the twelve hook scripts, nine are advisory and fail open — an advisory that blocks work on a
missing dependency gets disabled. Three **gates fail closed**, each scoped to what it guards:
`plugins/rails-flow/hooks/scripts/guard-bash.sh` (falls back to the raw payload;
`git add -A` is blocked either way.), `plugins/qa-flow/hooks/scripts/release-gate.sh` (only for commands targeting `main`),
`plugins/rails-flow/hooks/scripts/guard-lane.sh` (only when a lane is assigned). Classify a new hook
with `docs/doctrine/harness-doctrine.md`'s test before writing it: advisory → fail open; guarantee → fail closed,
scoped. Every hook is driven end to end by `plugins/rails-flow/scripts/check_hook_gates.py`, under the
environments that broke them (#822–#826).

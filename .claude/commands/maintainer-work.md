---
description: Take one reported issue through the maintenance loop — confirm, verify against source-of-truth, fix, PR into dev (unversioned), CHANGELOG under Unreleased. One issue at a time; shipping is a separate promotion.
argument-hint: "[issue number]"
---

# /maintainer-work — $ARGUMENTS

Work a single issue end to end. One at a time, full loop every time, nothing
half-done — the same discipline as `/rails-flow:issues`, adapted to maintaining
doctrine and plugins.

## Precondition — marketplace repo only (hard)

MAINTAINERS-ONLY. Confirm `.claude-plugin/marketplace.json` exists at the repo root before
branching, editing, or committing. If absent, STOP and tell the user this plugin is for
maintaining a claude-skills marketplace repo, not an app project — change nothing. (Same
test as the SessionStart hook.)

## Phase 0 — Pick & context

Confirm `gh auth status`. If `$ARGUMENTS` names an issue, work it; else take the head of
the triaged queue (run `/maintainer-triage` first if nothing is triaged). Read the
issue and its labels. Comment on the issue that work is starting. Branch off **`dev`** —
the integration branch, NOT the default branch (`main` is default because it is the install
surface, and work never starts from it): `fix/issue-<n>-<slug>` for bugs/doctrine,
`feature/issue-<n>-<slug>` otherwise.

## Phase 1 — Confirm the problem

Reproduce or locate it concretely. If it can't be confirmed, comment with what's
missing, apply `needs-info`, and stop — never fix a guess.

## Phase 2 — Route by component/type

- **`type:incorrect-doctrine` or `type:skill-gap` (comp:rails-8 / comp:hotwire)** →
  **doctrine-verifier FIRST** (BLOCKING). Only a **CONFIRMED** verdict authorizes
  **skill-doctor** to edit; REFUTED → close the issue with the citation; INCONCLUSIVE →
  leave doctrine unchanged and report what evidence is needed.
- **`type:bug` / `type:feature` (comp:rails-flow / qa-flow / pipeline)** →
  **plugin-doctor**, which reproduces, fixes, and tests every changed script.
- **comp:packaging / comp:marketplace** → fix the builder/manifest directly; prove
  reproducibility (`python3 scripts/package_core.py` → clean `git status`).

## Phase 3 — Verify the fix

Doctrine: citation recorded, `dist/*.skill` repackaged and valid. Plugin: `bash -n` +
behavior reproduction + other paths intact. Nothing proceeds without evidence.

## Phase 4 — PR into `dev` (unversioned)

Push the branch and open a PR **into `dev`** whose body carries the fix and the evidence
(verifier citation or test output).

Two hard rules, both the opposite of what feels natural:

- **Reference the issue, do not close it: write `Refs #<n>`, never `Closes #<n>`.** `main`
  is the default branch, so a closing keyword here would either do nothing or — worse, if
  someone flips defaults back — mark an issue done while its fix sits unshipped on `dev`.
  The promotion PR closes it, when it actually ships.
- **Bump NO versions.** Not `metadata.version`, not the plugin's `plugin.json`, not the
  rails-stack entry. A version is a claim about what a user can install, and nothing on
  `dev` is installable. Add the CHANGELOG notes under a **`### Unreleased`** heading in the
  component's section instead, with a line saying the number is assigned at promotion.
  (A stray bump on `dev` is a loaded gun: the next promotion publishes a release the moment
  it merges, decided by nobody. This is exactly what #143 did and #144 undid.)

Repackage `dist/` in this PR if `skills/**` changed — that is content, not a version.

## Phase 5 — Stop. Shipping is a separate, deliberate act.

**Do not promote as part of working an issue.** `/maintainer-work` ends when the fix is
merged to `dev`. Report that the work is staged and unreleased, and say what a promotion
would ship.

Promotion is its own decision, made per coherent slice (a feature, or a batch of related
fixes) — not per issue, and not held until the queue is empty. When the user calls for it,
hand to **release-manager** for the `dev → main` PR: assign the version numbers, rename the
`Unreleased` headings, write the ONE `(release vX.Y.Z)` block, carry every `Closes #n` for
what ships, confirm packaging is canonical, and merge. The workflow publishes the release —
never run `gh release` by hand.

## Report

Issue → verdict/reproduction → fix → PR into `dev` → **staged, unreleased** (name what a
promotion would ship). Then name the next queue item; do not start it without the user.

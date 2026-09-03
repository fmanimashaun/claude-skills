---
description: Take a reported issue through the maintenance loop — confirm, verify against source-of-truth, fix, PR into dev (unversioned), CHANGELOG under Unreleased. Group related issues on one branch to cover more ground; traceability stays per-issue. Shipping is a separate promotion.
argument-hint: "[issue number]"
---

# /maintainer-work — $ARGUMENTS

Work an issue end to end. Full loop every time, nothing half-done — the same discipline
as `/rails-flow:issues`, adapted to maintaining doctrine and plugins.

**Group related issues on one branch** — it covers more ground per branch, and for issues that
are one change wearing several numbers it is the only honest shape. Group when they share a
`comp:*` label and one coherent mechanism (same files or code path), need the same change type
under the doctrine gate, and stay reviewable in one sitting. There is no fixed cap. See
CLAUDE.md, *Grouping related issues on one branch* (decision: #206). If the fixes never touch
each other, grouping buys nothing — split then.

When you do group, traceability is **not** pooled: one `Refs #n` per issue in the PR body, one
CHANGELOG bullet per issue, and a separate `Closes #n` for each on the promotion.

## Precondition — marketplace repo only (hard)

MAINTAINERS-ONLY. Confirm `.claude-plugin/marketplace.json` exists at the repo root before
branching, editing, or committing. If absent, STOP and tell the user this plugin is for
maintaining a claude-skills marketplace repo, not an app project — change nothing. (Same
test as the SessionStart hook.)

## Phase 0 — Pick & context

Confirm `gh auth status`. If `$ARGUMENTS` names an issue, work it; else take the head of
the triaged queue (run `/maintainer-triage` first if nothing is triaged).

**Then check the pick against the graph before branching, naming every issue you intend to
put on the branch** (#133):

```bash
python3 scripts/issue_graph.py --ready 109 110
```

It exits non-zero — refusal on stderr, stdout left empty — when any named issue waits on open
work, is already closed, is absent from the tracker, or when the graph is too broken to answer
from. "Take the head of the queue" was a claim nothing checked; this is the check. Edges
*between* the issues you named are satisfied by the branch itself, so a grouped branch
declares its whole set in one call and only learns which member goes first.

On a refusal: work the blocker first, or state in the PR body that you are going out of the
computed order on purpose and why. Do not silently proceed. A READY verdict on an issue that
declares no edges says so in a note — that means the tracker names no blocker, not that
none exists, and it is the common case until the epic backfill lands.

Read the issue and its labels. Comment on the issue that work is starting. Branch off **`dev`** —
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

**If you touched markdown containing a shell block** — any command or skill file — also run
`python3 scripts/lint_markdown_shell.py`. Those blocks are executed verbatim in user projects
and were unverified until v1.21.x; a `--check || echo` shipped there and made a release gate
unable to block. `bash -n` on `.sh` files does not cover them.

**Then run the sweep — `python3 scripts/maintainer_doctor.py --gates-only --fast` — about forty
seconds now that `mutation coverage` runs on `dev` pushes and at promotion rather than per PR (#866).
It covers both linters above and every other content gate; a PR opened on a red local sweep is a PR
that asks the runner to find what a minute at the keyboard would have. Then review your own diff
against the `code-review` skill (`skills/code-review/SKILL.md`).** Both exist because a rented reviewer
kept catching a class our own review missed — and it had no special power: it checked the
diff against rules already written in this repo's markdown. The recurring class is
**claims-vs-enforcement**, a guarantee stated in prose that nothing makes true. It has
bitten three times in three PRs (`--check || echo`; a README mandating a flag the code left
optional; a docstring promising behaviour the code lacked), so the checkable half is now a
linter and the rest is that skill. Apply its class list to your own diff *before* asking
anyone else to — and note the skill is doctrine we ship, so it is the same rules a user's
`pr-reviewer` applies, not a maintainer-only checklist.

## Phase 4 — PR into `dev` (unversioned)

Push the branch and open a PR **into `dev`** whose body carries the fix and the evidence
(verifier citation or test output).

Two hard rules, both the opposite of what feels natural:

- **Reference the issue, do not close it: write `Refs #<n>`, never `Closes #<n>`.** `main`
  is the default branch, so a closing keyword here would either do nothing or — worse, if
  someone flips defaults back — mark an issue done while its fix sits unshipped on `dev`.
  The promotion PR closes it, when it actually ships. **On a grouped branch, one `Refs #n`
  per issue and one CHANGELOG bullet per issue** — a single bullet covering "both issues"
  loses which fix answered which report, and the promotion then cannot say what it closed.
- **Bump NO versions.** Not `metadata.version`, not the plugin's `plugin.json`, not the
  rails-stack entry. A version is a claim about what a user can install, and nothing on
  `dev` is installable. Add the CHANGELOG notes under a **`### Unreleased`** heading in the
  component's section instead, with a line saying the number is assigned at promotion.
  (A stray bump on `dev` is a loaded gun: the next promotion publishes a release the moment
  it merges, decided by nobody. This is exactly what #143 did and #144 undid.)

Repackage `dist/` in this PR if `skills/**` changed — that is content, not a version.

**Check what the body claims, not just what the diff does.** The gate above verifies the *doctrine*;
this verifies the *description*, and they fail differently. Three defects shipped from this repo in
one day whose diffs were each internally consistent and whose sentences were wrong — *"the gates run
in CI"* when every PR check was third-party, *"the publish is gated"* when the release job had no
`needs:`, and a scaffolded CI job referencing a variable that does not exist in GitHub Actions
(#359). No diff review catches those, because the defect is not in the diff.

```bash
python3 plugins/rails-flow/scripts/extract_claims.py /tmp/pr-body.md
```

Hand the list to **`claim-verifier`**, which checks each by **running or grepping** rather than
reasoning. An unverifiable claim is a finding: make it checkable or delete it. This is cheap here
and mandatory at the promotion, where the body becomes the published release notes — see
`release-manager`.

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

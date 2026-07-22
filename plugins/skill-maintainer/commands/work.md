---
description: Take one reported issue through the full maintenance loop — confirm, verify against source-of-truth, fix, PR, version bump + CHANGELOG, release. One issue at a time.
argument-hint: "[issue number]"
---

# /skill-maintainer:work — $ARGUMENTS

Work a single issue end to end. One at a time, full loop every time, nothing
half-done — the same discipline as `/rails-flow:issues`, adapted to maintaining
doctrine and plugins.

## Phase 0 — Pick & context

Confirm `gh auth status`. If `$ARGUMENTS` names an issue, work it; else take the head of
the triaged queue (run `/skill-maintainer:triage` first if nothing is triaged). Read the
issue and its labels. Comment on the issue that work is starting. Branch off the default
branch: `fix/issue-<n>-<slug>` for bugs/doctrine, `feature/issue-<n>-<slug>` otherwise.

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

## Phase 4 — PR

Push the branch and open a PR whose body carries the fix, the evidence (verifier
citation or test output), and **`Closes #<n>`** so the merge auto-closes the issue.

## Phase 5 — Ship (release-manager)

After the PR is approved/merged, hand to **release-manager**: bump only the component(s)
that changed (skill → rails-stack entry; plugin → its plugin.json; always the top-level
`metadata.version` as the tag), add the CHANGELOG entry (with the doctrine citation),
confirm packaging is canonical, and cut the tagged release with the `.skill` assets.
Verify the issue closed.

## Report

Issue → verdict/reproduction → fix → PR → component bump (old → new) → release URL. Then
name the next queue item; do not start it without the user.

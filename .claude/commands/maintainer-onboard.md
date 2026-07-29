---
description: Bring a maintainer machine up to speed — diagnose and repair the setup, then report released version, unshipped work, and candidate next work
argument-hint: "[--fix to apply the safe repairs]"
---

# /maintainer-onboard — $ARGUMENTS

Get a machine (and yourself) ready to maintain this marketplace. Run this **first** on a new
machine, or after any long gap.

This exists because the setup knowledge used to live only in someone's head. Moving maintenance
to a second machine once needed a hand-written 120-line briefing, and it was only complete
because the author had just hit every trap personally. A checklist in a readme would be the
same defect class this repo keeps paying for — a guarantee in prose that nothing makes true —
so the mechanical half is a script that can fail.

## Phase 1 — Diagnose the machine (mechanical)

```bash
python3 scripts/maintainer_doctor.py
```

Exit `0` = no failures · `1` = at least one failure · `2` = not a claude-skills checkout.

Read the output as **three** states, not two:

- **`ok`** — verified.
- **`FAIL`** — must be fixed before doing maintenance work. Each names a remedy.
- **`skip`** — the check **did not run**. It is *not* a pass. The commonest is the licensed
  corpora being absent, which is fine for most work but means the coverage matrix cannot be
  regenerated or drift-checked.

If it reports failures that are safe to repair mechanically — a stale local `main` ref, or
being parked on `main` — re-run with `--fix`. That touches exactly two things: fast-forwarding
the local `main` ref to `origin/main`, and checking out/pulling `dev`. It never rewrites
history, never `reset --hard`, never `clean`. Everything else it reports for a human to do
deliberately.

Then the full sweep, once the basics are green:

```bash
python3 scripts/maintainer_doctor.py --gates
```

Do NOT treat a passing sweep on a corpora-less machine as full coverage — the coverage-matrix
gates skip, and the doctor says so.

## Phase 2 — Load the doctrine (judgement)

Read, in this order:

1. **`CLAUDE.md`** — not a readme. It encodes rules that were each paid for: the strict git
   flow, why "never commit to `main`" is a correctness rule rather than tidiness, the two-step
   arm→promote release, and the doctrine-verifier gate that blocks skill edits without a cited
   source.
2. **`skills/code-review/SKILL.md`** — the review doctrine, applied to your own diff *before*
   anyone else's. It is shipped doctrine, so it is the same rules a user's `pr-reviewer` runs.
3. The component you are about to touch — `skills/*/references/`, or the plugin's agents and
   commands.

## Phase 3 — Report where things stand

Gather and report, without editing anything:

```bash
git describe --tags --abbrev=0 origin/main          # last shipped release
git log --oneline origin/main..dev                  # what a promotion would ship
gh issue list --state open --label 'prio:P1' --limit 20
```

Then tell the user, in a few lines:

- **released** version, and whether `dev` is content-identical to `main`
  (`git diff dev origin/main` empty). Never quote the ahead/behind counter — `main` gains one
  merge commit per release that `dev` never receives, so `dev` reads as tens of commits
  "behind" while being identical.
- **unshipped work** on `dev`, from the CHANGELOG's `### Unreleased` sections, and whether it
  is worth a promotion on its own.
- **doctor findings** that need a human.
- **candidate next work** — the P1 queue, plus `coverage.md`'s `needs doctrine` rows if the
  work is design-system related.

## Phase 4 — Stop

Do not start an issue. Name the candidates and let the user choose — the queue's priority
labels are input to that decision, not a substitute for it.

## Notes

- The licensed design corpora live in a separate **private** repo and are needed by exactly one
  file, `scripts/build_coverage.py`. The doctor prints the clone-and-symlink remedy when they
  are missing. Committing them into this repo is not an option: ~656 MB of licensed blobs in
  this history could only be removed with `git filter-repo` and a force-push that rewrites
  every commit SHA and detaches the release tags.
- If `gh` is unauthenticated, even `git fetch` can fail while the repo is private. The doctor
  checks this explicitly rather than letting it surface as a confusing fetch error.

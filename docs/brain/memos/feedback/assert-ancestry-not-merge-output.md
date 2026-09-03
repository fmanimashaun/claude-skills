---
name: feedback-assert-ancestry-not-merge-output
description: In the multi-worktree setup, `git merge origin/dev` can print "Already up to date" while origin/dev is genuinely ahead — assert ancestry instead.
type: feedback
---

Across the four sibling worktrees (`claude-skills`, `cs-qa`, `cs-df`, `cs-rf`) sharing one `.git`,
running `git fetch origin && git merge origin/dev` **as a single compound command** reported
`Already up to date.` while `origin/dev` was two commits ahead. Fetching immediately before is
necessary but NOT sufficient.

**Why:** `git merge-base --is-ancestor origin/dev HEAD` returned non-zero seconds later, and
`git rev-parse origin/dev` showed a different sha than the merge had acted on. Other sessions land
PRs into `dev` continuously, so the ref moves mid-command.

**How to apply:** never trust the merge's own output as proof. After merging, assert it:

```bash
git fetch origin
git merge origin/dev
git merge-base --is-ancestor origin/dev HEAD && echo "HEAD contains origin/dev"
```

Re-run the gate sweep after a real merge lands — the base changed, so earlier green results were
about a different tree. Related: [[verify-counts-before-stating-them]] (same shape: the tool's
summary line is not the evidence), [[fix-defects-in-the-same-work]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, assert-ancestry-not-merge-output.md._

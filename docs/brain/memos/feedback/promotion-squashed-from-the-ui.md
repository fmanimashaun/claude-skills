---
name: feedback-promotion-squashed-from-the-ui
description: A promotion merged in the GitHub UI defaults to squash; verify main's tip has TWO parents after every publish, and repair dev's ancestry immediately if not
type: feedback
---

On 2026-09-03 the maintainer merged promotion PR #894 themselves ("released"); main's tip `de4a4ea` had
ONE parent — a squash. Content was byte-identical to dev, so nothing looked wrong, but dev's tip was no
longer an ancestor of main: the exact v1.83.0→v1.84.0 defect (six phantom conflicts at the next
promotion). The repo allows all three merge methods and has no ruleset or branch protection on main.

**Why:** `gh pr merge --merge` is our rule, but the UI's default button is whatever the repo allows; a
human clicking "Merge" is not bound by CLAUDE.md. The damage is invisible until the NEXT promotion.

**How to apply:** after any publish you did not perform, run `git log -1 --format=%p origin/main` and
`git merge-base --is-ancestor origin/dev origin/main` before anything else. If one parent: on dev,
`git merge --no-edit origin/main`, assert `git diff <dev-before> dev --stat` is empty and
`merge-base --is-ancestor origin/main dev`, push dev. Then propose the ruleset (main: merge only).
Related: [[assert-ancestry-not-merge-output]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, promotion-squashed-from-the-ui.md._

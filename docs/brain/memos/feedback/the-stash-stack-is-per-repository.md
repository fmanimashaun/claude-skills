---
name: feedback-the-stash-stack-is-per-repository
description: git stash is shared by every worktree and session of a repo; a bare `stash drop`/`pop` takes whoever pushed last. Revert one file with `git restore -- <path>`.
type: feedback
---

To discard one uncommitted edit in a Retask worktree I ran `git stash push -- <path>` then a bare
`git stash drop`. **The stash stack belongs to the repository, not the worktree, branch or
session** — a bare `drop`/`pop` acts on `stash@{0}`, whoever pushed it. A peer's stash landing
between the two commands, or a `push` that creates nothing because the file was already clean,
makes the `drop` take theirs. It was safe only because the stack happened to be empty. Two nights
earlier in the same repo a bare `pop` pulled another session's fourteen files back as conflicts.

**Why:** several sessions share one Retask repo through linked worktrees; `refs/stash` is common.

**How to apply:** revert a single file with `git restore -- <path>` (scoped, touches no shared
ref — and still not `git checkout --`, see [[exit-status-describes-the-command-not-the-state]]).
Discard a whole throwaway worktree with `git worktree remove --force` **only after** checking no
process runs in it and HEAD is in `origin/<branch>`. If a stash is truly needed, drop it by the
ref its push printed, never bare.

**Verifying "the ref is mine" has its own trap** (found by a peer, 2026-09-23):
`git stash list --format=%gs -n1 stash@{N}` IGNORES the ref and prints the TOP entry, so a
check-then-drop by ref silently checks the wrong stash whenever the target isn't on top. Use
`git stash list --format='%gd|%gs'` and match the exact `%gd` column before `git stash drop stash@{N}`. Related: [[a-dirty-file-in-a-shared-checkout-has-no-author]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, the-stash-stack-is-per-repository.md._

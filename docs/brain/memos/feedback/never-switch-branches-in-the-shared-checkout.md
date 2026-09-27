---
name: feedback-never-switch-branches-in-the-shared-checkout
description: Several sessions run from the primary claude-skills checkout; a branch switch there moves all their HEADs. Fix in a worktree.
type: feedback
---

On 2026-09-23 I did five fixes by `git checkout -b fix/…` in `/Users/fmanimashaun/projects/claude-skills`
while four other sessions ran from that same directory. claude-skills-0b had to ask me to stop: a
branch switch there moves every session's HEAD at once, and the SessionStart hook reads that tree.

**Why:** the primary checkout is shared state with no owner. Its HEAD is an input to everyone else's
work, the same way a dirty file is ([[a-dirty-file-in-a-shared-checkout-has-no-author]]).

**How to apply:** when `ListAgents` shows any other session in this repo, keep the primary checkout
on `dev`. Do each fix in `git worktree add <scratchpad>/wt-<n> -b fix/<n> origin/dev`, and remove the
worktree after the merge. Related: [[a-run-owns-its-worktree]], [[confirm-your-branch-not-just-your-repo]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, never-switch-branches-in-the-shared-checkout.md._

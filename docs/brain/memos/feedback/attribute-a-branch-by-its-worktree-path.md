---
name: feedback-attribute-a-branch-by-its-worktree-path
description: Session names rotate and `author` is the shared account — only `git worktree list --porcelain` carries the owner, and I published a reflog query that does not.
type: feedback
---

With several sessions in one repository, **three obvious ways to ask "whose branch is this?" all fail**:

- **the session name** — rotates daily. I was `e7`, then `a9`, then `38`, then `30`'s peer, in one day; a
  name I held in the morning belonged to someone else by afternoon, and a coordinator reassigned two
  live PRs on the strength of one.
- **`gh pr list --author @me --limit 100`** — every session commits as the one account. On Retask it returned
  five open PRs of which exactly one was mine.
- **a reflog glob over `"$GD"/worktrees/*/logs/HEAD`** — **this is the one I got wrong and told four
  sessions to use.** `grep -o` discards the filename; even `-H` gives the worktree *directory* name
  (`wt-1157`), chosen by whoever made the lane, which maps to no session.

**What works:** `git worktree list --porcelain` — the lane's path contains the owning session's id,
so the branch's owner is in the output. It settled a two-session dispute over one PR in one command.

**The boundary, which matters as much as the method:** a branch whose worktree has **disappeared**
keeps its commits and its PR and loses its row. **No row does not mean no owner** — measured, a
branch with four commits and an open PR appeared in none of eleven rows. Ask before concluding from
silence.

**Why:** the reflog query was an instance of [[a-value-two-causes-both-produce]] and I did not apply
my own class to my own tool — `wt-1157` is produced by "the session that owns it" and by "any
session that named a directory that way", and nothing in the output separates them.

**How to apply:** attribute by `git worktree list --porcelain` and compare against your own
scratchpad path; treat an absent row as *unknown*, never as *unowned*; and before claiming a branch,
run it rather than asserting harder. Related: [[a-dirty-file-in-a-shared-checkout-has-no-author]],
[[confirm-your-branch-not-just-your-repo]], [[an-unpushed-branch-in-a-scratch-worktree]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, attribute-a-branch-by-its-worktree-path.md._

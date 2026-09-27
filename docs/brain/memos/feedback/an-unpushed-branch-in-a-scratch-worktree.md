---
name: feedback-an-unpushed-branch-in-a-scratch-worktree
description: A worktree directory under /private/tmp can vanish between sessions; if the branch was never pushed, one local ref is the only copy.
type: feedback
---

A scratch worktree's directory can be gone when you resume, with no warning. If the branch was
never pushed, the work exists only as a ref in the primary checkout's `.git`. Mine survived a
day's work that way — two migrations, a model rewrite, 18 examples.

**Why:** the lane skill frames pushing as *discoverability* ("push it, and peers can query it"),
never durability, and reports that 18 of 19 branches were already pushed — which reads as
reassurance. The 1 in 19 is the one that gets lost. Three sessions lost a worktree the same day.

**How to apply:** push at the **commit**, not at the PR — `git push -u origin <branch>` costs
nothing and needs no draft PR. To recover, decide before you act, because the two cases look alike:

    git worktree list                    # the lost one is marked `prunable`
    git log --oneline -1 <your-branch>   # prints -> recoverable; silent -> gone

Only then `git worktree prune && git worktree add <path> <branch>`, and push first thing. Silent
means nothing survives, and prune-and-recreate will hand you an empty worktree on a commitless
branch that looks like success.

A recreated worktree is missing **every gitignored file** — credentials key, `.env`, build
artifacts — and the suite then fails as a behaviour bug rather than a setup one. See
[[verify-in-the-environment-it-runs-in]] and [[a-stale-server-fails-as-a-behaviour-bug]].

Use `git archive <tag> <path> | tar -x -C <dir>` to get a pinned toolchain without checking
anything out, when the repo is a shared checkout other sessions are working in
([[a-dirty-file-in-a-shared-checkout-has-no-author]]).

## Worse the second time: I held the commit until the run went green (2026-09-23)

Same night, same class, and the version that actually cost work. I rewrote three spec files, started
a browser suite to verify them, and the session restarted mid-run. **The scratchpad was wiped — the
worktree, the log and every edit with it.** The branch survived with no commits on it, because I had
not made one. All three rewrites were gone and I redid them from context.

**Why I had not committed: I was waiting for green.** That is backwards, and it is the specific
mistake worth naming — "push at the commit" is useless if you are holding the commit until the
verification passes. The run is exactly the window in which work is most likely to be lost, because
it is the longest one, and it is also the window in which the tree must not change anyway
([[a-run-owns-its-worktree]]).

**How to apply: commit and push BEFORE starting a long verification run, not after.** The commit
message can be written as a claim and corrected by an amend if the run is red — a wrong commit
message costs one `--amend`, a wiped worktree costs the work. Assert the push by ancestry
(`git merge-base --is-ancestor <sha> origin/<branch>`) before the run starts, so the thing you are
about to spend ten minutes verifying exists somewhere other than a temp directory
([[exit-status-describes-the-command-not-the-state]]).

A scratchpad under `/private/tmp` does not survive a session restart. A `git worktree` inside one
inherits that, and neither warns you.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, an-unpushed-branch-in-a-scratch-worktree.md._

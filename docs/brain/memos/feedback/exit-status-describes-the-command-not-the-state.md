---
name: feedback-exit-status-describes-the-command-not-the-state
description: Four incidents in one night where a command exited 0 and the state was wrong. Assert the state after anything that changes it, never the command's output.
type: feedback
---

On 2026-09-22, five parallel sessions produced **four independent incidents of the same shape** in
about three hours. Every one exited 0.

1. **A `git push` printed success and the branch was not on the remote.** Found by comparing against
   `git ls-remote`; the push's own output gave no hint.
2. **Two suite runs reported cleanly over a tree that changed under them.** One session edited a spec
   file while a full suite was executing in the same worktree, then ran a targeted `rspec` against
   it — twice, an hour apart. A third session, checking on the strength of that report, found
   `spec/requests/client_picker_spec.rb` had been edited under its own run. That run finished
   **2805 examples, 0 failures** and was discarded. Nobody would have questioned that number.
3. **`git checkout -- <path>` silently destroyed uncommitted work.** It overwrites the working tree
   from the index with no confirmation and **no reflog entry**, so there is nothing to recover. A
   second session then realised it had run `git checkout -q origin/dev -- .` and `git checkout -q
   HEAD -- .` three times that day, and had survived only because it happened to have committed
   first.

**Why:** a command's exit status describes whether the command ran, not whether the world is now
what you wanted. The two diverge silently, and both readings look like success.

**How to apply — assert the state, and pick the predicate that survives:**

- **A push:** `git merge-base --is-ancestor <sha> origin/dev`. Not the push's output, and not
  `ls-remote` SHA-matching either — that one goes stale the moment the branch is deleted on merge,
  which is exactly when you most want to check. (See [[assert-ancestry-not-merge-output]].)
- **A suite or mutation run OWNS its worktree for its duration**, the way it owns its database.
  `git status --porcelain` empty before starting; `pgrep -fl rspec` before editing anything in a
  tree that might be busy. That second command also surfaces other sessions' runs and which database
  they hold, which nothing else reveals.
- **Never `git checkout -- <path>` to revert.** `git stash push -- <path>` is recoverable; checkout
  is not. **Reverting a mutation is exactly the moment people type the destructive command**,
  because it feels like undo.
- **Comparing runs: compare the LISTS, not the counts.** 1 failed → 1 failed hid four flakes
  disappearing in one case, and could equally hide one fixed and one newly broken.

**The generalisable half is the third incident, not the first two.** Two were caught because the
session remembered what it had just typed. One was caught because the session *looked* — and only
looking generalises, since it does not depend on suspecting yourself.

Related: [[gate-the-commit-on-the-check]], [[a-diagnostic-object-is-not-a-pass]],
[[a-watcher-that-cannot-see-a-dead-job]], [[an-unpushed-branch-in-a-scratch-worktree]],
[[a-ratchet-inherits-the-last-runs-state]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, exit-status-describes-the-command-not-the-state.md._

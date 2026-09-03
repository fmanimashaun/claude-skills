---
name: feedback-confirm-your-branch-not-just-your-repo
description: On claude-skills, another agent session can be working the SAME checkout — re-read `git branch --show-current` before every commit, not once at the start.
type: feedback
---

The `claude-skills` working directory is shared. A second session ran concurrently on
2026-08-20 and checked out `fix/attributes-interpolated-into-attribute-position` **underneath
me**, mid-task. My branch, my HEAD and my working tree all changed without any action of mine.

How it surfaced: `git log --oneline dev..HEAD` printed nothing for a branch I had just
committed two commits to, and `grep` could not find code I had verified minutes earlier. Both
looked like my own error. They were a different session's checkout.

**Why:** `git status --porcelain` showed the other session's modified files next to mine with
no marker distinguishing them, and my untracked `scripts/doctrine_map.py` was sitting in their
tree waiting to be swept into their commit. One `git add -A` on either side and the two changes
merge into one unreviewable commit under the wrong message. This already happened once in the
other direction: `assign_lanes.py` reached `dev` inside `4471e0c`, a commit about work orders,
undocumented and ungated, because it was in the tree when that commit was made.

**How to apply:** re-read `git branch --show-current` and `git rev-parse HEAD` immediately
before every commit and every push — treat them like a count, per
[[verify-counts-before-stating-them]]. When a second session is detected, do not `git checkout`
in the shared tree; take a worktree under `.claude/worktrees/<slice>` (gitignored, root-anchored)
and `mv` your untracked files into it, which also removes your footprint from theirs. Never
stage by directory or with `-A`; name every path.

Note that `guard-lane.sh` does **not** save you here: it is dormant unless `RAILS_FLOW_LANE` is
set, and an ad-hoc second session never sets it. The guard covers assigned lanes, not
accidental co-tenancy.

Related: [[verify-counts-before-stating-them]], [[assert-ancestry-not-merge-output]],
[[name-where-a-decision-landed]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, confirm-your-branch-not-just-your-repo.md._

# Session identity — the measurements behind §3a

`SKILL.md` §3a carries the rules and the two queries. This file carries the incidents they came from
and the boundary cases, so the body stays inside its context budget. Read it when a rule in §3a looks
arbitrary, or when you are about to widen one of the queries.

## `--author @me` is the account, measured

Every session on a machine commits and opens PRs as the same configured git user, so the author field
carries no session information at all.

Measured downstream: **five open PRs, one** belonging to the session that ran it.
A session filtering by it to find "its" PR adopts four it has never touched. The same figure was
reproduced independently by a second session on the same repository the following morning.

```bash
gh pr list --state open --author @me --limit 100   # every session's PRs, not yours
```

## Session names rotate and are reused

On one day: a session reported it *"was `<name-A>` last session; a different session holds that name
now"*, and another was **renamed while running** — it filed five issues signed with one name and an
hour later was listed under another, the same session throughout.

A remembered name, and a sign-off on an issue, may both name somebody else by the time you read them.

## Why `--git-dir` and not the `worktrees/*` glob

Verified by running both in one worktree while a second held its own branch: the glob returned the
peer's branch, `--git-dir` did not. The glob answers *what has any session held* — the very question
you are trying not to ask when you ask "is this mine".

The `Branch: renamed` alternation matters too. A plain `moving from` grep answers *what did this
check out* and silently drops any branch that arrived by `git branch -m`.

**And the glob is not the answer to "whose is it" either**, which is the natural next reach once the
narrow version says only *not mine*. With `grep -o` the filename is gone; with `grep -H` the path
component is the **worktree's directory name** (`wt-1157`), chosen by whoever created the lane, and it
maps to no session. It tells you a branch was held somewhere, not by whom.

## The worktree listing, and why its boundary is not hypothetical

Measured on one repository at one moment: **11 worktree rows across three sessions plus the shared
checkout**, distributed **5 / 3 / 2 / 1**. Two findings from that single listing:

**A live branch with an open PR had no row.** `qa/528-applicant-pipeline-evidence` appeared in none of
the 11 rows while carrying four commits and open PR #559. Its scratchpad worktree had disappeared at a
date rollover — the failure §5a exists for. A reader applying the method without its boundary would
have concluded nobody was on it and picked it up. This is the case that matters: merged-and-deleted
branches and exited sessions also leave no row, but that work is finished; this was not.

**The shared checkout held the most consequential branch in the repository** —
`integration/collate-5-prs` — and the rule correctly declines to attribute it. That is the rule
working rather than failing, and it is the clearest example of why the shared row must be reported as
unowned rather than attributed to whoever is currently on its HEAD. That HEAD moved between two of one
session's commands while it was reading the listing.

## Parse `--porcelain` as records

`git worktree list --porcelain` emits **blank-line-separated records**. The first draft of the §3a
snippet was `awk` and printed exactly **one row** — which looks like a complete answer in a repository
with one worktree, and is a confident wrong answer in one with eleven. Its author caught it before
sending.

This is §3's prefix-as-the-whole defect arriving *inside the tool built to settle ownership*, which is
why the warning sits beside the code in `SKILL.md` rather than being left to the general rule.

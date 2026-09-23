# Reading a list — the incidents behind §3's set-question rule

`SKILL.md` §3 carries the rule and the commands. This file carries the five incidents and the
measurement that rejected a lint for them, so the body stays inside its context budget.

## The five, in two days, across three sessions

Every one produced a confident, reproducible, wrong claim.

| what was read | over | what was claimed |
|---|---|---|
| `tail -80` | a 31-stage CI run | "7 green, 1 red" while **8** stages were dying |
| return-on-first-match | 43 findings | **4** reported as the total |
| `--date=%H:%M` | a two-day window | a commit attributed to the wrong day and session |
| `head -12` | 46 commits | "my PR is not in the collation branch" — it was |
| a regex on `in [0-9.]+s` | a 32-stage list | a stage silently absent because its duration read `4m43.21s` |

A sixth, later the same week and inside the tooling: a PR-check poller waited on
`PENDING|IN_PROGRESS` and exited early, because `gh pr checks` also returns **`QUEUED`**. Enumerating
the states you are waiting for is the same defect as reading a prefix — poll on the **terminal**
states instead, and let anything unrecognised keep you waiting.

## Why a lint on `| head` / `| tail` was rejected

Every such construct in the shipped corpus was checked, and re-measured on the day the rule shipped:

```
grep -rnE '\|[[:space:]]*(head|tail)[[:space:]]+-' --include='*.md' skills/ plugins/   ->  7
```

| where | construct | verdict |
|---|---|---|
| `parallel-session-lane/SKILL.md` | `sort -u \| tail -1` | **maximum** of decision numbers — correct |
| `parallel-session-lane/SKILL.md` | `sort -u \| tail -3` | recent migrations, a display — correct |
| `design-flow/commands/audit.md` ×2 | `lsof -t \| head -1` | *the* single listener, single cwd — correct |
| `qa-flow/commands/smoke.md` ×2 | `lsof -t \| head -1` | same — correct |
| `rails-flow/commands/brain-sync.md` | `base64 -d \| tail -20` | recent events — correct |

**Seven instances, seven legitimate, zero true positives.** And none of the five defects above is in
shipped shell at all — they are in how a session interrogates a repository at the moment it forms a
belief. No regex separates `sort | tail -1` (a maximum) from `git log | head -12` (a truncation), and
a check that is wrong on every instance it fires is one that gets switched off.

## Why the rule is keyed to the question and not the command

A session hit this, wrote the rule down as *"for a run's verdict, print every stage and count them"* —
and **it did not fire the next day**, when the list was git commits rather than CI stages.

The rule was right and scoped to the wrong noun. A rule scoped to where you last met a bug does not
generalise to where you meet it next, and **its author is the least likely person to notice**, because
they remember it as being about the idea rather than about the instance.

## Two git answers that are not measurements

**`--is-ancestor` answers "is this commit in that branch", not "did this PR merge".** After a squash
merge -- which is how many repositories land a feature branch, `gh pr merge --squash` included -- the
branch's own commits are never ancestors of the base, so the test returns 1 for a PR that merged.
Before deleting a branch, ask the PR (`gh pr view <n> --json state,mergeCommit`) or compare content
(`git diff --quiet origin/<base> <branch> -- <the paths it changed>`), never ancestry alone.

**A zero from a pattern that could not match is not a zero.** `git grep -E` uses POSIX extended
regex, where `\b` is undefined: on macOS `git grep -nE '\bfoo\b'` matches nothing and exits 1 --
indistinguishable from "not found" -- on a file that contains `foo`. Use `git grep -w foo` or
`git grep -P '\bfoo\b'`. Pair any negative with a control that must match on the same input.

## The stash list is shared

**The stash list is one per repository, not one per worktree.** `refs/stash` lives in the common git
directory, so every worktree -- and every session -- sees and can drop the same entries, and a bare
`git stash pop` or `git stash drop` takes whichever entry is on top, which may be a peer's. Name the
entry: list with `git stash list --format='%gd|%gs'`, find yours by its message, and drop it by that
ref. Do not select one with `git stash list -n1 'stash@{N}'`: once the stash list holds entries made
on more than one branch -- the parallel-worktree case -- it ignores the ref and prints the top entry.
To undo one file, `git restore -- <path>` needs no stash at all.

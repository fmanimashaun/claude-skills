---
name: parallel-session-lane
description: Operating protocol for working as one of several agent sessions running against the same repository at once — confirm your worktree, scope to one coherent slice, stay inside your assigned subtree, and review your own diff before the PR. Use when a prompt says you are one of N parallel sessions, assigns you a worktree or a directory lane, or hands you a list of issues that other sessions are also splitting.
---

# Parallel session lane

Several agent sessions may run against one repository at the same time. Every step below
exists to keep their HEADs, indexes, and diffs from colliding. Each rule was written after
the collision it prevents actually happened.

## 1. Confirm your worktree before any edit

- Work **only** inside the worktree you were assigned.
- Never work in the **primary checkout** — the clone `git worktree list` prints first, without a
  `[branch]` of its own to spare. Another session occupies it. Resolve it rather than hardcoding
  a path: an absolute home directory is wrong on every machine but one.
- Verify before editing:

  ```bash
  git rev-parse --show-toplevel   # where am I?
  git worktree list               # which one is the primary?
  ```

  If the toplevel is the primary checkout, move to your own worktree first.
- Why this is strict: **one directory means one HEAD and one index.** When this was ignored, a PR
  merged against the wrong branch and one session's uncommitted work rode onto another session's
  release branch.
- If the prompt does not clearly say which worktree is yours, **ask instead of guessing.**

## 2. Read the repository's agent instructions first

Read `CLAUDE.md` (and anything it imports, such as an `AGENTS.md`) in **your** worktree before
starting work, and follow it exactly. A sibling worktree's copy may be a different commit.

## 3. Take ONE coherent slice, not the whole list

- You may be handed several issues. Do not attempt the whole list.
- Group issues only when they share a **mechanism** *and* touch the **same files**. Anything
  else is a separate slice for a separate PR.
- State in the PR which assigned issues you deliberately left out, so they are not assumed done.

## 4. Stay in your lane

- Edit only the subtree you were assigned — one component, one package, one plugin directory.
- Do **not** edit shared or generated paths: build output, lockfiles, vendored artifacts, or
  another session's subtree.
- **Reading shared paths is fine; editing them is not.**
- If a candidate change cannot be made inside your lane, prefer to drop it from the slice. If you
  must touch a shared path, expect contention and call it out explicitly in the PR description.
- No drive-by fixes outside your lane, however obvious they look. The obvious ones are exactly
  what another session is already mid-way through.

## 5. Review your own diff before opening the PR

Apply your repository's review doctrine to your own diff **before** opening the PR, not after.
A parallel run multiplies the cost of a review round-trip: while your PR sits waiting, the
branches around it keep moving.

## 6. Do not clean up what you did not create

Worktrees, branches, and stashes that look abandoned usually belong to a live session. An
"idle" heuristic once deleted three worktrees that were in active use. If something looks
stale, say so; do not remove it.

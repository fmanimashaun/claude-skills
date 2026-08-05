---
name: parallel-session-lane
description: Operating protocol for working as one of several parallel sessions in this repo — confirm your worktree, scope to one coherent slice, stay inside your plugin lane, and review your own diff before the PR. Use when a prompt says you are one of N parallel sessions, assigns you a worktree (e.g. `cd ../cs-qa`) or a plugin lane (`plugins/<yours>/**`), or hands you a list of issues that other sessions are also splitting.
---

# Parallel session lane

Several sessions may run against this repo at the same time. Every step below exists
to keep their HEADs, indexes, and diffs from colliding.

## 1. Confirm your worktree before any edit

- Work **only** inside the worktree you were assigned (e.g. `cd ../cs-qa`, `cd ../cs-rf`).
- Never work in the **primary checkout** — the clone `git worktree list` prints first, without a
  `[branch]` of its own to spare. Another session occupies it. Resolve it rather than hardcoding
  a path: an absolute home directory is wrong on every machine but one, and this repo's whole
  onboarding story is a fresh clone somewhere else.
- Verify before editing: `git rev-parse --show-toplevel` and `git worktree list`. If the toplevel is the primary checkout, move to your own worktree first.
- Why this is strict: one directory means one HEAD and one index. Last time this was ignored, a PR merged against the wrong branch and one session's uncommitted work rode onto another session's release branch.
- If the prompt does not clearly say which worktree is yours, ask instead of guessing.

## 2. Read CLAUDE.md first

Read `CLAUDE.md` in your worktree before starting work and follow it exactly.

## 3. Take ONE coherent slice, not the whole list

- You may be handed several issues (e.g. `#126, #127, #130`). Do not attempt the whole list.
- Group issues only when they share a **mechanism** *and* touch the **same files**. Anything else is a separate slice for a separate PR.
- State in the PR which assigned issues you deliberately left out, so they are not assumed done.

## 4. Stay in your lane

- Edit `plugins/<yours>/**` **exclusively**.
- Do **not** edit `skills/**`, `dist/**`, or another session's plugin — those are shared and are not yours this session.
- Reading shared paths is fine; editing them is not.
- If a candidate change cannot be made inside your lane, prefer to drop it from the slice. If you must touch a shared path, expect contention with the other sessions and call it out explicitly in the PR description.
- No drive-by fixes outside your lane, however obvious they look.

## 5. Review your own diff before opening the PR

Read `skills/code-review/SKILL.md` and apply that review process to your own diff.
Do this before opening the PR, not after.

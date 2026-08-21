---
name: parallel-session-lane
description: Operating protocol for working as one of several agent sessions running against the same repository at once — confirm your worktree, scope to one coherent slice, stay inside your assigned subtree, and review your own diff before the PR. Use when a prompt says you are one of N parallel sessions, assigns you a worktree or a directory lane, or hands you a list of issues that other sessions are also splitting.
---

# Parallel session lane

Several agent sessions may run against one repository at the same time. Every step below
exists to keep their HEADs, indexes, and diffs from colliding. Each rule was written after
the collision it prevents actually happened.

## 0. Getting into this mode

Until #661 a human opened N terminals and assigned lanes by hand — this skill described a mode
nothing could put you in. `rails-flow` now ships an assigner:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assign_lanes.py" app/models app/controllers --budget-usd 6
```

It prints the `git worktree add` per lane and the session command with `RAILS_FLOW_LANE` set. It
**refuses** overlapping lanes, a single lane, a dirty tree, and a missing lane guard.

**It prepares; it does not spawn.** Creating a worktree is mechanical and deciding when an agent
starts is not, so it prints the commands rather than running them.

**No tmux and no daemon**, deliberately. `swarm-forge` needs message passing because its roles cannot
see each other's state; ours can — `compose_state.py` derives the driver's state *from the
repository* and a work order is a committed file. Git is the handoff medium and it survives a reboot,
which a tmux session does not.

**You will be told when you need this.** (#723) Until now activation was entirely on a human
remembering to run the assigner *before* opening the sessions — so the protocol shipped and stayed
dormant, and four unlaned sessions in one directory did exactly what it exists to prevent: one
session's branch switch moved another's HEAD mid-work, uncommitted work from several piled into one
tree, and the Stop gate failed one session's turn over **another** session's red specs. `rails-flow`'s
SessionStart hook now detects sibling live sessions sharing this working directory with no
`RAILS_FLOW_LANE` set, and says so. It **under-detects deliberately** — a false nudge on ordinary
single-session work is how an advisory gets ignored, and this exists because an unheeded advisory is
worth nothing.

**Spend is reported, never enforced.** N sessions is N times the cost, and this script cannot see a
provider balance — a cap it could not honour would be a promise nothing keeps.

## 1. Confirm your worktree before any edit

**This is enforced now, when a lane is assigned.** `rails-flow` ships a `PreToolUse` hook that
refuses a **write** outside the lane in `RAILS_FLOW_LANE`. Until it existed, §1 was advice: a session
that skipped it produced a clean-looking branch in the wrong worktree, silently, while another
session was working there — and nothing said so until a human read a diff that did not belong.

Three properties, each deliberate:

- **Dormant with no lane assigned.** No `RAILS_FLOW_LANE`, no opinion — a single-session run must not
  pay for a multi-session feature, and a guard that fired on ordinary work would be switched off.
- **Writes only.** §2 also says do not diff other branches; refusing *reads* would break legitimate
  context-gathering, and that over-reach is how a hook gets disabled.
- **Fails closed.** With `python3` missing it scans the raw payload, so the path still matches.

If the lane is wrong, change it deliberately. **Do not widen it to make one write pass** — that is
the same move as adding a carve-out to silence a gate.


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

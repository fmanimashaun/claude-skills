---
name: parallel-session-lane
description: Operating protocol for working as one of several agent sessions against the same repository at once — take your own worktree and test database, announce the FILE PATHS you are about to touch, query git for claimed decision numbers and migration timestamps rather than asking a peer, and copy the gitignored files a fresh worktree lacks before trusting any test result. Use when a prompt says you are one of N parallel sessions, when another session is live in the same repository, when you are handed a list of issues others are splitting, or when you are about to write into a shared checkout.
---

<!-- GENERATED from skills/parallel-session-lane/SKILL.md by scripts/build_maintainer_skills.py — do not edit.
     The shipped skill is the source of truth; this copy exists because this repository's
     own sessions do not load `rails-stack`, so the doctrine would otherwise reach every
     consumer except its maintainers. Edit the source and re-run the script. -->

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

**No tmux and no daemon** — but "no message passing" was too strong, and four sessions disproved it
in a day. Git is the right medium for a **handoff of work**: a work order is a committed file,
`compose_state.py` derives the driver's state from the repository, and both survive a reboot. Git is
the wrong medium for two other things, and sessions that had only git invented a channel within the
hour:

- **A fact about shared ground.** `dev` is red; the branch you are about to measure against is
  broken. Nothing commits that, and a session that does not hear it spends an afternoon attributing
  someone else's failures to its own diff. It happened twice in one morning.
- **A claim that has not been written yet.** Not the claim itself — see
  [§3](#3-claims-live-in-git-query-them-rather-than-asking-a-peer) — but the intent to take one, and
  the answer to "am I about to edit the file you are in". Paths collide; issue numbers do not
  predict it.

So: **git for work, messages for facts, and this skill for the protocol.** Prefer whatever direct
channel the harness gives you (Claude Code sessions have one) over a shared file. Three sessions
appending to one file is the collision this skill exists to prevent, reproduced in the coordination
layer.

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

## 1. One worktree per unit of work — before lanes, and without asking anyone

**This is the rule that four unlaned sessions reached on their own**, and it is more important than
the lane machinery above because it needs no assigner, no environment variable and nobody
remembering to run a script first. Measured on one repository in one day: **19 worktrees**, one
branch each, under per-session scratchpad directories.

```bash
git worktree add -b fix/the-thing "$SCRATCH/repo-thing" origin/dev
```

Three properties come with it, and each was paid for:

- **A private test database.** `createdb myapp_test_<you>`, or `DATABASE_URL` pointed at one, so a
  suite that truncates tables cannot empty another session's fixtures mid-run.
- **A distinctive scratchpad path.** One agent had its `pr-body.md` overwritten mid-task by another
  writing to the same shared temp path.
- **Gitignored files do not come with you.** See
  [§5](#5-a-fresh-worktree-is-missing-every-gitignored-file-and-the-suite-blames-something-else).

**Never `git worktree remove --force` without checking for uncommitted work.** A session destroyed a
finished fix that way and rewrote it from memory.

## 2. Say four things, unprompted

Not a status report — four moments where silence costs somebody else real time:

1. **Before starting**, with your **worktree path, branch, and the FILE PATHS you expect to touch.**
   Not the issue number: every near-miss in the day this was written was a path collision that no
   issue number predicted. Two issues can be entirely separate concerns and land in the same
   declaration list.
2. **When you touch something outside what you announced** — before you push, not after.
3. **The moment you learn something that changes someone else's ground**: a red `dev`, a merged PR
   that moves a file they said they were in, a premise in an issue that does not reproduce.
4. **When you merge**, saying what moved.

**Correct a peer's stale fact when you find one, and say how you measured.** Two sessions reported a
CI failure set that a later merge had already fixed; a third reported five uncommitted files that
had been committed an hour earlier. Both were acted on before being corrected. A measurement carries
its command; a recollection does not.

## 3. Claims live in git — query them rather than asking a peer

Shared namespaces — decision-record numbers, migration timestamps, anything numbered that several
branches append to — do **not** need a registry, a lock file or a message. They are already in git,
on branches everyone has pushed. What was missing was the query.

```bash
# The highest decision number anyone has taken, merged or not.
git fetch --all
git grep -ho "D-0[0-9][0-9]" $(git for-each-ref --format='%(refname)' refs/remotes/origin) \
  -- docs/brain/DECISIONS.md | sort -u | tail -1

# The same question for migration timestamps.
git ls-tree -r --name-only $(git for-each-ref --format='%(refname)' refs/remotes/origin) \
  -- db/migrate | sed 's|.*/||' | cut -d_ -f1 | sort -u | tail -3
```

**Why a query and not a file.** The sessions that wrote this were coordinating by hand and believed
*"the highest merged is D-073; two branches hold D-075 and D-076 unmerged."* The query above
answered **D-079, all of them already merged** — four numbers stale, inside a day. A registry file
would have drifted identically, because it needs somebody to update it; git did not, because every
branch that takes a number writes it into the file the query reads.

**`git ls-remote` is the wrong tool and that is why this looked impossible.** A decision number lives
*inside* a file, not in a branch name. The premise "git cannot see an unpushed worktree" was true and
irrelevant: measured across those 19 worktrees, **18 of 19 branches were already pushed.**

## 4. Confirm your worktree before any edit

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
  git branch --show-current       # whose branch am I standing on?
  git worktree list               # which one is the primary?
  ```

  If the toplevel is the primary checkout, move to your own worktree first.
- Why this is strict: **one directory means one HEAD and one index.** When this was ignored, a PR
  merged against the wrong branch and one session's uncommitted work rode onto another session's
  release branch.
- If the prompt does not clearly say which worktree is yours, **ask instead of guessing.**

### An uncommitted edit has no author, so commit early — even a WIP

`git status` prints ` M path` and `?? path` with **no indication of who wrote them**. In a shared
checkout the only reading available to whoever looks is *"mine"*, and that reading is wrong exactly
when it is most expensive. This is not hypothetical and it is not rare: **two sessions made the same
wrong call within four minutes of each other**, in opposite directions, over the same file.

- One session arrived on a branch a peer had pushed, read its open PR as its own to finish, and
  **merged it** before the author's message arrived.
- The other read ` M scripts/build_maintainer_skills.py` in that checkout and **announced it as its
  own work** to the session that was mid-write on it.

Neither session did anything careless. §2 does not prevent it either, because **the announcement and
the dirty file are in different media** — you cannot see a claim about paths when you are looking at
a working tree.

So:

- **Commit early, even a WIP**, in any tree another session can see. A commit has an author, a
  timestamp and a message; `git log` and `git blame` answer *"whose is this"* and ` M` never will.
  Push it, and [§3](#3-claims-live-in-git-query-them-rather-than-asking-a-peer) can see it too.
- **Read the branch line before the paths.** A startup status snapshot puts the branch above the
  file list, and a branch *you did not create* is proof a peer is in the tree. Both sessions above
  had that line in front of them, and both read the paths first.
- **A status snapshot is a measurement with a timestamp, not a standing fact.** Handed to you at
  startup, it describes the tree as it was; four minutes later it is a claim about the past. Re-run
  `git status` rather than trusting the copy you were given.
- **Settle ownership from the timeline, not from confidence** — yours or a peer's. `git reflog
  --date=iso` dates every checkout and commit, and `stat` dates the file. A write that lands after a
  checkout you did not make, in a session that has written nothing, is not yours. Two commands beat
  an argument, and they work from either side.
- **A green, mergeable PR says the code is ready — not that the work is yours to close out.** Every
  merge checklist says "merge on green" and none of them has a clause for a PR another session
  opened. Ask its author session first; the merge is the one step that cannot be taken back quietly.

### A long-running read is a second party in your own tree

Everything above is about two sessions. **The single-session case reads identically and nobody
announces it:** a gate sweep, a full suite or a corpus build takes minutes, and for those minutes it
is a reader with a stake in the tree staying still.

Measured: a 475-second gate sweep started in the primary checkout, while the same session then
checked out another branch, rebased a release commit onto a moved `dev`, created a third branch and
edited four files. It reported **one failure** where a run minutes earlier had reported none. That
number describes **no commit** — none was on disk for the duration — and both outcomes were bad:
green and meaningless, or red and an hour spent chasing a file that had already changed.

- **Run it against a commit, not against a directory.** `git worktree add --detach "$SCRATCH/sweep"
  <the commit you mean>` — then the number belongs to something, and nothing you do meanwhile can
  touch it.
- **If you did edit the tree under a run, throw the result away.** It is not a slow answer; it is no
  answer. Re-run it somewhere stable rather than interpreting it.
- **A detached worktree is missing every gitignored input**, so link them in before you trust it —
  see [§5](#5-a-fresh-worktree-is-missing-every-gitignored-file-and-the-suite-blames-something-else).
  A sweep that skips the one gate needing licensed corpora is not a greener sweep, it is a blinder
  one, and CI cannot run that gate at all.
- **A timeout is not a failure of the thing measured.** Under N sessions a suite that fits its budget
  on a quiet runner will not fit on the laptop running them, and the gate reports FAIL either way.
  Re-run the checker alone before believing it, and **do not raise the budget to make a loaded
  machine green** — the number is a property of the machine the gate is judged on.

## 5. A fresh worktree is missing every gitignored file, and the suite blames something else

A worktree is a clean checkout: **nothing gitignored comes with it.** Neither failure below names its
cause, and both were diagnosed as application defects first.

- **Built assets.** `app/assets/builds/` is gitignored, so system specs render an unstyled page and
  fail **as geometry** — a button "not visible", a modal without its gutter. Caught four sessions six
  times in one day, and once in a fully set-up main checkout where a server had been restarted
  without its CSS watcher. Build the assets whenever you are not certain a watcher is running.
- **The credentials key.** `config/master.key` is gitignored, so encrypted credentials cannot be
  decrypted, no OmniAuth strategy registers, and every sign-in silently lands on a signed-out page.
  Measured: **948 of 2,422 examples red**, all of them the same cause.

**And the second one has a trap inside the trap.** Through all 948 failures, that repository's
`spec/system` suite was **fully green** — because system specs signed in through a magic-link route
while request specs used a helper that needs the decrypted credentials. "The browser tests pass" is
exactly the evidence somebody would cite to conclude authentication works, and in that state it is
evidence of nothing.

**So: copy the gitignored files your suite needs into a new worktree before you trust a single
result, and make the suite refuse rather than mis-measure** — a `before(:suite)` check that aborts
naming the command beats a hundred individually-diagnosed failures. Check for *stale* as well as
missing: the worst incident had the file present and out of date.

## 6. Read the repository's agent instructions first

Read `CLAUDE.md` (and anything it imports, such as an `AGENTS.md`) in **your** worktree before
starting work, and follow it exactly. A sibling worktree's copy may be a different commit.

## 7. Take ONE coherent slice, not the whole list

- You may be handed several issues. Do not attempt the whole list.
- Group issues only when they share a **mechanism** *and* touch the **same files**. Anything
  else is a separate slice for a separate PR.
- State in the PR which assigned issues you deliberately left out, so they are not assumed done.

## 8. Stay in your lane

- Edit only the subtree you were assigned — one component, one package, one plugin directory.
- Do **not** edit shared or generated paths: build output, lockfiles, vendored artifacts, or
  another session's subtree.
- **Reading shared paths is fine; editing them is not.**
- If a candidate change cannot be made inside your lane, prefer to drop it from the slice. If you
  must touch a shared path, expect contention and call it out explicitly in the PR description.
- No drive-by fixes outside your lane, however obvious they look. The obvious ones are exactly
  what another session is already mid-way through.

## 9. Review your own diff before opening the PR

Apply your repository's review doctrine to your own diff **before** opening the PR, not after.
A parallel run multiplies the cost of a review round-trip: while your PR sits waiting, the
branches around it keep moving.

## 10. Do not clean up what you did not create

Worktrees, branches, and stashes that look abandoned usually belong to a live session. An
"idle" heuristic once deleted three worktrees that were in active use. If something looks
stale, say so; do not remove it.

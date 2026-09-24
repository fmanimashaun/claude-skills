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

- **THREE isolated resources, not one.** A private test database is the one people think of, and on
  its own it leaves two of the three failures in place. Measured on one repository with six sessions
  in a day: three distinct cross-session corruptions, and **every one of them first presented as a
  defect in the code under test** (#1078).

  1. **An isolated TEST database** — `myapp_test_<lane>`, so a suite that truncates tables cannot
     empty another session's fixtures. Without it: `PG::TRDeadlockDetected` with the blocking PID
     belonging to another session, and the loser sees `PG::UniqueViolation` from a seed in a
     `before` hook. It reads as a broken seed.
  2. **An isolated DEVELOPMENT database** — for whatever mints fixtures and serves a browser. Without
     it: rows destroyed between load and use, surfacing as `ActiveRecord::InvalidForeignKey` inside a
     rake task. It reads as a broken task.
  3. **A port of its own, and a refusal to adopt a server it did not start.** *"Reusing the server
     already answering on 3001"* is a sensible optimisation that becomes a cross-session corruption
     the moment there are N sessions: the browser runs against another worktree's code, against a
     third session's database. `/qa-flow:smoke` §2 now resolves the listener's working directory and
     **refuses** a stranger; `crawl`, `walkthrough` and `/design-flow:audit` delegate to it.

  **Set it in config, not with `DATABASE_URL`.** That variable is the obvious lever and it is the
  wrong one: it names **one** database while a lane needs two, and a value set to isolate the *test*
  database is inherited by any browser step that boots a *development* server — measured as 12
  browser failures inside a CI run and 182 standalone, neither of them about the code. Per-lane names
  belong in `config/database.yml`, where the environment picks the right one.
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

## 2a. Each session merges its own work; the coordinator and QA measure what landed

**The author lands their own PR.** They know when it is done, and a queue in front of one session is
the slowest part of a parallel run — measured on one repository in a day: **eighteen merges through a
single session**, with two authors idle at one point holding green, finished work.

**Both alternatives were tried on the same day and this is the one that survived.** Routing every
merge through one session produced the stall above. Leaving it unstated produced the opposite failure:
a session merged a peer's green PR before its author's message arrived. **Neither is fixed by a rule
about who is senior. It is fixed by saying that the author merges, and that somebody measures after.**

**What the author inherits with the merge, and it is the whole of it:**

1. **Rebase onto the current integration branch and CONFIRM it** — `git merge-base --is-ancestor
   origin/<base> HEAD` — rather than assuming the base has not moved. *The last session to measure is
   not the last session to change the base.*
2. **Re-run the suite on the rebased head**, not on the head measured earlier. A green number from a
   base that no longer exists is not evidence about the base that does.
3. **Run the gates the change can touch, not just the ones that are quick.** One merge went in on
   seven lint gates and not the architecture graph, and drifted the branch; the same omission
   repeated two merges later.
4. **Announce what you merged** (§2.4), especially when it moves a file a peer announced.

**And the standing prohibition is unchanged: do not merge a PR you did not open.** §4's last bullet
is the rule — ask its author session first. "Merge on green" has no clause for somebody else's work.

**Measurement is a SEPARATE job from permission, and this is the part teams get wrong.** The
coordinator and QA do not stand in front of the merge; they measure the integration branch *after*
it, and every finding says **new at this merge** or **pre-existing**. Without that attribution it is
noise — three sessions in one day lost time attributing inherited failures to their own diffs. With
it, it is the only signal that tells an author whether they broke something.

**A branch's own green run is not a measurement of the branch it lands on.** Integration is where the
interesting failures live: on that same day the integration branch went red five times, and **not one
was found by the merge that caused it** — every one surfaced later, from a session running something
for an unrelated reason.

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

### A set question is never answered by reading a list

The queries above are shaped the way they are for a second reason. **"Is X in Y", "how many", "is
that all" are questions about a set, and a prefix of some output is not an answer to any of them.**
**Six sessions in two days** each read a truncated list and reported the prefix as the whole — every
one a confident, reproducible, wrong claim. So ask with a predicate or a count, never with a prefix:

```bash
git merge-base --is-ancestor "$SHA" "$BRANCH"    # not: git log | head -12
grep -c pattern file                              # not: grep pattern file | head
gh api "$ENDPOINT" --jq '[.[] | select(.sha | startswith($x))] | length'
```

When you must *show* a list, **print the total beside it**: `… | head -20; echo "of $(… | wc -l)"`.
When you **poll**, wait on the terminal states rather than enumerating the pending ones — a watcher
listing `PENDING|IN_PROGRESS` exits early on a `QUEUED` row it never named.

**Two git answers that look like measurements and are not** — `--is-ancestor` after a squash merge,
and `git grep -E '\b…'` on macOS — are in [`references/reading-a-list.md`](references/reading-a-list.md#two-git-answers-that-are-not-measurements).

**The trigger is the shape of the question, not the shape of the command**, and that distinction is
load-bearing: one of the six had written this rule down the day before, scoped to CI stages, and it
did not fire when the next list was git commits. **A lint on `| head` / `| tail` was considered and
rejected on measurement** — 7 instances in the shipped corpus, 7 legitimate, 0 true positives, and
none of the six defects is in shipped shell at all. The incidents, the corpus table and the
generalisation failure: [`references/reading-a-list.md`](references/reading-a-list.md).

**Why a query and not a file.** The sessions that wrote this were coordinating by hand and believed
*"the highest merged is D-073; two branches hold D-075 and D-076 unmerged."* The query above
answered **D-079, all of them already merged** — four numbers stale, inside a day. A registry file
would have drifted identically, because it needs somebody to update it; git did not, because every
branch that takes a number writes it into the file the query reads.

**`git ls-remote` is the wrong tool and that is why this looked impossible.** A decision number lives
*inside* a file, not in a branch name. The premise "git cannot see an unpushed worktree" was true and
irrelevant: measured across those 19 worktrees, **18 of 19 branches were already pushed.**

**Read that number the other way round as well.** It is reassuring for *this* query and alarming for
the branch it excludes: the 1 in 19 is precisely the branch that can be lost, because it is the one
with a single copy. On a machine running many sessions a day, 1 in 19 is not rare — see §5a.

## 3a. "Is this mine?" and "whose is it?" — two questions, two queries

§3 answers *has this number been claimed*. The questions that follow from a lane — a private worktree,
a private database, a private port — are **which of the things on this machine are mine**, and then
**whose is this one**. A session that has to invent either answer invents a wrong one.

**Neither obvious identifier works.** `--author @me` is the **account**: every session commits as the
same configured git user, measured at five open PRs of which one belonged to the session that ran it.
**Session names rotate and are reused**, including mid-session — a remembered name may denote somebody
else by the time you read it. And **a first-person handoff is not yours**: a resumed-session summary
written in *"I shipped #1162"* voice is usually keyed to the **project directory**, so every session
here reads and overwrites the same one. It means *somebody in this directory* shipped it. Detail and
incidents: [`references/session-identity.md`](references/session-identity.md).

**"Is it mine?" — ask this worktree's own reflog.**

```bash
# Every branch THIS worktree has held, including ones that arrived by rename.
grep -oE "moving from [^ ]+ to [^ ]+|Branch: renamed [^ ]+ to [^ ]+" "$(git rev-parse --git-dir)/logs/HEAD" \
  | awk '{print $NF}' | sed 's#^refs/heads/##' | sort -u
```

**`--git-dir`, not the `--git-common-dir/worktrees/*` glob** — the glob reads every worktree and
answers *what has any session held*, which is the question you are trying not to ask. Keep the
`Branch: renamed` alternation or branches acquired by `git branch -m` vanish silently.

**"Whose is it?" — the reflog cannot say.** It eliminates; it never identifies, and a negative leaves
nothing to act on but asking around. A lane worktree's **path carries its owning session's id**, so:

```bash
git worktree list --porcelain > /tmp/wt.txt
python3 - <<'PY'
rows, cur = [], {}
for line in open('/tmp/wt.txt'):
    line = line.rstrip('\n')
    if not line:                       # BLANK-LINE-SEPARATED RECORDS, not lines --
        if cur: rows.append(cur); cur = {}   # a line filter reads the first and stops
        continue
    k, _, v = line.partition(' ')
    cur[k] = v
if cur: rows.append(cur)
for r in rows:
    path = r.get('worktree', '')
    branch = r.get('branch', '(detached)').replace('refs/heads/', '')
    parts = path.split('/')
    sid = parts[5] if '/scratchpad/' in path and len(parts) > 5 else None
    print(f"  {branch:34} {'session ' + sid if sid else 'SHARED checkout (no single owner)'}")
PY
```

Compare a printed id against your own scratchpad path and you have the holder, with no round trip.

**It answers exactly one question: which session has this branch checked out in a live worktree right
now** — not who is working on it, and not who authored it. Four boundaries, and it misleads past them:

- **NO ROW DOES NOT MEAN NO OWNER, and the dangerous case is live work.** A branch whose worktree
  disappeared (§5a) keeps its commits and its PR and loses its row. Measured: across 11 rows, a branch
  with four commits and an **open PR** appeared in none of them. Merged-and-deleted branches and
  exited sessions also leave no row, but that work is over; this was not.
- **The mapping is one-to-many** — in that listing, 5 / 3 / 2 worktrees across three sessions.
- **The shared checkout has no owner.** Never attribute it to whoever is on its HEAD; that HEAD moves,
  and it moved mid-listing.
- **A `(detached)` row is a rebase in progress**, not an unowned branch — the one state in which
  interrupting is least welcome.

**With no row there is no fallback: ask, and say which branch you mean.** The branch name routes to an
*issue*, not a session, and the PR author is the shared account.

**Where this bites: merge by NUMBER.** Never merge from an author-filtered list, and **never merge a
branch this listing says is somebody else's** — green is a statement about the code, not about whether
its owner is finished with it. A wrong pick under `gh pr merge --admin` is unrecoverable rather than
embarrassing, and `--admin` is exactly the case where no CI run is left to catch it.

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
- **Push at the commit, not at the PR — the reason is durability, not discovery.** A branch that has
  only ever been committed lives in exactly one place: a ref in the primary checkout's `.git`, with
  a working copy in a scratch directory that can vanish (§5a). Letting
  [§3](#3-claims-live-in-git-query-them-rather-than-asking-a-peer) see your work is the lesser
  benefit, and framing it that way invites the reasonable conclusion that work not worth announcing
  yet need not be pushed yet. It does. No draft PR is required and no peer has to look.
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

A worktree is a clean checkout: **nothing gitignored comes with it.** Neither failure below names its cause; both were first diagnosed as application defects.

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

## 5a. Your worktree can disappear, and the two outcomes look identical

A lane lives in a scratch directory, and a scratch directory is something another process may clean
up. Sessions have resumed to find the path simply not there. What happens next depends entirely on
one thing — whether the branch was ever pushed — and **the recovery command succeeds either way**,
so you must find out before you run it.

**Discriminate first. Two commands, from the primary checkout:**

```bash
git worktree list                     # the lost lane shows as `prunable`
git log --oneline -1 <your-branch>    # PRINTS -> the commits live; SILENT -> there is nothing there
```

The second is the whole question. A worktree directory is a working copy; the branch ref lives in the
common `.git`, so it usually outlives the directory. If `git log` prints, the work is intact.

**Then recover, and push before anything else:**

```bash
git worktree prune
git worktree add "$SCRATCH/<lane>" <your-branch>
git push -u origin <your-branch>      # FIRST, before a single edit or test run
```

**Why the order is not negotiable: `prune` followed by `add` on a branch with no commits produces a
clean, empty worktree that looks exactly like success.** There is no error, no warning, and the
directory is there with the right branch checked out. Run `git log` before `prune`, not after — after
`prune` you are reading the same silence with one fewer explanation for it.

**A recovered worktree is a fresh worktree, so §5 applies again — and it is harder to notice here.**
Everything tracked is correct, the branch is right, the history is right, and that is exactly the
state in which nobody thinks to re-copy a gitignored file.

**The list is per-project and you cannot work it out from the failures**, because the two kinds fail
in opposite directions. Measured across one recovery:

| missing | how it failed |
|---|---|
| `app/assets/builds/` | **loudly** — `rspec` refused to run at all, 0 examples, exit 1, until `bin/rails tailwindcss:build` |
| `config/master.key`, `.env` | **silently** — credentials do not decrypt, sign-in lands signed-out, and hundreds of examples go red |
| a JS harness's `node_modules/` (an e2e suite under `qa/`, say) | **loudly** — the harness cannot load its dependencies until `npm ci` in its own directory |

The build directory is the lucky one: it names itself and costs a minute. The credentials key is the
dangerous one, because **its failure mode is a false regression** — red specs that read as a defect in
the branch you just recovered, on the day you are least inclined to doubt your setup. That is §5's
trap arriving a second time, through a door you thought you had already closed. So re-copy from the
project's own list before the first run, rather than deriving it from what breaks.

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

**Stashes and `origin/*` are shared by every worktree**: a bare `git stash pop` can take a peer's entry, and
`reset --soft origin/dev` can squash away their merged work ([both, and the safe forms](references/reading-a-list.md#the-stash-list-is-shared)).

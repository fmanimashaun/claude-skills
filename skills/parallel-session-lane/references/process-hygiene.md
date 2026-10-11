# Process hygiene: the processes you start are yours to end

`SKILL.md` §10 says do not clean up what you did not create. This is the other half: the processes
you DID start must not outlive the work that started them. On a shared machine, a leak in one session
becomes every session's outage.

## What happened (2026-10-03, measured)

A red-first reproduction of a process-killing bug ran **74 times in a loop**, with no containment.
Each run left a tree behind:
- every process in it was STOPPED (`ps` state `T`);
- each was re-parented to pid 1 once its parent exited;
- each held about 31 unreaped children.

The user reached 2,643 of 2,666 processes (`kern.maxprocperuid`). Every `fork()` on the machine then
failed with `EAGAIN`, and every session's gates reported `BlockingIOError`. That reads like a code
failure, and nothing pointed at the real cause.

The reproduction did have a cleanup step. It matched processes by a marker at the end of their command
line, but the leaked roots' command lines ended with something else, so it matched nothing, silently.

## The rules

1. **Run a reproduction of a process bug ONCE, and inside containment, never in a loop.** A red-first
   run of a leak is expected to leak, because that is the bug, so contain it. rails-flow ships the
   helper: `scripts/process_containment.py` in the rails-flow plugin. Use it from Python as
   `with contained():`, or wrap any command with `python3 <rails-flow>/scripts/process_containment.py -- <command>`.
   Every process started inside it inherits a unique environment token. When the block ends, even
   after a crash, every process carrying the token is frozen and killed. A second interrupt that arrives
   while the helper is cleaning up waits until the cleanup has finished; it does not abandon it.
2. **Count afterwards.** After a reproduction, check `ps` for leftovers, for example processes in
   state `T` or with parent pid 1. A clean exit status says nothing about what the run left behind.
3. **A watcher loop reaps what it starts and stops on its own condition.** Use `subprocess.run` or
   `wait()` for every child it spawns, so none lingers as a zombie, and give it a condition that ends
   it. "Loop until someone notices" is not a condition.
4. **Ownership comes from what you can prove you started.** A process group or session cannot hold a
   tree, because fixtures start children in new sessions on purpose. The parent-pid tree cannot either,
   because an orphan's parent becomes pid 1. The helper uses the environment, which survives both. A
   process that clears its own environment (`env -i`) escapes it; that is the documented limit.

## Two facts measured while building the helper

- **`RLIMIT_NPROC` cannot cap one fixture.** It counts EVERY process the user owns. With 500 already
  running, a cap of 64 made the next `fork()` fail at once (`EAGAIN`, macOS). There is no per-tree
  process limit to set, so the helper reports what it killed instead, and a fixture can assert on that.
- **The environment survives re-parenting.** A grandchild started in a new session, whose parent then
  exited (its parent pid becomes 1), is still found by its inherited token, read from the process's
  environment. Read it as separate `NAME=value` entries and compare each WHOLE: a search over printed
  text mistook another variable's value for the variable, and a reaper killed another session's process
  that way (#1646 review). Where the environment cannot be read, match nothing.

## What a session's end reaps

rails-flow's `SessionEnd` hook runs `scripts/session_reaper.py`, once, when the session ends. It cannot
block the end, and it never fails it. Claude Code sets `CLAUDE_CODE_SESSION_ID` (v2.1.132 and later) in
Bash and PowerShell tool subprocesses and in hook command subprocesses, and (v2.1.154 and later) in stdio
MCP server subprocesses; it matches the `session_id` in the hook's JSON input and is updated on `/clear`
(https://code.claude.com/docs/en/env-vars). Two consequences for the reaper: a process started before a
`/clear` carries the OLD id, so it is not this session's by that test; and a process the docs do not list
(a monitor, a background task) is not documented to carry the id at all, so the reaper may not find it. The
reaper signals a process only if ALL of these hold:

1. its environment has the variable named exactly `CLAUDE_CODE_SESSION_ID`, whose whole value is this
   session's id;
2. its parent is pid 1, so nothing is waiting on it;
3. it is stopped (`ps` state `T`).

It sends CONT, then TERM, then KILL to one that ignores TERM. Everything else is left alone: another
session's processes, a process whose command line merely mentions the id, a stopped process that still
has a parent, and a RUNNING orphan, which may be a server you meant to leave. It never matches a process
by its name or command line; `pkill -f rspec` killed other sessions' runs twice, and that is the habit
this refuses. It does not replace rule 1: contain a fixture so it does not leak, and let the reaper be the
net for what leaked anyway.

## The advisory that watches for it

rails-flow's session-start hook counts zombie processes (`ps` state `Z`) and, at 50 or more
(`RAILS_FLOW_ZOMBIE_WARN` to change it), prints the count and the busiest parents by command. It prints
nothing below the threshold, because this hook runs again after every compaction. It is advice: it
cannot stop the process that is leaking, and the leak is still fixed by rule 3 above.

The same hook also counts the user's STOPPED ORPHANS (state `T`, parent pid 1) and, at 3 or more
(`RAILS_FLOW_STOPPED_ORPHAN_WARN` to change it), prints the count and the owning session ids, read from
each process's environment. It is silent below the threshold. A session's own are reaped when it ends;
to clear one now, send the owning session's id to the reaper:
`echo '{"session_id":"<id>"}' | python3 <rails-flow>/scripts/session_reaper.py`.

## A long-running read is a second party in your own tree

`SKILL.md` §4 is about two sessions. **The single-session case reads identically and nobody
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

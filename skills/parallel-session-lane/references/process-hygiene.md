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
   after a crash, every process carrying the token is frozen and killed.
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
  exited (its parent pid becomes 1), is still found by its inherited token, through `ps -E` on macOS or
  `/proc/<pid>/environ` on Linux.

## The advisory that watches for it

rails-flow's session-start hook counts zombie processes (`ps` state `Z`) and, at 50 or more
(`RAILS_FLOW_ZOMBIE_WARN` to change it), prints the count and the busiest parents by command. It prints
nothing below the threshold, because this hook runs again after every compaction. It is advice: it
cannot stop the process that is leaking, and the leak is still fixed by rule 3 above.

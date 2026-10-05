# Three isolated resources, not one

`SKILL.md` §1 says each unit of work gets its own worktree. This is the detail behind its first
property, moved here verbatim so the skill body stays inside its 500-line Level-2 budget (#1581).

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

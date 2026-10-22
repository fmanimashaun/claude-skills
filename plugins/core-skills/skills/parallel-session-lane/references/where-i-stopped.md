# Leave a where-I-stopped note a killed session could resume from

A session can be killed with no warning: a restart, a spend limit, an expired login. Whatever it knew
and did not write down is gone, and the next session, or you under a new name, starts from the disk.

**Two records, and they are not the same thing:**
- **The facts file is written for you.** If rails-flow is installed, its Stop hook rewrites
  `<git-common-dir>/handoff/<worktree-key>.md` after every turn: branch, HEAD sha, commits not on any
  remote, and uncommitted files. It is keyed by WORKTREE, so it is never another session's. The next
  session start points at it, and says when HEAD has moved since it was written.
- **The where-I-stopped note is yours.** Keep it in `HANDOFF.md`, or as a comment on the PR. It is
  not a work order: `/rails-flow:handoff` writes a work order, which is a plan for someone to execute.
  This note says what is true and what was asked. Keep it current at each meaningful step, not at the
  end, because there may be no end.

**What goes in the note:**
- **Each claim with the command that verifies it.** For example: "pushed: `git rev-parse HEAD` =
  `origin/<branch>`", or "suite green: `bundle exec rspec spec/requests/x_spec.rb`". A reader can
  rerun the command. "Done" with nothing behind it is a claim the next session takes on trust.
- **The last request, word for word.** A paraphrase drops the clause that mattered. Copy the message.
- **Numbers copied from a measurement, never retyped from memory.** Paste the line the command
  printed (`8099 examples, 8 failures`) and say when it ran. A remembered number is stale by default.

**A first-person note with no author misleads its reader.** "I shipped X" in a file keyed to a
directory reads as true for whoever opens it next. Name the session, the worktree and the HEAD sha the
note was written at, so a reader on a different HEAD knows the note describes an older state.

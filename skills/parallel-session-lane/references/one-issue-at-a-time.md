# One issue at a time, and the worktree is yours to end

The full text of `SKILL.md` §1a (#1581): the owner's four rules, the coordinator's half, what the rails-flow
`guard-worktree` hook refuses, and its limit.

The owner's rules for parallel sessions (#1581). §1 says make a worktree per unit of work; these say
when you may make the next one, and what you owe the last one.

1. **One issue at a time per session.** An issue is in progress until its PR **merges**.
2. **A new assignment that arrives mid-issue is queued, or handed back.** Tell the assigner to give it to
   someone else if it cannot wait. It never gets a second worktree.
3. **Clean up when done.** `git worktree remove <path>` (never `--force`, §1) when the PR merges, or when a
   review or a measurement finishes. Reviews prefer a `git archive` export, and a review is not an issue.
4. **Resume in place.** After a restart or a spend-limit cutoff, continue in the abandoned worktree
   (`git worktree list`, `HANDOFF.md`, the session-start pointer). Never create a new worktree for work
   already started: that is how the first one is orphaned with its uncommitted edits.

**The coordinator's half.** Assign a build issue only to a session with nothing in progress, and give a
waiting session a review, not a second issue. Record each lane with
`python3 <rails-flow>/hooks/scripts/lib/coordination.py assign --session-id <coordinator> --path <worktree>
--branch <branch> --issue <n> --owner <session>`. **Only the coordinator writes the record** (one file,
`$(git rev-parse --git-common-dir)/coordination.json`, keyed by worktree path, never by session name:
names change at every restart); sessions only read it.

**What makes it true: the rails-flow `guard-worktree` hook.** With rails-flow installed, a
`git worktree add` is **denied** when (a) this session holds a recorded lane whose branch is not merged
into the integration branch, or (b) a worktree for the same branch, or the same issue, already exists and
is not merged. Rule (b) reads `git worktree list` alone: it needs no record and no session identity. The
denial names the existing worktree, so a resumed session continues there. At session start rails-flow
prints the lane to resume, finished worktrees (merged, clean) to remove, and a warning when zombie
processes pile up (see [process hygiene](references/process-hygiene.md)). Without rails-flow these four
rules are advice, and only you keep them.

**Its limit, stated: it protects against accident, not impersonation.** A session's identity is the
`session_id` it sends, and the coordinator writes the lane record, so a session nobody recorded passes
rule (a), and anything that can send the coordinator's id can write the record. The issue number is read
only from a branch or directory written `issue-N`, `N-slug` or `.../N-slug`; a branch with none gets the
exact-branch check alone. A worktree made by hand outside the agent, by `git -C <another repository>`, or through
a shell variable, function or alias is out of reach. A `$VAR` or `$(...)` in the BRANCH cannot be
judged without running it, and a pipe to `sh`, `find -exec`, an alias and a heredoc are out of reach: the guard
targets accidents. A `git worktree add` the hook can find but not parse is refused, never allowed.
